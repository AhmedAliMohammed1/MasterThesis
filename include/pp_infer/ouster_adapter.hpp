#pragma once

#include "pp_infer/model_contract.hpp"
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <string>

namespace pp_infer {
// Explicit source selection; no fallback or per-frame normalization.
sensor_msgs::msg::PointCloud2 ouster_to_xyzi(
    const sensor_msgs::msg::PointCloud2& input, const std::string& source,
    const InputLimits& limits);
rclcpp::Node::SharedPtr make_ouster_adapter(
    const rclcpp::NodeOptions& options = rclcpp::NodeOptions{});
}  // namespace pp_infer
