#include "pp_infer/point_policy.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <unordered_map>

namespace pp_infer {
void PointGrid::validate() const {
  if (!max_pillars || !max_per_pillar || !point_capacity)
    throw std::invalid_argument("Point policy capacities must be positive");
  for (std::size_t axis = 0; axis < 3; ++axis)
    if (!std::isfinite(lower[axis]) || !std::isfinite(upper[axis]) ||
        !(upper[axis] > lower[axis]))
      throw std::invalid_argument("Point policy requires finite increasing ROI bounds");
  for (std::size_t axis = 0; axis < 2; ++axis) {
    const float span = upper[axis] - lower[axis];
    const float cells = span / voxel_xy[axis];
    if (!std::isfinite(voxel_xy[axis]) || voxel_xy[axis] <= 0 ||
        !std::isfinite(cells) || cells >= 2147483648.0f)
      throw std::invalid_argument("Point policy grid arithmetic exceeds INT32 cells");
  }
}
PointPolicyCounts prepare_points(std::vector<float>& packed,
                                 PointPolicy policy, const PointGrid* grid) {
  if (packed.size() % 4) throw std::invalid_argument("Packed XYZI requires four floats per point");
  PointPolicyCounts counts;
  counts.input_points = packed.size() / 4;
  if (policy == PointPolicy::passthrough) {
    counts.retained_points = counts.input_points;
    return counts;
  }
  if (policy != PointPolicy::bounded || !grid)
    throw std::invalid_argument("Bounded point policy requires an explicit verified grid");
  grid->validate();
  std::unordered_map<std::uint64_t, std::size_t> pillars;
  pillars.reserve(std::min(grid->max_pillars, counts.input_points));
  std::vector<float> selected;
  selected.reserve(std::min(grid->point_capacity, counts.input_points) * 4);
  for (std::size_t offset = 0; offset < packed.size(); offset += 4) {
    const float* point = packed.data() + offset;
    if (!std::all_of(point, point + 4, [](float value) { return std::isfinite(value); })) {
      ++counts.nonfinite_points;
      continue;
    }
    if (point[0] == 0 && point[1] == 0 && point[2] == 0) {
      ++counts.zero_xyz_points;
      continue;
    }
    bool inside = true;
    for (std::size_t axis = 0; axis < 3; ++axis)
      inside = inside && point[axis] >= grid->lower[axis] && point[axis] < grid->upper[axis];
    if (!inside) { ++counts.out_of_range_points; continue; }
    // Separate float operations deliberately match the existing numpy float32
    // sensitivity control. Do not replace with double or reciprocal multiply.
    const float relative_x = point[0] - grid->lower[0];
    const float relative_y = point[1] - grid->lower[1];
    const auto x = static_cast<std::uint32_t>(std::floor(relative_x / grid->voxel_xy[0]));
    const auto y = static_cast<std::uint32_t>(std::floor(relative_y / grid->voxel_xy[1]));
    const auto key = (std::uint64_t(x) << 32) | y;
    auto entry = pillars.find(key);
    if (entry == pillars.end() && pillars.size() == grid->max_pillars) {
      ++counts.pillar_limit_points;
      continue;
    }
    if (entry != pillars.end() && entry->second == grid->max_per_pillar) {
      ++counts.per_pillar_limit_points;
      continue;
    }
    if (counts.retained_points == grid->point_capacity) {
      ++counts.point_limit_points;
      continue;
    }
    if (entry == pillars.end()) entry = pillars.emplace(key, 0).first;
    ++entry->second;
    // memcpy retains all four original float bit patterns, including signed zero.
    const auto start = selected.size();
    selected.resize(start + 4);
    std::memcpy(selected.data() + start, point, 4 * sizeof(float));
    ++counts.retained_points;
  }
  counts.retained_pillars = pillars.size();
  packed.swap(selected);
  return counts;
}
}  // namespace pp_infer
