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

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"
#include "sensor_msgs/msg/point_cloud2.hpp"
#include "vision_msgs/msg/detection3_d_array.hpp"
#include "pcl_conversions/pcl_conversions.h"


using std::placeholders::_1;
using namespace std::chrono_literals;

/* This example creates a subclass of Node and uses std::bind() to register a
 * member function as a callback from the timer. */

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

    pointpillar = std::make_unique<PointPillar>(engine_path);

    publisher_ = this->create_publisher<vision_msgs::msg::Detection3DArray>("bbox", 700);

    subscription_ = this->create_subscription<sensor_msgs::msg::PointCloud2>(
      "/point_cloud", 700, std::bind(&MinimalPublisher::topic_callback, this, _1));

  }

private:
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


  void topic_callback(const sensor_msgs::msg::PointCloud2::ConstSharedPtr msg)
  {
    std::size_t valid_points;
    try {
      valid_points = pp_infer::pack_xyzi(*msg,
        {pointpillar->getPointCapacity(), max_cloud_bytes, intensity_scale},
        cloud_scratch, packed_points);
    } catch (const std::exception& error) {
      RCLCPP_WARN(this->get_logger(), "Dropping invalid point cloud: %s", error.what());
      return;
    }
    if (valid_points == 0) {
      publisher_->publish(pp_infer::make_detections(msg->header, {}, class_names));
      return;
    }
    try {
      const auto detections = pointpillar->infer(packed_points.data(), valid_points,
        nms_iou_thresh, pre_nms_top_n, class_names.size(), do_profile);
      publisher_->publish(pp_infer::make_detections(msg->header, detections, class_names));
    } catch (const std::exception& error) {
      RCLCPP_ERROR(this->get_logger(), "Inference failed; frame dropped: %s", error.what());
    }
  }

  rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::Publisher<vision_msgs::msg::Detection3DArray>::SharedPtr publisher_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr subscription_;
  size_t count_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<MinimalPublisher>());
  rclcpp::shutdown();
  return 0;
}
