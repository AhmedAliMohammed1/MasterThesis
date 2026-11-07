#include "pp_infer/ouster_adapter.hpp"
#include "pp_infer/ros_adapter.hpp"
#include <diagnostic_msgs/msg/diagnostic_array.hpp>
#include <chrono>
#include <cstring>
#include <functional>
#include <iostream>
#include <thread>

namespace {
using Cloud = sensor_msgs::msg::PointCloud2;
using Field = sensor_msgs::msg::PointField;
void require(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}
void rejects(const std::function<void()>& action) {
  try { action(); } catch (const std::invalid_argument&) { return; }
  throw std::runtime_error("Expected invalid_argument");
}
Cloud fixture() {
  Cloud msg;
  msg.header.frame_id = "ouster_sensor";
  msg.header.stamp.sec = 12; msg.header.stamp.nanosec = 345;
  msg.width = 2; msg.height = 2; msg.point_step = 48; msg.row_step = 104;
  msg.is_dense = true;
  for (const auto& name : {"x", "y", "z", "signal", "reflectivity", "ring"}) {
    Field field; field.name = name; field.count = 1;
    if (field.name == "x") { field.offset = 0; field.datatype = Field::FLOAT32; }
    if (field.name == "y") { field.offset = 4; field.datatype = Field::FLOAT32; }
    if (field.name == "z") { field.offset = 8; field.datatype = Field::FLOAT32; }
    if (field.name == "signal") { field.offset = 28; field.datatype = Field::UINT16; }
    if (field.name == "reflectivity") { field.offset = 32; field.datatype = Field::UINT8; }
    if (field.name == "ring") { field.offset = 20; field.datatype = Field::UINT16; }
    msg.fields.push_back(field);
  }
  msg.data.assign(208, 0xee);
  for (unsigned row = 0; row < 2; ++row) for (unsigned col = 0; col < 2; ++col) {
    auto* p = msg.data.data() + row * msg.row_step + col * msg.point_step;
    const float xyz[]{static_cast<float>(row * 2 + col), -2, 3};
    const std::uint16_t signal = row == 0 ? 0 : 65535;
    std::memcpy(p, xyz, 12); std::memcpy(p + 28, &signal, 2);
    p[32] = col == 0 ? 0 : 255;
  }
  return msg;
}
float value(const Cloud& msg, std::size_t index, std::size_t component) {
  float result;
  std::memcpy(&result, msg.data.data() + index * 16 + component * 4, 4);
  return result;
}
void data_tests() {
  const auto msg = fixture();
  const auto original = msg;
  const auto reflectivity = pp_infer::ouster_to_xyzi(msg, "reflectivity", {4, 208, 255});
  require(msg == original, "Source mutated");
  require(reflectivity.header == msg.header && reflectivity.width == 2 && reflectivity.height == 2,
          "Header or organization changed");
  require(reflectivity.point_step == 16 && reflectivity.row_step == 32 && reflectivity.data.size() == 64,
          "Wrong compact layout");
  require(reflectivity.fields[3].name == "intensity" && reflectivity.fields[3].datatype == Field::FLOAT32,
          "Missing FLOAT32 intensity");
  require(value(reflectivity, 0, 3) == 0 && value(reflectivity, 3, 3) == 1 &&
          value(reflectivity, 2, 0) == 2 && value(reflectivity, 3, 1) == -2, "Padding/conversion mismatch");
  const auto signal = pp_infer::ouster_to_xyzi(msg, "signal", {4, 208, 65535});
  require(value(signal, 0, 3) == 0 && value(signal, 2, 3) == 1, "UINT16 signal conversion failed");
  require(value(pp_infer::ouster_to_xyzi(msg, "signal", {4, 208, 1}), 2, 3) == 65535,
          "Raw numeric conversion failed");
  pcl::PointCloud<pcl::PointXYZI> scratch;
  std::vector<float> packed;
  require(pp_infer::pack_xyzi(reflectivity, {4, 208, 1}, scratch, packed) == 4 && packed[15] == 1,
          "Output incompatible with actual detector adapter");
  auto bad = msg; const float nan = std::numeric_limits<float>::quiet_NaN();
  std::memcpy(bad.data.data(), &nan, 4);
  const auto nonfinite = pp_infer::ouster_to_xyzi(bad, "reflectivity", {4, 208, 255});
  require(!nonfinite.is_dense && pp_infer::pack_xyzi(nonfinite, {4, 208, 1}, scratch, packed) == 3,
          "Nonfinite XYZ handling changed");
  for (const auto& mutation : std::vector<std::function<void(Cloud&)>>{
      [](Cloud& c) { c.fields.erase(c.fields.begin() + 4); },
      [](Cloud& c) { c.fields.push_back(c.fields[4]); },
      [](Cloud& c) { c.fields[4].count = 2; },
      [](Cloud& c) { c.fields[4].datatype = Field::INT8; },
      [](Cloud& c) { c.fields[0].datatype = Field::UINT32; },
      [](Cloud& c) { c.fields[4].offset = 48; },
      [](Cloud& c) { c.fields[4].offset = 1; },
      [](Cloud& c) { c.point_step = 0; },
      [](Cloud& c) { c.is_bigendian = true; },
      [](Cloud& c) { c.row_step = 1; },
      [](Cloud& c) { c.data.pop_back(); }}) {
    bad = msg; mutation(bad);
    rejects([&] { pp_infer::ouster_to_xyzi(bad, "reflectivity", {4, 208, 255}); });
  }
  for (double divisor : {0.0, -1.0, std::numeric_limits<double>::infinity(), 1e-300})
    rejects([&] { pp_infer::ouster_to_xyzi(msg, "reflectivity", {4, 208, divisor}); });
  rejects([&] { pp_infer::ouster_to_xyzi(msg, "reflectivity", {3, 208, 255}); });
  rejects([&] { pp_infer::ouster_to_xyzi(msg, "reflectivity", {4, 207, 255}); });
  rejects([&] { pp_infer::ouster_to_xyzi(msg, "automatic", {4, 208, 255}); });
  bad = msg; bad.fields[4].datatype = Field::UINT16;
  const std::uint16_t code = 120;
  std::memcpy(bad.data.data() + 32, &code, 2);
  require(std::abs(value(pp_infer::ouster_to_xyzi(bad, "reflectivity", {4, 208, 255}), 0, 3) - 120.F/255) < 1e-6,
          "Legacy UINT16 reflectivity failed");
  bad.fields[4].datatype = Field::FLOAT32;
  const float fraction = 127.5F;
  // FLOAT32 fields can be unaligned in source data; memcpy must handle this.
  bad.fields[4].offset = 33;
  std::memcpy(bad.data.data() + 33, &fraction, 4);
  // Give every point a valid float channel before converting the whole scan.
  for (unsigned row = 0; row < 2; ++row) for (unsigned col = 0; col < 2; ++col)
    std::memcpy(bad.data.data() + row * bad.row_step + col * bad.point_step + 33, &fraction, 4);
  require(value(pp_infer::ouster_to_xyzi(bad, "reflectivity", {4, 208, 255}), 0, 3) == 0.5F,
          "Unaligned FLOAT32 conversion failed");
  bad.fields[4].offset = 32;
  std::memcpy(bad.data.data() + 32, &nan, 4);
  rejects([&] { pp_infer::ouster_to_xyzi(bad, "reflectivity", {4, 208, 255}); });
  const float negative = -1;
  std::memcpy(bad.data.data() + 32, &negative, 4);
  rejects([&] { pp_infer::ouster_to_xyzi(bad, "reflectivity", {4, 208, 255}); });
  auto empty = msg; empty.width = 0; empty.row_step = 0; empty.data.clear();
  require(pp_infer::ouster_to_xyzi(empty, "signal", {4, 208, 1}).data.empty(), "Empty cloud failed");
  std::cout << "PASS Ouster conversions, detector packing, preservation and rejection controls\n";
}
void transport_tests() {
  rclcpp::NodeOptions options;
  options.parameter_overrides({rclcpp::Parameter("input_topic", "/ouster_adapter_test/raw"),
                              rclcpp::Parameter("output_topic", "/ouster_adapter_test/xyzi")});
  auto adapter = pp_infer::make_ouster_adapter(options);
  auto probe = std::make_shared<rclcpp::Node>("ouster_probe");
  auto pub = probe->create_publisher<Cloud>("/ouster_adapter_test/raw", rclcpp::SensorDataQoS());
  Cloud output;
  int outputs = 0;
  auto sub = probe->create_subscription<Cloud>("/ouster_adapter_test/xyzi", rclcpp::QoS(5).reliable(),
    [&](Cloud::ConstSharedPtr msg) { output = *msg; ++outputs; });
  bool rejected = false;
  auto stats = probe->create_subscription<diagnostic_msgs::msg::DiagnosticArray>("/ouster_adapter/stats", 5,
    [&](diagnostic_msgs::msg::DiagnosticArray::ConstSharedPtr msg) {
      for (const auto& status : msg->status) for (const auto& item : status.values)
        if (item.key == "rejected" && item.value != "0") rejected = true;
    });
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(adapter); executor.add_node(probe);
  auto until = [&](const std::function<bool()>& predicate) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(6);
    while (!predicate() && std::chrono::steady_clock::now() < deadline) {
      executor.spin_some(); std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    require(predicate(), "ROS transport timed out");
  };
  until([&] { return pub->get_subscription_count() == 1 && sub->get_publisher_count() == 1; });
  pub->publish(fixture());
  until([&] { return outputs == 1; });
  require(output.header == fixture().header && value(output, 3, 3) == 1, "Transport output mismatch");
  auto bad = fixture(); bad.fields.erase(bad.fields.begin() + 4);
  pub->publish(bad);
  until([&] { return rejected; });
  require(outputs == 1, "Rejected cloud was published");
  pub->publish(fixture());
  until([&] { return outputs == 2; });
  require(!adapter->set_parameter(rclcpp::Parameter("intensity_divisor", 1.0)).successful,
          "Conversion parameter changed at runtime");
  options.parameter_overrides({rclcpp::Parameter("input_topic", "/same"),
                              rclcpp::Parameter("output_topic", "/same")});
  rejects([&] { pp_infer::make_ouster_adapter(options); });
  options.parameter_overrides({rclcpp::Parameter("intensity_source", "auto")});
  rejects([&] { pp_infer::make_ouster_adapter(options); });
  options.parameter_overrides({rclcpp::Parameter("intensity_divisor", 0.0)});
  rejects([&] { pp_infer::make_ouster_adapter(options); });
  options.parameter_overrides({rclcpp::Parameter("input_topic", "/before_remap"),
                              rclcpp::Parameter("output_topic", "/after_remap")});
  options.arguments({"--ros-args", "-r", "/before_remap:=/after_remap"});
  rejects([&] { pp_infer::make_ouster_adapter(options); });
  std::cout << "PASS best-effort input -> adapter -> reliable output, diagnostics and recovery\n";
}
}  // namespace
int main(int argc, char** argv) {
  const bool transport = argc > 1 && std::string(argv[1]) == "--transport-only";
  if (transport) rclcpp::init(argc, argv);
  int result = 0;
  try { if (transport) transport_tests(); else data_tests(); }
  catch (const std::exception& error) { std::cerr << "FAIL " << error.what() << '\n'; result = 1; }
  if (transport) rclcpp::shutdown();
  return result;
}
