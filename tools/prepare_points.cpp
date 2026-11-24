// Standalone CPU diagnostic preparation. Never selected by ROS launchers.
#include "pp_infer/point_policy.hpp"
#include <cstdio>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

namespace {
float number(const char* text) {
  std::size_t end{}; const auto result = std::stof(text, &end);
  if (text[end] != '\0') throw std::invalid_argument("Invalid grid number");
  return result;
}
std::size_t capacity(const char* text) {
  const std::string value(text);
  if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
    throw std::invalid_argument("Capacity must be a positive integer");
  std::size_t end{}; const auto result = std::stoull(value, &end);
  if (!result || result > std::numeric_limits<std::size_t>::max())
    throw std::invalid_argument("Capacity out of range");
  return static_cast<std::size_t>(result);
}
}
int main(int argc, char** argv) {
  try {
    if (argc != 15) {
      std::cerr << "Usage: pp_prepare_points INPUT.bin NEW_OUTPUT.bin "
        "passthrough|bounded xmin ymin zmin xmax ymax zmax voxel_x voxel_y "
        "max_pillars max_per_pillar point_capacity\n"
        "Native-endian FLOAT32 XYZI. Caller must verify explicit model grid. "
        "Output must not exist. This is an offline diagnostic, not a ROS setting.\n";
      return 2;
    }
    const std::string mode(argv[3]);
    if (mode != "passthrough" && mode != "bounded")
      throw std::invalid_argument("Policy must be passthrough or bounded");
    pp_infer::PointGrid grid{{number(argv[4]), number(argv[5]), number(argv[6])},
      {number(argv[7]), number(argv[8]), number(argv[9])},
      {number(argv[10]), number(argv[11])}, capacity(argv[12]), capacity(argv[13]), capacity(argv[14])};
    std::ifstream input(argv[1], std::ios::binary | std::ios::ate);
    if (!input) throw std::runtime_error("Cannot open input");
    const auto size = input.tellg();
    if (size < 0 || size % (4*sizeof(float)) != 0 || size > (std::streamoff(1) << 30))
      throw std::invalid_argument("Input requires packed XYZI and at most 1 GiB");
    std::vector<float> points(static_cast<std::size_t>(size) / sizeof(float));
    input.seekg(0);
    if (size && !input.read(reinterpret_cast<char*>(points.data()), size))
      throw std::runtime_error("Incomplete input read");
    const auto counts = pp_infer::prepare_points(points,
      mode == "bounded" ? pp_infer::PointPolicy::bounded : pp_infer::PointPolicy::passthrough,
      &grid);
    // Exclusive creation protects original artifacts, including concurrent use.
    std::FILE* output = std::fopen(argv[2], "wbx");
    if (!output) throw std::runtime_error("Cannot create output exclusively; choose a new writable path");
    const auto written = std::fwrite(points.data(), sizeof(float), points.size(), output);
    const auto closed = std::fclose(output);
    if (written != points.size() || closed != 0) {
      std::remove(argv[2]);  // Only the file exclusively created by this process.
      throw std::runtime_error("Output write failed; incomplete file removed");
    }
    std::cout << "{\"policy\":\"" << mode << "\",\"input_points\":" << counts.input_points
      << ",\"retained_points\":" << counts.retained_points;
    if (mode == "bounded") {
      std::cout << ",\"nonfinite_points\":" << counts.nonfinite_points
        << ",\"zero_xyz_points\":" << counts.zero_xyz_points
        << ",\"out_of_range_points\":" << counts.out_of_range_points
        << ",\"pillar_limit_points\":" << counts.pillar_limit_points
        << ",\"per_pillar_limit_points\":" << counts.per_pillar_limit_points
        << ",\"point_limit_points\":" << counts.point_limit_points
        << ",\"retained_pillars\":" << counts.retained_pillars;
    }
    std::cout << "}\n";
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n'; return 1;
  }
}
