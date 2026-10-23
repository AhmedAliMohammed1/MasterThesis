#include "pp_infer/detection_output.hpp"

#include <chrono>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <thread>

namespace {
void require(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}
void rejects(const std::function<void()>& action) {
  try { action(); } catch (const std::invalid_argument&) { return; }
  throw std::runtime_error("Expected invalid_argument");
}
const std::vector<std::string> classes{"Vehicle", "Pedestrian", "Cyclist"};
std::vector<Bndbox> boxes() {
  return {{1,2,3,4,5,6,0,0,0.25F}, {2,3,4,5,6,7,0.7F,1,0.5F}, {4,5,6,7,8,9,-0.2F,2,0.9F}};
}
std::map<std::string, std::string> fields(const diagnostic_msgs::msg::DiagnosticArray& message) {
  require(message.status.size() == 1, "Expected one diagnostic status");
  std::map<std::string, std::string> values;
  for (const auto& entry : message.status[0].values) values[entry.key] = entry.value;
  return values;
}
void wait_until(rclcpp::executors::SingleThreadedExecutor& executor, const std::function<bool()>& ready) {
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
  while (!ready()) {
    executor.spin_some();
    if (std::chrono::steady_clock::now() > deadline) throw std::runtime_error("ROS output discovery/delivery timed out");
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
}
}  // namespace

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  int result = 0;
  try {
    std_msgs::msg::Header header;
    header.frame_id = "lidar"; header.stamp.sec = 123;
    const auto all = pp_infer::make_detections(header, boxes(), classes, 0.0);
    const auto filtered = pp_infer::make_detections(header, boxes(), classes, 0.5);
    require(filtered.header == all.header && filtered.detections.size() == 2, "Score equality must pass");
    require(filtered.detections[0] == all.detections[1] && filtered.detections[1] == all.detections[2],
            "Kept detection fields/order changed");
    auto edges = boxes(); edges[0].score = 0; edges[1].score = 1;
    require(pp_infer::make_detections(header, edges, classes, 1).detections.size() == 1, "Threshold one failed");
    require(pp_infer::make_detections(header, edges, classes, 0).detections.size() == 3, "Threshold zero failed");
    require(pp_infer::make_detections(header, {}, classes, 0.5).detections.empty(), "Empty frame failed");
    for (double invalid : {-0.01, 1.01, std::numeric_limits<double>::quiet_NaN(),
                           std::numeric_limits<double>::infinity()})
      rejects([&] { pp_infer::make_detections(header, {}, classes, invalid); });
    auto invalid = boxes(); invalid[0].l = -1;
    rejects([&] { pp_infer::make_detections(header, invalid, classes, 1); });
    for (float score : {-0.1F, 1.1F, std::numeric_limits<float>::quiet_NaN()}) {
      invalid = boxes(); invalid[0].score = score;
      rejects([&] { pp_infer::make_detections(header, invalid, classes, 1); });
    }

    rclcpp::NodeOptions options;
    options.arguments({"--ros-args", "-r", "bbox:=/filter_test/boxes"}).use_global_arguments(false);
    auto node = std::make_shared<rclcpp::Node>("filter_test", options);
    pp_infer::DetectionOutput output(*node, classes);
    vision_msgs::msg::Detection3DArray::SharedPtr received;
    diagnostic_msgs::msg::DiagnosticArray::SharedPtr stats;
    visualization_msgs::msg::MarkerArray::SharedPtr marker;
    auto detection_sub = node->create_subscription<vision_msgs::msg::Detection3DArray>(
      "/filter_test/boxes", 10, [&](vision_msgs::msg::Detection3DArray::SharedPtr value) { received = value; });
    const auto qos = rclcpp::QoS(10).reliable().transient_local();
    auto stats_sub = node->create_subscription<diagnostic_msgs::msg::DiagnosticArray>(
      "/filter_test/boxes/stats", qos, [&](diagnostic_msgs::msg::DiagnosticArray::SharedPtr value) { stats = value; });
    auto count_sub = node->create_subscription<visualization_msgs::msg::MarkerArray>(
      "/filter_test/boxes/count", qos, [&](visualization_msgs::msg::MarkerArray::SharedPtr value) { marker = value; });
    rclcpp::executors::SingleThreadedExecutor executor;
    executor.add_node(node);
    wait_until(executor, [&] {
      return node->count_publishers("/filter_test/boxes") == 1 &&
             node->count_subscribers("/filter_test/boxes") == 1 &&
             node->count_subscribers("/filter_test/boxes/stats") == 1 &&
             node->count_subscribers("/filter_test/boxes/count") == 1;
    });
    // Discovery of the local graph precedes endpoint matching in some RMWs.
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    auto publish = [&](const std::vector<Bndbox>& candidates) {
      received.reset(); stats.reset(); marker.reset(); ++header.stamp.nanosec;
      output.publish(header, candidates);
      wait_until(executor, [&] {
        return received && stats && marker && received->header == header && stats->header == header &&
               marker->markers.size() == 1 && marker->markers[0].header == header;
      });
      require(fields(*stats)["published_count"] == std::to_string(received->detections.size()),
              "Stats do not match actual publication");
    };
    publish(boxes());
    require(*received == pp_infer::make_detections(header, boxes(), classes, 0.5),
            "Live filter/header output differs from adapter");
    auto values = fields(*stats);
    require(values["post_nms_count"] == "3" && values["filtered_count"] == "1" &&
            values["published_detections_total"] == "2", "Initial counts incorrect");
    require(marker->markers[0].text.find("2 boxes / 3") != std::string::npos, "RViz count mismatch");
    require(node->set_parameter(rclcpp::Parameter("confidence_threshold", 0.75)).successful,
            "Dynamic threshold update failed");
    publish(boxes());
    require(received->detections.size() == 1 && fields(*stats)["published_detections_total"] == "3",
            "Dynamic threshold not applied to next scan");
    for (double bad : {-0.01, 1.01, std::numeric_limits<double>::quiet_NaN(),
                        std::numeric_limits<double>::infinity()})
      require(!node->set_parameter(rclcpp::Parameter("confidence_threshold", bad)).successful,
              "Invalid threshold update accepted");
    require(node->get_parameter("confidence_threshold").as_double() == 0.75, "Rejected update changed threshold");
    try {
      require(!node->set_parameter(rclcpp::Parameter("confidence_threshold", 1)).successful,
              "Integer threshold update accepted");
    } catch (const rclcpp::exceptions::InvalidParameterTypeException&) {
      // Static ROS parameter typing may reject this before the local validator.
    }
    node->declare_parameter("reject_batch", false);
    auto veto = node->add_on_set_parameters_callback([](const std::vector<rclcpp::Parameter>& params) {
      rcl_interfaces::msg::SetParametersResult result; result.successful = true;
      for (const auto& p : params) if (p.get_name() == "reject_batch" && p.as_bool()) result.successful = false;
      return result;
    });
    require(!node->set_parameters_atomically({rclcpp::Parameter("confidence_threshold", 0.0),
              rclcpp::Parameter("reject_batch", true)}).successful, "Atomic veto failed");
    require(node->get_parameter("confidence_threshold").as_double() == 0.75, "Rejected atomic batch changed threshold");
    require(node->set_parameter(rclcpp::Parameter("confidence_threshold", 1.0)).successful, "Threshold one rejected");
    publish(boxes());
    require(received->detections.empty() && fields(*stats)["filtered_count"] == "3", "All-filtered frame retained boxes");
    publish({});
    require(fields(*stats)["post_nms_count"] == "0" && fields(*stats)["processed_frames_total"] == "4",
            "Valid empty frame not counted");
    require(node->set_parameter(rclcpp::Parameter("confidence_threshold", 0.0)).successful, "Threshold zero rejected");
    publish(boxes());
    require(received->detections.size() == 3 && fields(*stats)["published_detections_total"] == "6" &&
            fields(*stats)["filtered_detections_total"] == "6", "Cumulative totals or disabled gate incorrect");
    require(marker->markers[0].text.find("Total published: 6 | total removed: 6") != std::string::npos &&
            marker->markers[0].text.find("Processed frames: 5") != std::string::npos,
            "RViz cumulative totals do not match actual publications");
    for (auto failure : {pp_infer::FrameFailure::invalid_cloud, pp_infer::FrameFailure::inference_error}) {
      received.reset(); stats.reset(); marker.reset(); ++header.stamp.nanosec;
      output.report_failure(header, failure);
      wait_until(executor, [&] { return stats && marker && stats->header == header; });
      values = fields(*stats);
      require(!received && values["published_count"] == "unavailable" && values["processed_frames_total"] == "5" &&
              values["published_detections_total"] == "6", "Failed frame reported a successful empty detection");
      require(stats->status[0].level == diagnostic_msgs::msg::DiagnosticStatus::WARN &&
              marker->markers[0].text.find("unavailable") != std::string::npos, "Failure indicator missing");
    }
    require(values["invalid_cloud_frames_total"] == "1" && values["inference_error_frames_total"] == "1",
            "Frame failure counters incorrect");
    require(marker->markers[0].text.find("dropped input/inference: 1/1") != std::string::npos,
            "RViz dropped-frame counters incorrect");
    diagnostic_msgs::msg::DiagnosticArray::SharedPtr late_stats;
    auto late_sub = node->create_subscription<diagnostic_msgs::msg::DiagnosticArray>(
      "/filter_test/boxes/stats", qos,
      [&](diagnostic_msgs::msg::DiagnosticArray::SharedPtr value) { late_stats = value; });
    wait_until(executor, [&] { return late_stats != nullptr; });
    require(late_stats->header == header, "Late monitoring subscriber did not get latest state");
    for (double bad : {-0.1, 1.1, std::numeric_limits<double>::quiet_NaN()}) {
      rclcpp::NodeOptions override_options;
      override_options.parameter_overrides({rclcpp::Parameter("confidence_threshold", bad)});
      auto invalid_node = std::make_shared<rclcpp::Node>("invalid_threshold", override_options);
      rejects([&] { pp_infer::DetectionOutput invalid_output(*invalid_node, classes); });
    }
    std::cout << "PASS: boundary filtering, unchanged fields/headers, invalid results/settings, dynamic/atomic updates, "
                 "actual ROS remapping/publication, zero/empty frames, counts/totals, failure status and late subscribers\n";
  } catch (const std::exception& error) {
    std::cerr << "FAIL: " << error.what() << '\n'; result = 1;
  }
  rclcpp::shutdown();
  return result;
}
