#include "pp_infer/output_contract.hpp"
#include <array>
#include <iostream>
#include <limits>
#include <stdexcept>

template<class F> void rejects(F action) {
  try { action(); } catch (const std::exception&) { return; }
  throw std::runtime_error("Expected rejection");
}
int main() {
  using namespace pp_infer;
  rejects([] { checked_detection_count(-1, 10); });
  rejects([] { checked_detection_count(11, 10); });
  if (checked_detection_count(10, 10) != 10 || checked_detection_count(0, 0) != 0) return 1;
  std::array<float, 18> rows{1, 2, 3, 4, 2, 1, 0.5f, 1, 0.9f,
                           2, 3, 4, 4, 2, 1, 0, 0, 0.8f};
  const auto boxes = decode_boxes(rows.data(), 2, 2);
  if (boxes.size() != 2 || boxes[0].id != 1 || boxes[0].l != 4 || boxes[0].score != 0.9f) return 1;
  for (const float bad : {-1.f, 0.5f, 2.f, 2147483648.f, std::numeric_limits<float>::quiet_NaN()}) {
    rows[16] = bad;
    rejects([&] { decode_boxes(rows.data(), 2, 2); });
  }
  rows[16] = 0;
  rows[12] = 0;
  rejects([&] { decode_boxes(rows.data(), 2, 2); });
  rows[12] = 4;
  rows[17] = std::numeric_limits<float>::infinity();
  rejects([&] { decode_boxes(rows.data(), 2, 2); });
  rejects([] { decode_boxes(nullptr, 1, 2); });
  rejects([] { decode_boxes(nullptr, 0, 0); });
  if (!decode_boxes(nullptr, 0, 2).empty()) return 1;
  std::cout << "Output count, class, geometry, score and empty-result contract passed\n";
}
