#include "pp_infer/ros_adapter.hpp"

#include <pcl_conversions/pcl_conversions.h>
#include <algorithm>
#include <array>
#include <cstring>
#include <limits>
#include <rcl_interfaces/msg/parameter_descriptor.hpp>

namespace pp_infer {
ProcessingConfig declare_processing_config(rclcpp::Node& node) {
  rcl_interfaces::msg::ParameterDescriptor descriptor;
  descriptor.read_only = true;
  ProcessingConfig result;
  result.classes = node.declare_parameter<std::vector<std::string>>("class_names", {}, descriptor);
  result.intensity_scale = node.declare_parameter<double>("intensity_scale", 1, descriptor);
  const double threshold = node.declare_parameter<double>("nms_iou_thresh", 0.01, descriptor);
  const auto top_n = node.declare_parameter<std::int64_t>("pre_nms_top_n", 4096, descriptor);
  const auto bytes = node.declare_parameter<std::int64_t>("max_cloud_bytes", 64 * 1024 * 1024, descriptor);
  result.model_path = node.declare_parameter<std::string>("model_path", "", descriptor);
  result.engine_path = node.declare_parameter<std::string>("engine_path", "", descriptor);
  result.build_precision = node.declare_parameter<std::string>("data_type", "fp16", descriptor);
  if (result.classes.empty() || std::any_of(result.classes.begin(), result.classes.end(),
      [](const std::string& name) { return name.empty(); }))
    throw std::invalid_argument("class_names must contain nonempty class labels from the model contract");
  if (!std::isfinite(result.intensity_scale) || result.intensity_scale <= 0 ||
      !std::isfinite(threshold) || threshold < 0 || threshold > 1 ||
      top_n <= 0 || top_n > std::numeric_limits<int>::max() || bytes <= 0)
    throw std::invalid_argument("Invalid intensity_scale, NMS threshold/top_n, or max_cloud_bytes");
  if (static_cast<std::uint64_t>(bytes) > std::numeric_limits<std::size_t>::max())
    throw std::invalid_argument("max_cloud_bytes cannot fit in size_t");
  if (result.engine_path.empty()) throw std::invalid_argument("engine_path must be configured");
  if (result.build_precision != "fp32" && result.build_precision != "fp16")
    throw std::invalid_argument("Legacy data_type must be fp32 or fp16; it does not change a loaded engine");
  result.nms_threshold = static_cast<float>(threshold);
  result.top_n = static_cast<int>(top_n);
  result.maximum_cloud_bytes = static_cast<std::size_t>(bytes);
  return result;
}

std::size_t pack_xyzi(const sensor_msgs::msg::PointCloud2& msg,
                     const InputLimits& limits,
                     pcl::PointCloud<pcl::PointXYZI>& scratch,
                     std::vector<float>& packed) {
  packed.clear();
  limits.validate();
  const std::size_t count = checked_product(msg.width, msg.height);
  const std::size_t row_bytes = checked_product(msg.width, msg.point_step);
  const std::size_t total_bytes = checked_product(msg.height, msg.row_step);
  if (count > limits.point_capacity || msg.data.size() > limits.maximum_cloud_bytes ||
      total_bytes > limits.maximum_cloud_bytes)
    throw std::invalid_argument("PointCloud2 exceeds point capacity or message byte limit");
  if (msg.row_step < row_bytes || msg.data.size() != total_bytes)
    throw std::invalid_argument("PointCloud2 row_step/data length is inconsistent");
  if (count == 0) {
    if (!msg.data.empty()) throw std::invalid_argument("Empty cloud contains unexpected data");
    scratch.clear();
    return 0;
  }
  const std::uint16_t endian_probe = 1;
  if (msg.is_bigendian || *reinterpret_cast<const unsigned char*>(&endian_probe) != 1)
    throw std::invalid_argument("Only little-endian PointCloud2 FLOAT32 data is supported");
  if (msg.point_step < 4 * sizeof(float))
    throw std::invalid_argument("PointCloud2 point_step cannot hold XYZI");
  std::array<std::uint32_t, 4> offsets{};
  const std::array<std::string, 4> names{{"x", "y", "z", "intensity"}};
  for (std::size_t i = 0; i < names.size(); ++i) {
    const sensor_msgs::msg::PointField* match = nullptr;
    for (const auto& field : msg.fields) {
      if (field.name != names[i]) continue;
      if (match) throw std::invalid_argument("Duplicate required PointCloud2 field");
      match = &field;
    }
    if (!match || match->count != 1 || match->datatype != sensor_msgs::msg::PointField::FLOAT32 ||
        match->offset > msg.point_step - sizeof(float))
      throw std::invalid_argument("Missing or unsupported scalar FLOAT32 XYZI field/offset");
    offsets[i] = match->offset;
  }
  std::sort(offsets.begin(), offsets.end());
  for (std::size_t i = 1; i < offsets.size(); ++i)
    if (offsets[i] - offsets[i - 1] < sizeof(float))
      throw std::invalid_argument("PointCloud2 XYZI fields overlap");
  pcl::fromROSMsg(msg, scratch);
  if (scratch.size() != count) throw std::runtime_error("PCL produced an unexpected point count");
  packed.reserve(checked_product(limits.point_capacity, 4));
  for (const auto& point : scratch) {
    if (!std::isfinite(point.x) || !std::isfinite(point.y) ||
        !std::isfinite(point.z) || !std::isfinite(point.intensity)) continue;
    const double normalized = point.intensity / limits.intensity_scale;
    if (!std::isfinite(normalized) || std::abs(normalized) > std::numeric_limits<float>::max()) {
      packed.clear();
      throw std::invalid_argument("Normalized intensity exceeds finite FLOAT32 range");
    }
    packed.insert(packed.end(), {point.x, point.y, point.z, static_cast<float>(normalized)});
  }
  return packed.size() / 4;
}

vision_msgs::msg::Detection3DArray make_detections(
    const std_msgs::msg::Header& header, const std::vector<Bndbox>& boxes,
    const std::vector<std::string>& classes) {
  vision_msgs::msg::Detection3DArray array;
  array.header = header;
  array.detections.reserve(boxes.size());
  for (const auto& box : boxes) {
    if (!valid_box(box) || static_cast<std::size_t>(box.id) >= classes.size() || classes[box.id].empty())
      throw std::invalid_argument("Detection has invalid geometry/class/score");
    vision_msgs::msg::Detection3D detection;
    detection.header = header;
    detection.bbox.center.position.x = box.x;
    detection.bbox.center.position.y = box.y;
    detection.bbox.center.position.z = box.z;
    detection.bbox.size.x = box.l;
    detection.bbox.size.y = box.w;
    detection.bbox.size.z = box.h;
    detection.bbox.center.orientation.z = std::sin(static_cast<double>(box.rt) / 2);
    detection.bbox.center.orientation.w = std::cos(static_cast<double>(box.rt) / 2);
    vision_msgs::msg::ObjectHypothesisWithPose hypothesis;
    hypothesis.hypothesis.class_id = std::to_string(box.id);
    hypothesis.hypothesis.score = box.score;
    hypothesis.pose.pose = detection.bbox.center;
    detection.results.push_back(hypothesis);
    array.detections.push_back(detection);
  }
  return array;
}
}  // namespace pp_infer
