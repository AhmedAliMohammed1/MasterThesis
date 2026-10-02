#include "pp_infer/ros_adapter.hpp"
#include <cstring>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
void require(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}
void rejects(const std::function<void()>& action) {
  try { action(); } catch (const std::invalid_argument&) { return; }
  throw std::runtime_error("Expected invalid_argument");
}
sensor_msgs::msg::PointCloud2 fixture() {
  sensor_msgs::msg::PointCloud2 msg;
  msg.width = 2; msg.height = 2; msg.point_step = 16; msg.row_step = 40;
  msg.header.frame_id = "lidar"; msg.header.stamp.sec = 123; msg.header.stamp.nanosec = 456;
  const std::vector<std::string> names{"x", "y", "z", "intensity"};
  for (std::size_t i = 0; i < names.size(); ++i) {
    sensor_msgs::msg::PointField f;
    f.name = names[i]; f.offset = i * 4; f.datatype = f.FLOAT32; f.count = 1;
    msg.fields.push_back(f);
  }
  msg.data.assign(80, 0xff);  // Row padding is deliberately not point data.
  for (unsigned row = 0; row < 2; ++row)
    for (unsigned col = 0; col < 2; ++col) {
      const float values[]{static_cast<float>(row * 2 + col), 2, 3, 255};
      std::memcpy(msg.data.data() + row * msg.row_step + col * msg.point_step, values, 16);
    }
  return msg;
}
rclcpp::NodeOptions options(std::vector<rclcpp::Parameter> extra = {}) {
  std::vector<rclcpp::Parameter> params{
    rclcpp::Parameter("class_names", std::vector<std::string>{"Vehicle", "Pedestrian"}),
    rclcpp::Parameter("engine_path", "fixture.engine")};
  params.insert(params.end(), extra.begin(), extra.end());
  // These fixtures test local parameter validation, not DDS services/events.
  rclcpp::NodeOptions opt;
  opt.parameter_overrides(params).enable_rosout(false).start_parameter_services(false)
    .start_parameter_event_publisher(false).use_global_arguments(false);
  return opt;
}
}  // namespace

