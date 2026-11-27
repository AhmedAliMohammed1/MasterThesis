/*
 * Copyright (c) 2022, NVIDIA CORPORATION. All rights reserved.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software and associated documentation files (the "Software"),
 * to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense,
 * and/or sell copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
 * DEALINGS IN THE SOFTWARE.
 */

#define BOOST_BIND_NO_PLACEHOLDERS

#include <chrono>
#include <memory>
#include <iostream>
#include <fstream>
#include <vector>
#include <iomanip>
#include <map>
#include <algorithm>
#include <cassert>
#include <sstream>
#include <unistd.h>
#include <string>
#include <limits>

#include "cuda_runtime.h"
#include "pp_infer/pointpillar.h"
#include "pp_infer/ros_adapter.hpp"
#include "pp_infer/detection_output.hpp"
#include "pp_infer/latest_frame.hpp"

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"
#include "sensor_msgs/msg/point_cloud2.hpp"
#include "vision_msgs/msg/detection3_d_array.hpp"
#include "pcl_conversions/pcl_conversions.h"


using namespace std::chrono_literals;

// A single inference callback owns the GPU context in both processing modes.

class MinimalPublisher : public rclcpp::Node
{
public:
  MinimalPublisher()
  : Node("minimal_publisher")
  {
    const auto config = pp_infer::declare_processing_config(*this);
    class_names = config.classes;
    nms_iou_thresh = config.nms_threshold;
    pre_nms_top_n = config.top_n;
    model_path = config.model_path;
    engine_path = config.engine_path;
    data_type = config.build_precision;
    intensity_scale = config.intensity_scale;
    max_cloud_bytes = config.maximum_cloud_bytes;

    rcl_interfaces::msg::ParameterDescriptor descriptor;
    descriptor.read_only = true;
    descriptor.description = "latest skips superseded scans; all_frames preserves sequential processing.";
    processing_mode = declare_parameter<std::string>("processing_mode", "all_frames", descriptor);
    if (processing_mode != "latest" && processing_mode != "all_frames")
      throw std::invalid_argument("processing_mode must be latest or all_frames");

    output = std::make_unique<pp_infer::DetectionOutput>(*this, class_names, processing_mode == "latest" ? 1 : 700);
    pointpillar = std::make_unique<PointPillar>(engine_path);

    performance_ = create_publisher<diagnostic_msgs::msg::DiagnosticArray>(
      "~/performance", rclcpp::QoS(1).reliable().transient_local());
    if (processing_mode == "latest") {
      // Receipt and inference have separate mutually exclusive groups. Only the
      // inference timer owns TensorRT, packing buffers, and DetectionOutput.
      inference_group_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
      subscription_ = create_subscription<sensor_msgs::msg::PointCloud2>(
        "/point_cloud", rclcpp::QoS(1).best_effort(),
        [this](sensor_msgs::msg::PointCloud2::ConstSharedPtr msg) { pending_.push(std::move(msg)); });
      timer_ = create_wall_timer(1ms, [this] {
        auto frame = pending_.take();
        if (frame) topic_callback(frame->value, frame->received);
      }, inference_group_);
    } else {
      subscription_ = create_subscription<sensor_msgs::msg::PointCloud2>(
        "/point_cloud", rclcpp::QoS(700).reliable(),
        [this](sensor_msgs::msg::PointCloud2::ConstSharedPtr msg) { topic_callback(msg, Clock::now()); });
    }
    RCLCPP_INFO(get_logger(), "Processing mode: %s; timings: %s/performance",
      processing_mode.c_str(), get_fully_qualified_name());

  }

private:
  using Clock = std::chrono::steady_clock;
  std::string processing_mode;
  pp_infer::LatestFrame<sensor_msgs::msg::PointCloud2::ConstSharedPtr> pending_;
  rclcpp::CallbackGroup::SharedPtr inference_group_;
  rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr performance_;

