/*
 * SPDX-FileCopyrightText: Copyright (c) 2022 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "pp_infer/postprocess.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>

namespace {
struct Point2 { double x; double y; };
using Corners = std::array<Point2, 4>;
// Clipping a quadrilateral by four half-planes produces at most eight vertices.
struct Polygon { std::array<Point2, 12> points{}; std::size_t size{0}; };

bool valid_geometry(const Bndbox& box) noexcept {
  return std::isfinite(box.x) && std::isfinite(box.y) && std::isfinite(box.z) &&
    std::isfinite(box.l) && std::isfinite(box.w) && std::isfinite(box.h) &&
    std::isfinite(box.rt) && box.l > 0 && box.w > 0 && box.h > 0;
}

Corners corners(const Bndbox& box, double origin_x, double origin_y) {
  const double c = std::cos(static_cast<double>(box.rt));
  const double s = std::sin(static_cast<double>(box.rt));
  const double l = static_cast<double>(box.l) / 2;
  const double w = static_cast<double>(box.w) / 2;
  Corners result{{{-l, -w}, {l, -w}, {l, w}, {-l, w}}};
  for (auto& p : result) {
    const double x = p.x;
    p.x = x * c - p.y * s + (static_cast<double>(box.x) - origin_x);
    p.y = x * s + p.y * c + (static_cast<double>(box.y) - origin_y);
  }
  return result;
}

double side(Point2 a, Point2 b, Point2 p) {
  return (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x);
}

Polygon clip(const Polygon& input, Point2 a, Point2 b) {
  Polygon output;
  if (input.size == 0) return output;
  auto append = [&output](Point2 p) {
    if (output.size >= output.points.size())
      throw std::runtime_error("Rotated intersection exceeded its bounded vertex capacity");
    output.points[output.size++] = p;
  };
  Point2 previous = input.points[input.size - 1];
  double previous_side = side(a, b, previous);
  for (std::size_t i = 0; i < input.size; ++i) {
    const Point2 current = input.points[i];
    const double current_side = side(a, b, current);
    if ((previous_side >= 0) != (current_side >= 0)) {
      const double t = previous_side / (previous_side - current_side);
      append({previous.x + t * (current.x - previous.x),
              previous.y + t * (current.y - previous.y)});
    }
    if (current_side >= 0) append(current);
    previous = current;
    previous_side = current_side;
  }
  return output;
}

double area(const Polygon& polygon) {
  if (polygon.size < 3) return 0;
  double twice_area = 0;
  const auto origin = polygon.points[0];
  for (std::size_t i = 1; i + 1 < polygon.size; ++i)
    twice_area += side(origin, polygon.points[i], polygon.points[i + 1]);
  return std::abs(twice_area) / 2;
}
}  // namespace

bool valid_box(const Bndbox& box) noexcept {
  return valid_geometry(box) && std::isfinite(box.score) && box.id >= 0;
}

double rotated_bev_iou(const Bndbox& a, const Bndbox& b) {
  if (!valid_geometry(a) || !valid_geometry(b)) return 0;
  const auto subject = corners(a, a.x, a.y);
  const auto boundary = corners(b, a.x, a.y);
  // Reject separated projections before clipping, including extreme coordinates
  // where a small box's corners can lose resolution far from the local origin.
  for (bool x_axis : {true, false}) {
    auto less = [x_axis](Point2 p, Point2 q) { return x_axis ? p.x < q.x : p.y < q.y; };
    const auto bounds_a = std::minmax_element(subject.begin(), subject.end(), less);
    const auto bounds_b = std::minmax_element(boundary.begin(), boundary.end(), less);
    const auto value = [x_axis](Point2 p) { return x_axis ? p.x : p.y; };
    if (value(*bounds_a.second) <= value(*bounds_b.first) ||
        value(*bounds_b.second) <= value(*bounds_a.first)) return 0;
  }
  Polygon polygon;
  std::copy(subject.begin(), subject.end(), polygon.points.begin());
  polygon.size = subject.size();
  for (std::size_t i = 0; i < boundary.size(); ++i)
    polygon = clip(polygon, boundary[i], boundary[(i + 1) % boundary.size()]);
  const double area_a = static_cast<double>(a.l) * a.w;
  const double area_b = static_cast<double>(b.l) * b.w;
  const double overlap = std::clamp(area(polygon), 0.0, std::min(area_a, area_b));
  const double union_area = area_a + area_b - overlap;
  return union_area > 0 ? std::clamp(overlap / union_area, 0.0, 1.0) : 0;
}

int nms_cpu(std::vector<Bndbox> boxes, const float threshold,
            std::vector<Bndbox>& output, const int top_n, const bool class_aware) {
  // Clear on every attempt, including invalid arguments, to prevent stale detections.
  output.clear();
  if (!std::isfinite(threshold) || threshold < 0 || threshold > 1 || top_n <= 0)
    throw std::invalid_argument("NMS requires finite IoU in [0,1] and positive top_n");
  for (const auto& box : boxes)
    if (!valid_box(box)) throw std::invalid_argument("NMS received an invalid box/class/score");
  // Equal scores retain original engine order; semantics are explicit and repeatable.
  std::stable_sort(boxes.begin(), boxes.end(),
    [](const Bndbox& a, const Bndbox& b) { return a.score > b.score; });
  const std::size_t count = std::min(boxes.size(), static_cast<std::size_t>(top_n));
  std::vector<bool> suppressed(count, false);
  output.reserve(count);
  for (std::size_t i = 0; i < count; ++i) {
    if (suppressed[i]) continue;
    output.push_back(boxes[i]);
    for (std::size_t j = i + 1; j < count; ++j) {
      if (suppressed[j] || (class_aware && boxes[i].id != boxes[j].id)) continue;
      // Preserve the original >= threshold rule, including its threshold=0 behavior.
      if (rotated_bev_iou(boxes[i], boxes[j]) >= threshold) suppressed[j] = true;
    }
  }
  return 0;
}
