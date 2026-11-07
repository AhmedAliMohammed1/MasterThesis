// Binary-stream probe for recorded bag checks, using the production converter
// and detector packer without DDS, an engine, CUDA or a GPU.
#include "pp_infer/ouster_adapter.hpp"
#include "pp_infer/ros_adapter.hpp"
#include <rclcpp/serialization.hpp>
#include <cstring>
#include <iostream>

int main(int argc, char** argv) {
  if (argc != 3) {
    std::cerr << "Usage: ouster_adapter_probe signal|reflectivity divisor\n";
    return 2;
  }
  std::size_t frame = 0;
  try {
    std::size_t used = 0;
    const double divisor = std::stod(argv[2], &used);
    if (used != std::strlen(argv[2])) throw std::invalid_argument("Invalid divisor");
    const pp_infer::InputLimits limits{204800, 67108864, divisor};
    limits.validate();
    rclcpp::Serialization<sensor_msgs::msg::PointCloud2> serialization;
    pcl::PointCloud<pcl::PointXYZI> scratch;
    std::vector<float> packed;
    while (true) {
      std::uint32_t size = 0;
      std::cin.read(reinterpret_cast<char*>(&size), sizeof(size));
      if (std::cin.eof() && std::cin.gcount() == 0) break;
      if (!std::cin || size == 0 || size > limits.maximum_cloud_bytes + 65536)
        throw std::invalid_argument("Invalid/truncated CDR frame size");
      rclcpp::SerializedMessage input(size);
      auto& buffer = input.get_rcl_serialized_message();
      std::cin.read(reinterpret_cast<char*>(buffer.buffer), size);
      if (!std::cin) throw std::invalid_argument("Truncated CDR payload");
      buffer.buffer_length = size;
      sensor_msgs::msg::PointCloud2 message;
      serialization.deserialize_message(&input, &message);
      const auto output = pp_infer::ouster_to_xyzi(message, argv[1], limits);
      const std::uint32_t valid = pp_infer::pack_xyzi(output,
        {limits.point_capacity, limits.maximum_cloud_bytes, 1.0}, scratch, packed);
      rclcpp::SerializedMessage serialized;
      serialization.serialize_message(&output, &serialized);
      const auto& result = serialized.get_rcl_serialized_message();
      const std::uint32_t result_size = result.buffer_length;
      std::cout.write(reinterpret_cast<const char*>(&result_size), 4);
      std::cout.write(reinterpret_cast<const char*>(&valid), 4);
      std::cout.write(reinterpret_cast<const char*>(result.buffer), result_size);
      std::cout.flush();
      if (!std::cout) throw std::runtime_error("Output stream failed");
      ++frame;
    }
  } catch (const std::exception& error) {
    std::cerr << "Bag probe failed at frame " << frame << ": " << error.what() << '\n';
    return 1;
  }
  return 0;
}