  void publish_performance(const std_msgs::msg::Header& header, const char* outcome,
      Clock::time_point received, Clock::time_point started, double pack_ms,
      const InferenceTimings& timings, double publish_ms) {
    diagnostic_msgs::msg::DiagnosticArray message;
    message.header = header;
    diagnostic_msgs::msg::DiagnosticStatus status;
    status.name = std::string(get_fully_qualified_name()) + "/performance";
    status.hardware_id = "pointpillars";
    status.message = outcome;
    status.level = std::string(outcome) == "ok" ? 0 : 1;
    auto add = [&](const std::string& key, const std::string& value) {
      diagnostic_msgs::msg::KeyValue entry;
      entry.key = key; entry.value = value; status.values.push_back(entry);
    };
    add("processing_mode", processing_mode);
    add("replaced_pending_frames_total", std::to_string(pending_.replaced()));
    add("queue_wait_ms", std::to_string(std::chrono::duration<double, std::milli>(started - received).count()));
    add("pack_ms", std::to_string(pack_ms));
    add("gpu_pipeline_ms", std::to_string(timings.gpu_pipeline_ms));
    add("decode_ms", std::to_string(timings.decode_ms));
    add("nms_ms", std::to_string(timings.nms_ms));
    add("publish_ms", std::to_string(publish_ms));
    add("processing_ms", std::to_string(std::chrono::duration<double, std::milli>(Clock::now() - started).count()));
    // Never subtract recorded sensor timestamps from the wall clock: replay
    // recordings can have different epochs. Header is retained for correlation.
    message.status.push_back(std::move(status));
    performance_->publish(message);
  }
  std::vector<std::string> class_names;
  float nms_iou_thresh;
  int pre_nms_top_n;
  bool do_profile{false};
  std::string model_path;
  std::string engine_path;
  std::string data_type;
  double intensity_scale;
  std::size_t max_cloud_bytes;
  pcl::PointCloud<pcl::PointXYZI> cloud_scratch;
  std::vector<float> packed_points;
  std::unique_ptr<PointPillar> pointpillar;
  std::unique_ptr<pp_infer::DetectionOutput> output;


  void topic_callback(const sensor_msgs::msg::PointCloud2::ConstSharedPtr msg, Clock::time_point received)
  {
    const auto started = Clock::now();
    InferenceTimings timings;
    double pack_ms = 0;
    double publish_ms = 0;
    std::size_t valid_points;
    try {
      valid_points = pp_infer::pack_xyzi(*msg,
        {pointpillar->getPointCapacity(), max_cloud_bytes, intensity_scale},
        cloud_scratch, packed_points);
    } catch (const std::exception& error) {
      RCLCPP_WARN(this->get_logger(), "Dropping invalid point cloud: %s", error.what());
      output->report_failure(msg->header, pp_infer::FrameFailure::invalid_cloud);
      publish_performance(msg->header, "invalid_cloud", received, started,
        std::chrono::duration<double, std::milli>(Clock::now() - started).count(), timings, publish_ms);
      return;
    }
    pack_ms = std::chrono::duration<double, std::milli>(Clock::now() - started).count();
    try {
      std::vector<Bndbox> detections;
      if (valid_points != 0)
        detections = pointpillar->infer(packed_points.data(), valid_points,
          nms_iou_thresh, pre_nms_top_n, class_names.size(), do_profile, &timings);
      const auto before_publish = Clock::now();
      output->publish(msg->header, detections);
      publish_ms = std::chrono::duration<double, std::milli>(Clock::now() - before_publish).count();
      publish_performance(msg->header, "ok", received, started, pack_ms, timings, publish_ms);
    } catch (const std::exception& error) {
      RCLCPP_ERROR(this->get_logger(), "Inference failed; frame dropped: %s", error.what());
      output->report_failure(msg->header, pp_infer::FrameFailure::inference_error);
      publish_performance(msg->header, "inference_error", received, started, pack_ms, timings, publish_ms);
    }
  }

  rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr subscription_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<MinimalPublisher>();
  rclcpp::executors::MultiThreadedExecutor executor(rclcpp::ExecutorOptions(), 2);
  executor.add_node(node);
  executor.spin();
  rclcpp::shutdown();
  return 0;
}
