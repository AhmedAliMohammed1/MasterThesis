#include "pp_infer/postprocess.h"

#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <random>
#include <stdexcept>
#include <vector>

namespace {
void require(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}
void near(double actual, double expected, double tolerance = 1e-6) {
  require(std::isfinite(actual) && std::abs(actual - expected) <= tolerance, "Unexpected IoU");
}
Bndbox box(float x = 0, float y = 0, float l = 2, float w = 2,
           float yaw = 0, int id = 0, float score = 0.9F) {
  return {x, y, 0, l, w, 2, yaw, id, score};
}
void rejects(const std::function<void()>& action) {
  try { action(); } catch (const std::invalid_argument&) { return; }
  throw std::runtime_error("Expected invalid_argument");
}
}  // namespace

int main() {
  const std::vector<std::pair<const char*, std::function<void()>>> tests = {
    {"identical and disjoint", [] {
      near(rotated_bev_iou(box(), box()), 1);
      near(rotated_bev_iou(box(), box(10)), 0);
    }},
    {"touching edge and corner", [] {
      near(rotated_bev_iou(box(), box(2)), 0);
      near(rotated_bev_iou(box(), box(2, 2)), 0);
    }},
    {"known partial overlap", [] { near(rotated_bev_iou(box(), box(1)), 1.0 / 3); }},
    {"containment", [] { near(rotated_bev_iou(box(), box(0, 0, 1, 1)), 0.25); }},
    {"45 degree square", [] {
      near(rotated_bev_iou(box(), box(0, 0, 2, 2, 0.785398163F)), std::sqrt(0.5));
    }},
    {"90 degree rectangle", [] {
      near(rotated_bev_iou(box(0, 0, 4, 2), box(0, 0, 4, 2, 1.570796327F)), 1.0 / 3);
    }},
    {"invalid geometry", [] {
      near(rotated_bev_iou(box(), box(0, 0, 0)), 0);
      near(rotated_bev_iou(box(), box(0, 0, -2)), 0);
      auto invalid = box(); invalid.rt = std::numeric_limits<float>::quiet_NaN();
      near(rotated_bev_iou(box(), invalid), 0);
      require(!valid_box(Bndbox{}), "Default box must be safely invalid");
    }},
    {"extreme coordinates", [] {
      near(rotated_bev_iou(box(), box(std::numeric_limits<float>::max())), 0);
      const auto large = box(1e10F, -1e10F, 4, 2, 0.2F);
      near(rotated_bev_iou(large, large), 1);
    }},
    {"NMS replaces stale output and handles empty input", [] {
      std::vector<Bndbox> out{box()};
      nms_cpu({}, 0.1F, out, 10);
      require(out.empty(), "Stale output survives empty frame");
    }},
    {"score ranking and top-k", [] {
      std::vector<Bndbox> out;
      nms_cpu({box(10, 0, 2, 2, 0, 0, 0.3F), box(0), box(20, 0, 2, 2, 0, 0, 0.7F)}, 0.1F, out, 2);
      require(out.size() == 2 && out[0].x == 0 && out[1].x == 20, "Incorrect top-k order");
    }},
    {"same-class versus cross-class suppression", [] {
      std::vector<Bndbox> out;
      const std::vector<Bndbox> candidates{box(), box(0, 0, 2, 2, 0, 1, 0.8F), box(0, 0, 2, 2, 0, 0, 0.7F)};
      nms_cpu(candidates, 0.1F, out, 10, true);
      require(out.size() == 2 && out[1].id == 1, "Class-aware suppression failed");
      nms_cpu(candidates, 0.1F, out, 10);
      require(out.size() == 1, "Legacy default must stay class-agnostic");
    }},
    {"equal scores are stable", [] {
      std::vector<Bndbox> out;
      nms_cpu({box(10), box(20), box(30)}, 0.1F, out, 2);
      require(out.size() == 2 && out[0].x == 10 && out[1].x == 20, "Unstable score ties");
    }},
    {"invalid settings and candidates clear output", [] {
      std::vector<Bndbox> out{box()};
      rejects([&] { nms_cpu({box()}, 0.1F, out, -1); });
      require(out.empty(), "Invalid top-k retained stale output");
      rejects([&] { nms_cpu({}, 0.1F, out, 0); });
      rejects([&] { nms_cpu({}, -0.1F, out, 1); });
      rejects([&] { nms_cpu({}, 1.1F, out, 1); });
      rejects([&] { nms_cpu({}, std::numeric_limits<float>::quiet_NaN(), out, 1); });
      auto invalid = box(); invalid.score = std::numeric_limits<float>::infinity();
      rejects([&] { nms_cpu({invalid}, 0.1F, out, 1); });
      invalid = box(); invalid.id = -1;
      rejects([&] { nms_cpu({invalid}, 0.1F, out, 1); });
    }},
    {"threshold boundaries preserve legacy comparison", [] {
      std::vector<Bndbox> out;
      nms_cpu({box(), box()}, 1, out, 10);
      require(out.size() == 1, "Expected >= threshold rule at one");
      nms_cpu({box(), box(10)}, 0, out, 10);
      require(out.size() == 1, "Expected legacy zero-threshold behavior");
    }},
    {"randomized symmetry range and self overlap", [] {
      std::mt19937 rng(42);
      std::uniform_real_distribution<float> position(-10, 10), size(0.1F, 8), yaw(-3.14F, 3.14F);
      for (int i = 0; i < 2000; ++i) {
        const auto a = box(position(rng), position(rng), size(rng), size(rng), yaw(rng));
        const auto b = box(position(rng), position(rng), size(rng), size(rng), yaw(rng));
        const double overlap = rotated_bev_iou(a, b);
        require(std::isfinite(overlap) && overlap >= 0 && overlap <= 1, "Invalid IoU range");
        near(overlap, rotated_bev_iou(b, a));
        near(rotated_bev_iou(a, a), 1);
      }
    }}
  };
  for (const auto& test : tests) {
    try { test.second(); }
    catch (const std::exception& error) {
      std::cerr << "FAIL " << test.first << ": " << error.what() << '\n'; return 1;
    }
    std::cout << "PASS " << test.first << '\n';
  }
  std::cout << tests.size() << " cases passed\n";
}
