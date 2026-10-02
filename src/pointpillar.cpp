/*
 * SPDX-FileCopyrightText: Copyright (c) 2022 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "pp_infer/pointpillar.h"
#include "pp_infer/cuda_resources.hpp"
#include "pp_infer/model_contract.hpp"
#include "pp_infer/output_contract.hpp"
#include <NvInfer.h>
#include <NvInferPlugin.h>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
class Logger final : public nvinfer1::ILogger {
 public:
  void log(Severity severity, const char* message) noexcept override {
    if (severity <= Severity::kWARNING) std::cerr << "TensorRT: " << message << '\n';
  }
};
struct Profiler final : nvinfer1::IProfiler {
  float total_ms{};
  bool enabled{};
  void reportLayerTime(const char*, float ms) noexcept override { if (enabled) total_ms += ms; }
};
constexpr std::array<const char*, 4> names{"points", "num_points", "output_boxes", "num_boxes"};
std::vector<char> read_engine(const std::string& path) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) throw std::runtime_error("Cannot open engine: " + path + "; build it offline with trtexec");
  const auto length = input.tellg();
  if (length <= 0 || length > (std::streamoff(1) << 30))
    throw std::runtime_error("Engine must be nonempty and at most 1 GiB");
  std::vector<char> bytes(static_cast<std::size_t>(length));
  input.seekg(0);
  if (!input.read(bytes.data(), length)) throw std::runtime_error("Incomplete engine read");
  return bytes;
}
}

struct PointPillar::Impl {
  // Declaration order retains logger/runtime/engine/profiler until context dies.
  Logger logger;
  std::unique_ptr<nvinfer1::IRuntime> runtime;
  std::unique_ptr<nvinfer1::ICudaEngine> engine;
  Profiler profiler;
  pp_infer::CudaStream stream;
  std::unique_ptr<nvinfer1::IExecutionContext> context;
  std::array<std::unique_ptr<pp_infer::DeviceBuffer>, 4> buffers;
  std::vector<float> host_boxes;
  std::size_t points{}, boxes{};
  bool faulted{};

  explicit Impl(const std::string& path) {
    if (!initLibNvInferPlugins(&logger, "")) throw std::runtime_error("Plugin initialization failed");
    runtime.reset(nvinfer1::createInferRuntime(logger));
    if (!runtime) throw std::runtime_error("TensorRT runtime creation failed");
    const auto bytes = read_engine(path);
    engine.reset(runtime->deserializeCudaEngine(bytes.data(), bytes.size()));
    if (!engine) throw std::runtime_error("Engine deserialization failed; verify TensorRT version and PointPillars plugins");
    if (engine->getNbIOTensors() != 4 || engine->getNbOptimizationProfiles() != 1)
      throw std::runtime_error("Require four named I/O tensors and one batch-one profile");
    for (std::size_t i = 0; i < names.size(); ++i) {
      const auto mode = i < 2 ? nvinfer1::TensorIOMode::kINPUT : nvinfer1::TensorIOMode::kOUTPUT;
      const auto type = i % 2 == 0 ? nvinfer1::DataType::kFLOAT : nvinfer1::DataType::kINT32;
      if (engine->getTensorIOMode(names[i]) != mode || engine->getTensorDataType(names[i]) != type ||
          engine->getTensorLocation(names[i]) != nvinfer1::TensorLocation::kDEVICE ||
          engine->getTensorFormat(names[i]) != nvinfer1::TensorFormat::kLINEAR ||
          engine->isShapeInferenceIO(names[i]))
        throw std::runtime_error(std::string("Unsupported tensor contract: ") + names[i]);
    }
    auto shape = engine->getTensorShape("points");
    if (shape.nbDims != 3 || (shape.d[0] != -1 && shape.d[0] != 1) || shape.d[1] <= 0 || shape.d[2] != 4 ||
        shape.d[1] > std::numeric_limits<std::int32_t>::max())
      throw std::runtime_error("Require points [batch, P, 4] with fixed positive INT32 capacity");
    points = static_cast<std::size_t>(shape.d[1]);
    context.reset(engine->createExecutionContext());
    if (!context) throw std::runtime_error("Context creation failed");
    shape.d[0] = 1;
    if (!context->setInputShape("points", shape) || !context->setInputShape("num_points", nvinfer1::Dims{1, {1}}) ||
        context->inferShapes(0, nullptr) != 0)
      throw std::runtime_error("Batch-one shape resolution failed");
    const auto count_shape = context->getTensorShape("num_boxes");
    const auto input_count_shape = context->getTensorShape("num_points");
    shape = context->getTensorShape("output_boxes");
    if (input_count_shape.nbDims != 1 || input_count_shape.d[0] != 1 ||
        count_shape.nbDims != 1 || count_shape.d[0] != 1 ||
        shape.nbDims != 3 || shape.d[0] != 1 || shape.d[1] <= 0 || shape.d[2] != 9 ||
        shape.d[1] > std::numeric_limits<std::int32_t>::max())
      throw std::runtime_error("Require output_boxes [1, B, 9] and counts [1]");
    boxes = static_cast<std::size_t>(shape.d[1]);
    host_boxes.resize(pp_infer::checked_product(boxes, 9));
    const std::array<std::size_t, 4> sizes{
      pp_infer::checked_product(points, 4 * sizeof(float)), sizeof(std::int32_t),
      pp_infer::checked_product(host_boxes.size(), sizeof(float)), sizeof(std::int32_t)};
    for (std::size_t i = 0; i < names.size(); ++i) {
      buffers[i] = std::make_unique<pp_infer::DeviceBuffer>(sizes[i]);
      if (!context->setTensorAddress(names[i], buffers[i]->get()))
        throw std::runtime_error(std::string("Cannot bind tensor: ") + names[i]);
    }
    context->setProfiler(&profiler);
  }
  ~Impl() { cudaStreamSynchronize(stream.get()); }
};

PointPillar::PointPillar(const std::string& path) : impl_(std::make_unique<Impl>(path)) {}
PointPillar::~PointPillar() = default;
std::size_t PointPillar::getPointCapacity() const { return impl_->points; }
std::vector<Bndbox> PointPillar::infer(const float* xyzi, std::size_t count,
                                    float threshold, int top_n, std::size_t classes, bool profile) {
  auto& state = *impl_;
  if (state.faulted) throw std::runtime_error("GPU runtime faulted; restart the node");
  if (count > state.points || (count && !xyzi) || !classes || top_n <= 0 ||
      !std::isfinite(threshold) || threshold < 0 || threshold > 1)
    throw std::invalid_argument("Invalid inference input or NMS configuration");
  if (!count) return {};
  const std::int32_t encoded_count = static_cast<std::int32_t>(count);
  std::int32_t detected{};
  const auto stream = state.stream.get();
  try {
    // Fixed capacity input: clear padding, then copy only valid points.
    pp_infer::cuda_check(cudaMemsetAsync(state.buffers[0]->get(), 0, state.points * 4 * sizeof(float), stream), "clear points");
    pp_infer::cuda_check(cudaMemcpyAsync(state.buffers[0]->get(), xyzi, count * 4 * sizeof(float), cudaMemcpyHostToDevice, stream), "copy points");
    pp_infer::cuda_check(cudaMemcpyAsync(state.buffers[1]->get(), &encoded_count, sizeof(encoded_count), cudaMemcpyHostToDevice, stream), "copy count");
    pp_infer::cuda_check(cudaMemsetAsync(state.buffers[3]->get(), 0, sizeof(detected), stream), "clear output count");
    state.profiler.total_ms = 0;
    // TensorRT 10.16 rejects null in setProfiler. Retain the owned profiler;
    // callbacks collect timings only when requested (TRT callback overhead remains).
    state.profiler.enabled = profile;
    state.context->setEnqueueEmitsProfile(true);
    if (!state.context->enqueueV3(stream)) throw std::runtime_error("TensorRT enqueueV3 failed");
    pp_infer::cuda_check(cudaMemcpyAsync(&detected, state.buffers[3]->get(), sizeof(detected), cudaMemcpyDeviceToHost, stream), "copy output count");
    pp_infer::cuda_check(cudaStreamSynchronize(stream), "complete inference");
    pp_infer::checked_detection_count(detected, state.boxes);
    if (detected) {
      pp_infer::cuda_check(cudaMemcpyAsync(state.host_boxes.data(), state.buffers[2]->get(),
        static_cast<std::size_t>(detected) * 9 * sizeof(float), cudaMemcpyDeviceToHost, stream), "copy boxes");
      pp_infer::cuda_check(cudaStreamSynchronize(stream), "complete boxes");
    }
  } catch (...) {
    cudaStreamSynchronize(stream);  // Drain references to stack/input data before unwinding.
    state.faulted = true;
    throw;
  }
  auto raw = pp_infer::decode_boxes(state.host_boxes.data(), static_cast<std::size_t>(detected), classes);
  std::vector<Bndbox> result;
  nms_cpu(raw, threshold, result, top_n);
  return result;
}
