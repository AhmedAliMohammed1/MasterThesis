#include "pp_infer/ouster_adapter.hpp"
#include <iostream>

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  int result = 0;
  try { rclcpp::spin(pp_infer::make_ouster_adapter()); }
  catch (const std::exception& error) {
    std::cerr << "Ouster adapter failed: " << error.what() << '\n';
    result = 1;
  }
  rclcpp::shutdown();
  return result;
}
