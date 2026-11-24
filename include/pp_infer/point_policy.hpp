#pragma once

#include <array>
#include <cstddef>
#include <vector>

namespace pp_infer {
// Explicit diagnostic policy. No model-specific defaults are inferred from an
// engine's point tensor shape. The caller must verify this grid against export.
struct PointGrid {
  std::array<float, 3> lower, upper;
  std::array<float, 2> voxel_xy;
  std::size_t max_pillars, max_per_pillar, point_capacity;
  void validate() const;
};
enum class PointPolicy { passthrough, bounded };
// Classification and retained_pillars are populated only for bounded mode.
// Passthrough reports only input/retained counts; it does not audit the grid.
struct PointPolicyCounts {
  std::size_t input_points{}, nonfinite_points{}, zero_xyz_points{};
  std::size_t out_of_range_points{}, pillar_limit_points{}, per_pillar_limit_points{};
  std::size_t point_limit_points{}, retained_points{}, retained_pillars{};
};
// Stable first-encountered pillars/points, float32 grid arithmetic. Neither
// source coordinates nor feature bits are recalculated. This is not CUDA thread
// encounter order and is not an accuracy calibration. Passthrough is unchanged,
// including nonfinite/zero points, and does not inspect grid configuration.
// Invalid layout/configuration leaves packed unchanged.
PointPolicyCounts prepare_points(std::vector<float>& packed,
    PointPolicy policy = PointPolicy::passthrough, const PointGrid* grid = nullptr);
}  // namespace pp_infer
