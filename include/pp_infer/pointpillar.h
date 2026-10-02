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

#pragma once
#include <cstddef>
#include <memory>
#include <string>
#include <vector>
#include "postprocess.h"

// One caller owns this context. Engine generation is an offline operation.
class PointPillar {
 public:
  explicit PointPillar(const std::string& engine_file);
  ~PointPillar();
  PointPillar(const PointPillar&) = delete;
  PointPillar& operator=(const PointPillar&) = delete;
  std::size_t getPointCapacity() const;
  std::vector<Bndbox> infer(const float* xyzi, std::size_t count,
                           float nms_threshold, int top_n,
                           std::size_t class_count, bool profile = false);
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
