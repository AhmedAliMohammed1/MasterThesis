#pragma once

#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>

namespace pp_infer {
inline std::size_t checked_product(std::size_t a, std::size_t b) {
  if (b != 0 && a > std::numeric_limits<std::size_t>::max() / b)
    throw std::invalid_argument("Size multiplication overflow");
  return a * b;
}

// Operational input limits. Actual engine capacity/normalization must come from
// the inspected model contract; fixtures may supply explicit test values.
struct InputLimits {
  std::size_t point_capacity;
  std::size_t maximum_cloud_bytes;
  double intensity_scale;
  void validate() const {
    if (point_capacity == 0 || maximum_cloud_bytes == 0 ||
        !std::isfinite(intensity_scale) || intensity_scale <= 0)
      throw std::invalid_argument("Input limits require positive capacities and finite positive intensity scale");
    checked_product(point_capacity, 4 * sizeof(float));
  }
};
}  // namespace pp_infer
