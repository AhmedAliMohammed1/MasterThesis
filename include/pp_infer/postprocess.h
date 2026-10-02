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

#ifndef POSTPROCESS_H_
#define POSTPROCESS_H_

#include <vector>

struct Bndbox {
    float x{0};
    float y{0};
    float z{0};
    float w{0};
    float l{0};
    float h{0};
    float rt{0};
    int id{0};
    float score{0};
    Bndbox() = default;
    Bndbox(float x_, float y_, float z_, float l_, float w_, float h_, float rt_, int id_, float score_)
        : x(x_), y(y_), z(z_), w(w_), l(l_), h(h_), rt(rt_), id(id_), score(score_) {}
};

// Geometry uses length along X, width along Y and counterclockwise yaw.
bool valid_box(const Bndbox& box) noexcept;
double rotated_bev_iou(const Bndbox& a, const Bndbox& b);

// Output replaces prior contents. Invalid arguments/candidates throw invalid_argument.
// Default preserves legacy cross-class suppression until the model contract is known.
int nms_cpu(std::vector<Bndbox> bndboxes, const float nms_thresh,
            std::vector<Bndbox> &nms_pred, const int pre_nms_top_n, const bool class_aware = false);

#endif
