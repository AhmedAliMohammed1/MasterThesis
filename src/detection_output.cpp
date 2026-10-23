#include "pp_infer/detection_output.hpp"

#include <iomanip>
#include <limits>
#include <sstream>
#include <utility>
#include <rcl_interfaces/msg/parameter_descriptor.hpp>

namespace pp_infer {
namespace {
bool valid_threshold(double value) {
  return std::isfinite(value) && value >= 0 && value <= 1;
}
std::string number(double value) {
  std::ostringstream text;
  text << std::setprecision(std::numeric_limits<double>::max_digits10) << value;
  return text.str();
}
}  // namespace

DetectionOutput::DetectionOutput(rclcpp::Node& node, std::vector<std::string> classes)
    : node_(node), classes_(std::move(classes)) {
  rcl_interfaces::msg::ParameterDescriptor descriptor;
  descriptor.description = "Publish only detections with score >= this value. Finite [0,1]; dynamically configurable.";
  const double threshold = node_.declare_parameter<double>("confidence_threshold", 0.5, descriptor);
  if (!valid_threshold(threshold))
    throw std::invalid_argument("confidence_threshold must be finite and in [0,1]");
  parameter_callback_ = node_.add_on_set_parameters_callback(
    [](const std::vector<rclcpp::Parameter>& parameters) {
      rcl_interfaces::msg::SetParametersResult result;
      result.successful = true;
      for (const auto& parameter : parameters) {
        if (parameter.get_name() == "confidence_threshold" &&
            (parameter.get_type() != rclcpp::ParameterType::PARAMETER_DOUBLE ||
             !valid_threshold(parameter.as_double()))) {
          result.successful = false;
          result.reason = "confidence_threshold must be a double, finite and in [0,1]";
          break;
        }
      }
      return result;
    });
  detections_ = node_.create_publisher<vision_msgs::msg::Detection3DArray>("bbox", 700);
  // Derive from the resolved topic so bbox remappings also isolate monitoring.
  const std::string topic = detections_->get_topic_name();
  const auto monitor_qos = rclcpp::QoS(1).reliable().transient_local();
  stats_ = node_.create_publisher<diagnostic_msgs::msg::DiagnosticArray>(topic + "/stats", monitor_qos);
  count_ = node_.create_publisher<visualization_msgs::msg::MarkerArray>(topic + "/count", monitor_qos);
  RCLCPP_INFO(node_.get_logger(), "Confidence threshold %.3f; monitoring %s/stats and %s/count",
              threshold, topic.c_str(), topic.c_str());
}

void DetectionOutput::publish(const std_msgs::msg::Header& header, const std::vector<Bndbox>& boxes) {
  const double threshold = node_.get_parameter("confidence_threshold").as_double();
  auto message = make_detections(header, boxes, classes_, threshold);
  const auto published = message.detections.size();
  detections_->publish(message);  // An empty array clears the previous frame in consumers.
  ++processed_frames_;
  total_published_ += published;
  total_filtered_ += boxes.size() - published;
  publish_monitor(header, "ok", threshold, boxes.size(), published, true);
}

void DetectionOutput::report_failure(const std_msgs::msg::Header& header, FrameFailure failure) {
  if (failure == FrameFailure::invalid_cloud) ++invalid_cloud_frames_;
  else ++inference_error_frames_;
  publish_monitor(header, failure == FrameFailure::invalid_cloud ? "invalid_cloud" : "inference_error",
                  node_.get_parameter("confidence_threshold").as_double(), 0, 0, false);
}

void DetectionOutput::publish_monitor(const std_msgs::msg::Header& header, const char* frame_status,
                                     double threshold, std::size_t before, std::size_t after, bool valid) {
  diagnostic_msgs::msg::DiagnosticArray message;
  message.header = header;
  diagnostic_msgs::msg::DiagnosticStatus status;
  status.name = std::string(node_.get_fully_qualified_name()) + "/detections";
  status.hardware_id = "pointpillars";
  status.level = valid ? diagnostic_msgs::msg::DiagnosticStatus::OK : diagnostic_msgs::msg::DiagnosticStatus::WARN;
  status.message = valid ? "Latest processed scan" : "Frame dropped; detection count unavailable";
  auto add = [&](const std::string& key, const std::string& value) {
    diagnostic_msgs::msg::KeyValue field;
    field.key = key; field.value = value; status.values.push_back(field);
  };
  add("frame_status", frame_status);
  add("confidence_threshold", number(threshold));
  add("post_nms_count", valid ? std::to_string(before) : "unavailable");
  add("filtered_count", valid ? std::to_string(before - after) : "unavailable");
  add("published_count", valid ? std::to_string(after) : "unavailable");
  add("processed_frames_total", std::to_string(processed_frames_));
  add("published_detections_total", std::to_string(total_published_));
  add("filtered_detections_total", std::to_string(total_filtered_));
  add("invalid_cloud_frames_total", std::to_string(invalid_cloud_frames_));
  add("inference_error_frames_total", std::to_string(inference_error_frames_));
  message.status.push_back(status);
  stats_->publish(message);

  visualization_msgs::msg::Marker marker;
  marker.header = header;
  marker.ns = "detection_count"; marker.id = 0;
  marker.type = visualization_msgs::msg::Marker::TEXT_VIEW_FACING;
  marker.action = visualization_msgs::msg::Marker::ADD;
  marker.pose.orientation.w = 1;
  marker.pose.position.x = 8; marker.pose.position.z = 5;
  marker.scale.z = 0.8;
  marker.color.r = valid ? 0.2F : 1.0F;
  marker.color.g = valid ? 1.0F : 0.3F;
  marker.color.b = 0.2F; marker.color.a = 1;
  std::ostringstream display_threshold;
  display_threshold << std::setprecision(4) << threshold;
  marker.text = valid ? "Latest scan: " + std::to_string(after) + " boxes / " + std::to_string(before) +
      " before score filter\nscore >= " + display_threshold.str() + " | removed " + std::to_string(before - after)
      : std::string("Frame dropped: ") + frame_status + "\nDetection count unavailable";
  marker.text += "\nTotal published: " + std::to_string(total_published_) +
      " | total removed: " + std::to_string(total_filtered_) +
      "\nProcessed frames: " + std::to_string(processed_frames_) +
      " | dropped input/inference: " + std::to_string(invalid_cloud_frames_) +
      "/" + std::to_string(inference_error_frames_);
  visualization_msgs::msg::MarkerArray markers;
  markers.markers.push_back(marker);
  count_->publish(markers);
}
}  // namespace pp_infer