int main(int argc, char** argv) {
  const bool data_only = argc > 1 && std::string(argv[1]) == "--data-only";
  const bool parameters_only = argc > 1 && std::string(argv[1]) == "--parameters-only";
  if (!data_only) rclcpp::init(argc, argv);
  pcl::PointCloud<pcl::PointXYZI> scratch;
  std::vector<float> packed;
  const pp_infer::InputLimits limits{4, 100, 255};
  const std::vector<std::pair<const char*, std::function<void()>>> tests{
    {"organized row padding and normalization", [&] {
      require(pp_infer::pack_xyzi(fixture(), limits, scratch, packed) == 4, "Wrong valid count");
      require(packed.size() == 16 && packed[8] == 2 && packed[15] == 1, "Row/normalization mismatch");
    }},
    {"empty replaces prior results", [&] {
      sensor_msgs::msg::PointCloud2 empty;
      require(pp_infer::pack_xyzi(empty, limits, scratch, packed) == 0 && packed.empty(), "Stale input");
    }},
    {"capacity and byte bounds before conversion", [&] {
      rejects([&] { pp_infer::pack_xyzi(fixture(), {3, 100, 255}, scratch, packed); });
      rejects([&] { pp_infer::pack_xyzi(fixture(), {4, 79, 255}, scratch, packed); });
    }},
    {"malformed row and data length", [&] {
      auto msg = fixture(); msg.row_step = 16;
      rejects([&] { pp_infer::pack_xyzi(msg, limits, scratch, packed); });
      msg = fixture(); msg.data.pop_back();
      rejects([&] { pp_infer::pack_xyzi(msg, limits, scratch, packed); });
    }},
    {"required field schema and offsets", [&] {
      auto msg = fixture(); msg.fields.pop_back();
      rejects([&] { pp_infer::pack_xyzi(msg, limits, scratch, packed); });
      msg = fixture(); msg.fields[0].offset = 16;
      rejects([&] { pp_infer::pack_xyzi(msg, limits, scratch, packed); });
      msg = fixture(); msg.fields[0].datatype = msg.fields[0].UINT32;
      rejects([&] { pp_infer::pack_xyzi(msg, limits, scratch, packed); });
      msg = fixture(); msg.fields[0].count = 2;
      rejects([&] { pp_infer::pack_xyzi(msg, limits, scratch, packed); });
      msg = fixture(); msg.fields.push_back(msg.fields[0]);
      rejects([&] { pp_infer::pack_xyzi(msg, limits, scratch, packed); });
      msg = fixture(); msg.fields[1].offset = 0;
      rejects([&] { pp_infer::pack_xyzi(msg, limits, scratch, packed); });
    }},
    {"unsupported byte order", [&] {
      auto msg = fixture(); msg.is_bigendian = true;
      rejects([&] { pp_infer::pack_xyzi(msg, limits, scratch, packed); });
    }},
    {"finite filtering regardless of is_dense", [&] {
      auto msg = fixture(); msg.is_dense = true;
      const float nan = std::numeric_limits<float>::quiet_NaN();
      std::memcpy(msg.data.data(), &nan, 4);
      require(pp_infer::pack_xyzi(msg, limits, scratch, packed) == 3, "NaN was not removed");
      require(packed[0] == 1, "Wrong finite point sequence");
    }},
    {"invalid intensity scale and normalized overflow", [&] {
      rejects([&] { pp_infer::pack_xyzi(fixture(), {4, 100, 0}, scratch, packed); });
      rejects([&] { pp_infer::pack_xyzi(fixture(), {4, 100, 1e-300}, scratch, packed); });
      require(packed.empty(), "Failed normalization retained stale points");
    }},
    {"checked arithmetic", [] {
      rejects([] { pp_infer::checked_product(std::numeric_limits<std::size_t>::max(), 4); });
      require(pp_infer::checked_product(0, 4) == 0, "Zero product incorrect");
    }},
    {"Jazzy class pose dimensions and headers", [] {
      const auto msg = fixture();
      Bndbox b{1, 2, 3, 4, 5, 6, 1.570796327F, 1, 0.8F};
      const auto out = pp_infer::make_detections(msg.header, {b}, {"Vehicle", "Pedestrian"});
      require(out.header == msg.header && out.detections[0].header == msg.header, "Header changed");
      const auto& d = out.detections[0];
      require(d.results[0].hypothesis.class_id == "1" && d.results[0].hypothesis.score == b.score, "Class/schema mismatch");
      require(d.bbox.size.x == 4 && d.bbox.size.y == 5 && d.bbox.size.z == 6, "Dimension ordering");
      require(std::abs(d.bbox.center.orientation.z - std::sqrt(0.5)) < 1e-6, "Yaw mismatch");
      require(d.results[0].pose.pose == d.bbox.center, "Hypothesis pose mismatch");
      require(pp_infer::make_detections(msg.header, {}, {}).detections.empty(), "Empty result mismatch");
    }},
    {"invalid output class and geometry", [] {
      rejects([] { pp_infer::make_detections(std_msgs::msg::Header{}, {{0, 0, 0, 2, 2, 2, 0, 3, 1}}, {"Vehicle"}); });
      rejects([] { pp_infer::make_detections(std_msgs::msg::Header{}, {Bndbox{}}, {"Vehicle"}); });
    }},
    {"typed config and immutable parameters", [] {
      rclcpp::Node node("config_test", options());
      const auto cfg = pp_infer::declare_processing_config(node);
      require(cfg.classes.size() == 2 && cfg.top_n == 4096, "Typed config mismatch");
      const auto change = node.set_parameters({rclcpp::Parameter("intensity_scale", 2.0)});
      require(!change[0].successful, "Processing parameter should require restart");
    }},
    {"invalid config rejected before runtime", [] {
      rclcpp::Node zero("zero_scale", options({rclcpp::Parameter("intensity_scale", 0.0)}));
      rejects([&] { pp_infer::declare_processing_config(zero); });
      rclcpp::Node huge("huge_top", options({rclcpp::Parameter("pre_nms_top_n", std::int64_t{2147483648LL})}));
      rejects([&] { pp_infer::declare_processing_config(huge); });
      auto missing = options(); missing.parameter_overrides({});
      rclcpp::Node no_classes("no_classes", missing);
      rejects([&] { pp_infer::declare_processing_config(no_classes); });
    }}
  };
  int result = 0;
  std::size_t passed = 0;
  for (std::size_t i = 0; i < tests.size(); ++i) {
    const bool parameter_case = i >= tests.size() - 2;
    if ((data_only && parameter_case) || (parameters_only && !parameter_case)) continue;
    const auto& test = tests[i];
    try { test.second(); }
    catch (const std::exception& error) {
      std::cerr << "FAIL " << test.first << ": " << error.what() << '\n'; result = 1; break;
    }
    std::cout << "PASS " << test.first << '\n';
    ++passed;
  }
  if (result == 0) std::cout << passed << " cases passed\n";
  if (!data_only) rclcpp::shutdown();
  return result;
}
