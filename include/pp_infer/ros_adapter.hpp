#pragma once

#include "pp_infer/model_contract.hpp"
#include "pp_infer/postprocess.h"
#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <vision_msgs/msg/detection3_d_array.hpp>
#include <cstdint>
#include <string>
#include <vector>

namespace pp_infer {
struct ProcessingConfig {
  std::vector<std::string> classes;
  double intensity_scale;
  float nms_threshold;
  int top_n;
  std::size_t maximum_cloud_bytes;
  std::string model_path;
  std::string engine_path;
  std::string build_precision;
};
ProcessingConfig declare_processing_config(rclcpp::Node& node);

// Supports scalar FLOAT32 XYZI, little-endian data, including row padding.
// Rejects oversized/malformed clouds before PCL allocation; drops nonfinite
// points. Replaces packed on every attempt. Scratch is reusable by one owner.
// Capacity also bounds raw points before filtering to keep PCL allocation bounded.
std::size_t pack_xyzi(const sensor_msgs::msg::PointCloud2& message,
                     const InputLimits& limits,
                     pcl::PointCloud<pcl::PointXYZI>& scratch,
                     std::vector<float>& packed);

vision_msgs::msg::Detection3DArray make_detections(
    const std_msgs::msg::Header& header, const std::vector<Bndbox>& boxes,
    const std::vector<std::string>& classes);
}  // namespace pp_infer
