#pragma once
#include "model_contract.hpp"
#include "postprocess.h"
#include <cstdint>
#include <vector>

namespace pp_infer {
inline std::size_t checked_detection_count(std::int32_t count, std::size_t capacity) {
  if (count < 0 || static_cast<std::size_t>(count) > capacity)
    throw std::runtime_error("Output count outside engine capacity");
  return static_cast<std::size_t>(count);
}
// Decode only completed host results. Every row must satisfy the deployment
// contract before any detections are returned to the caller.
inline std::vector<Bndbox> decode_boxes(const float* rows, std::size_t count, std::size_t classes) {
  if (!classes || (count && !rows)) throw std::invalid_argument("Invalid output storage/classes");
  checked_product(count, 9);
  std::vector<Bndbox> result;
  result.reserve(count);
  for (std::size_t i = 0; i < count; ++i) {
    const float* row = rows + i * 9;
    if (!std::isfinite(row[7]) || row[7] < 0 || std::floor(row[7]) != row[7] ||
        static_cast<double>(row[7]) >= static_cast<double>(classes) ||
        static_cast<double>(row[7]) > std::numeric_limits<int>::max())
      throw std::runtime_error("Invalid output class index");
    Bndbox box(row[0], row[1], row[2], row[3], row[4], row[5], row[6], static_cast<int>(row[7]), row[8]);
    if (!valid_box(box) || !std::isfinite(box.score)) throw std::runtime_error("Invalid output box");
    result.push_back(box);
  }
  return result;
}
}  // namespace pp_infer
