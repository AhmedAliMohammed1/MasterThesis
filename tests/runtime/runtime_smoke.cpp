#include "pp_infer/pointpillar.h"
#include <iostream>
#include <stdexcept>
#include <vector>

// Synthetic resource/API smoke check, not model accuracy evidence.
int main(int argc, char** argv) {
  if (argc != 2) { std::cerr << "usage: runtime_smoke ENGINE\n"; return 2; }
  try {
    PointPillar runtime(argv[1]);
    std::cout << "Point capacity: " << runtime.getPointCapacity() << '\n';
    if (!runtime.infer(nullptr, 0, 0.01f, 4096, 3).empty()) return 1;
    try {
      runtime.infer(nullptr, runtime.getPointCapacity() + 1, 0.01f, 4096, 3);
      throw std::runtime_error("Oversize input was accepted");
    } catch (const std::invalid_argument&) {}
    std::vector<float> points;
    for (int i = 0; i < 128; ++i) {
      points.insert(points.end(), {5.f + float(i % 16) * 0.1f,
        float(i / 16) * 0.1f, 0.f, 0.5f});
    }
    for (int i = 0; i < 10; ++i) {
      const auto boxes = runtime.infer(points.data(), points.size() / 4, 0.01f, 4096, 3, i == 0);
      std::cout << "Synthetic frame " << i << ": " << boxes.size() << " detections\n";
    }
    if (!runtime.infer(nullptr, 0, 0.01f, 4096, 3).empty()) return 1;
    std::cout << "PASS: load, capacity rejection, repeated inference, profiling and empty result\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "FAIL: " << error.what() << '\n';
    return 1;
  }
}
