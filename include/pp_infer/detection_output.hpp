#pragma once

#include "pp_infer/ros_adapter.hpp"
#include <diagnostic_msgs/msg/diagnostic_array.hpp>
#include <visualization_msgs/msg/marker_array.hpp>

namespace pp_infer {
enum class FrameFailure { invalid_cloud, inference_error };

// Publication and monitoring shared by the GPU node and GPU-free ROS tests.
// Call once per input, from a single owner. Parameters are read only after
// committed ROS updates; rejected atomic parameter batches have no side effects.
class DetectionOutput {
 public:
  DetectionOutput(rclcpp::Node& node, std::vector<std::string> classes);
  void publish(const std_msgs::msg::Header& header, const std::vector<Bndbox>& boxes);
  void report_failure(const std_msgs::msg::Header& header, FrameFailure failure);

 private:
  void publish_monitor(const std_msgs::msg::Header& header, const char* status,
                       double threshold, std::size_t before, std::size_t after, bool valid);
  rclcpp::Node& node_;
  std::vector<std::string> classes_;
  rclcpp::Publisher<vision_msgs::msg::Detection3DArray>::SharedPtr detections_;
  rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr stats_;
  rclcpp::Publisher<visualization_msgs::msg::MarkerArray>::SharedPtr count_;
  rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr parameter_callback_;
  std::uint64_t processed_frames_{0}, total_published_{0}, total_filtered_{0};
  std::uint64_t invalid_cloud_frames_{0}, inference_error_frames_{0};
};
}  // namespace pp_infer
