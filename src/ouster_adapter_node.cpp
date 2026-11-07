#include "pp_infer/ouster_adapter.hpp"
#include <diagnostic_msgs/msg/diagnostic_array.hpp>
#include <rcl_interfaces/msg/parameter_descriptor.hpp>
#include <chrono>
#include <sstream>

namespace pp_infer {
namespace {
class OusterAdapter : public rclcpp::Node {
public:
  explicit OusterAdapter(const rclcpp::NodeOptions& options) : Node("ouster_adapter", options) {
    rcl_interfaces::msg::ParameterDescriptor immutable;
    immutable.read_only = true;
    const auto input = declare_parameter<std::string>("input_topic", "/ouster1/points", immutable);
    const auto output = declare_parameter<std::string>("output_topic", "/point_cloud", immutable);
    source_ = declare_parameter<std::string>("intensity_source", "reflectivity", immutable);
    limits_.intensity_scale = declare_parameter<double>("intensity_divisor", 255.0, immutable);
    const auto points = declare_parameter<std::int64_t>("max_points", 204800, immutable);
    const auto bytes = declare_parameter<std::int64_t>("max_cloud_bytes", 67108864, immutable);
    if (points <= 0 || bytes <= 0 ||
        static_cast<std::uint64_t>(points) > std::numeric_limits<std::size_t>::max() ||
        static_cast<std::uint64_t>(bytes) > std::numeric_limits<std::size_t>::max() ||
        (source_ != "signal" && source_ != "reflectivity"))
      throw std::invalid_argument("Invalid Ouster capacities or intensity_source");
    limits_.point_capacity = static_cast<std::size_t>(points);
    limits_.maximum_cloud_bytes = static_cast<std::size_t>(bytes);
    limits_.validate();
    // Resolve remaps before checking, so configuration cannot create a feedback loop.
    input_ = get_node_topics_interface()->resolve_topic_name(input);
    output_ = get_node_topics_interface()->resolve_topic_name(output);
    if (input_ == output_) throw std::invalid_argument("Ouster input/output topics must differ");
    // Pass original names to rclcpp so remapping is applied exactly once.
    publisher_ = create_publisher<sensor_msgs::msg::PointCloud2>(output, rclcpp::QoS(5).reliable());
    stats_ = create_publisher<diagnostic_msgs::msg::DiagnosticArray>("~/stats", 5);
    subscription_ = create_subscription<sensor_msgs::msg::PointCloud2>(input, rclcpp::SensorDataQoS(),
      [this](const sensor_msgs::msg::PointCloud2::ConstSharedPtr msg) {
        ++received_;
        try {
          auto adapted = ouster_to_xyzi(*msg, source_, limits_);
          publisher_->publish(adapted);
          ++converted_;
          last_error_.clear();
          std::ostringstream schema;
          schema << msg->width << 'x' << msg->height << " point_step=" << msg->point_step;
          for (const auto& f : msg->fields)
            schema << ' ' << f.name << "(type=" << unsigned(f.datatype) << ",offset=" << f.offset
                   << ",count=" << f.count << ')';
          if (schema.str() != schema_) {
            schema_ = schema.str();
            RCLCPP_INFO(get_logger(), "Accepted Ouster schema: %s", schema_.c_str());
          }
        } catch (const std::exception& error) {
          ++rejected_;
          last_error_ = error.what();
          RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 5000, "Rejected Ouster cloud: %s", error.what());
        }
      });
    timer_ = create_wall_timer(std::chrono::seconds(2), [this] { inspect(); });
    RCLCPP_INFO(get_logger(), "%s -> %s; intensity = %s / %.9g. Input best effort; output reliable.",
      input_.c_str(), output_.c_str(), source_.c_str(), limits_.intensity_scale);
  }
private:
  void inspect() {
    std::ostringstream candidates;
    for (const auto& topic : get_topic_names_and_types()) {
      if (topic.first == output_ || count_publishers(topic.first) == 0) continue;
      for (const auto& type : topic.second)
        if (type == "sensor_msgs/msg/PointCloud2") candidates << topic.first << ' ';
    }
    if (candidates.str() != candidates_) {
      candidates_ = candidates.str();
      RCLCPP_INFO(get_logger(), "Discovered PointCloud2 topics: %s", candidates_.c_str());
    }
    const bool fresh = received_ != previous_received_;
    previous_received_ = received_;
    diagnostic_msgs::msg::DiagnosticArray message;
    message.header.stamp = now();
    diagnostic_msgs::msg::DiagnosticStatus status;
    status.name = std::string(get_fully_qualified_name()) + ": input";
    status.hardware_id = input_;
    status.level = !last_error_.empty() ? status.ERROR : (!fresh ? status.WARN : status.OK);
    status.message = !last_error_.empty() ? last_error_ : (!fresh ? "Waiting for incoming clouds" : "Converting clouds");
    auto add = [&](const std::string& key, const std::string& value) {
      diagnostic_msgs::msg::KeyValue item;
      item.key = key; item.value = value; status.values.push_back(item);
    };
    add("input_topic", input_); add("output_topic", output_);
    add("input_publishers", std::to_string(count_publishers(input_)));
    add("intensity_source", source_); add("intensity_divisor", std::to_string(limits_.intensity_scale));
    add("received", std::to_string(received_)); add("converted", std::to_string(converted_));
    add("rejected", std::to_string(rejected_)); add("schema", schema_);
    add("pointcloud_topics", candidates_);
    message.status.push_back(status);
    stats_->publish(message);
    if (!fresh) RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 10000,
      "No recent clouds on %s. Check topic/type, ROS domain and middleware. Candidates: %s",
      input_.c_str(), candidates_.c_str());
  }
  InputLimits limits_{};
  std::string source_, input_, output_, schema_, candidates_, last_error_;
  std::uint64_t received_{0}, converted_{0}, rejected_{0}, previous_received_{0};
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr publisher_;
  rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr stats_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr subscription_;
  rclcpp::TimerBase::SharedPtr timer_;
};
}  // namespace
rclcpp::Node::SharedPtr make_ouster_adapter(const rclcpp::NodeOptions& options) {
  return std::make_shared<OusterAdapter>(options);
}
}  // namespace pp_infer
