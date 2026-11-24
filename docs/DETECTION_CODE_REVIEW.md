# Independent detection code review

Reviewed 9 November 2026. This is a source review, not a new GPU accuracy result. Existing unrelated documentation edits were preserved.

## Main finding

The inspected application code does not contain a verified coordinate swap or extra height shift that explains the poor 3D detections. A minimal production correction cannot honestly be selected from the height symptom alone. The useful next boundary is the model's input/voxel-feature/decoder contract, with explicit capacity controls. Do not add a fitted output z offset or replace working NMS.

## What was inspected

README.md; config/model_contract.json; docs/MODEL_REFERENCE_COMPARISON.md; the current inference node/runtime, generic/Ouster adapters, CPU overlap/NMS, output contract and their relevant C++ tests; the cached pinned NVIDIA voxel/decode kernel sources and voxel plugin enqueue path. No host driver, data, model, engine or runtime source was changed by this review. No AGENTS.md was found in the inspected project/ancestor locations.

## Verified application behavior

| Boundary | Source location | Review result |
| --- | --- | --- |
| Raw box decoding | include/pp_infer/output_contract.hpp:26 | Direct x/y/z/dx/dy/dz/yaw mapping. Bndbox constructor accepts length before width and stores each correctly. |
| ROS message geometry | src/pointcloud_adapter.cpp:116 | Center remains the decoded center; size.x receives length, size.y width, size.z height. Yaw quaternion is consistent with yaw around +z. |
| Point packing | src/pointcloud_adapter.cpp:89 | XYZ and order preserved after finite filtering. Only intensity is divided. Organized row padding has a focused fixture. |
| GPU input/count | src/pointpillar.cpp:139 | Capacity input is cleared, valid points copied, actual INT32 point count sent. Output count is validated before box-row copying. |
| Error handling | src/pointpillar.cpp:162 | Invalid decoded rows reject the whole observation; they are not silently removed. The GPU fault latch covers GPU execution/transfers, while decoder validation follows it. |
| Confidence gate | src/pointcloud_adapter.cpp:125 | The additional gate removes candidates without changing coordinates. It cannot repair vertical localization. |

The older same-candidate comparison selected identical boxes in all 192 observations with project and unchanged NVIDIA NMS. This review does not treat that as exact training/numerical parity. Elevated boxes are already present in raw TensorRT8 and TensorRT10 candidates, so a ROS publication-only explanation is inconsistent with the saved experiment.

## Material input risk, with bounded scope

The generic point packer checks total allocation capacity, not occupied pillars or per-pillar occupancy. All-zero XYZ returns remain finite and are retained. The pinned published NVIDIA kernel increments a pillar counter and writes coordinates at that index without a visible max-pillar guard (.recovery/reference-upstream/trt10-voxelGeneratorKernels.cu:86–89). The later feature kernel clamps the count after that write. This is a verified concern in the inspected published source; it does not prove identical machine code or an observed tensor overwrite in the packaged library.

The recorded capacity controls improve repeatability but retain poor 3D accuracy. Therefore capacity/valid-return handling is justified as its own explicit, tested input policy, not as a demonstrated complete accuracy solution.

Minimal implementation recommendation: one plain preprocessing function operating on packed XYZI, using the inspected model grid and an explicitly selected policy. Preserve input point bits and order. Report original, nonfinite/invalid-return, out-of-ROI, retained and capacity-removed counts. Keep the legacy behavior selectable for reproducing frozen studies. Avoid a new plugin abstraction, automatic sensor classifier, worker rewrite or channel-ranking framework in this correction.

Required tests: half-open ROI bounds; float32 grid arithmetic at cell edges; first-encountered pillar and point selection; exact 10,000/32 boundaries; original bit/order preservation; zero-return policy; no over-capacity output; unchanged default/legacy path. A three-repeat geometry-only GPU control is an engineering check, not new independent scenes or proof of 3D accuracy.

## Other findings that do not explain the shared poor geometry

- decode_boxes accepts finite scores below zero or above one, whereas make_detections rejects them. This is a small consistency gap in the direct C++ API; sigmoid model outputs normally satisfy the range. If changed, add two direct decoder boundary tests rather than redesigning postprocessing.
- The literal Ouster signal selector cannot read a recording that names the verified signal channel intensity. Use an explicit field mapping if needed; do not silently assume every intensity field is signal. The offline study already uses its verified schema, so this does not invalidate its completed comparison.
- The synchronous reliable depth-700 callback can accumulate old clouds. This affects live age/latency, not saved direct-run box geometry. Worker/QoS changes should remain separate from the accuracy investigation.
- Class-agnostic NMS and IoU 0.01 can affect recall, but neither explains elevated raw candidates. Any class-aware/threshold trial belongs on development data and must not silently replace the frozen baseline.

## Next decisive accuracy check

Establish the original model's training coordinate and feature construction from an independent training-framework reference. Compare one small cloud's voxel membership, 10 pillar features, scatter positions, pre-decoder box residuals and the decoder math. Keep original engine/data unchanged and mark any new exposed-output model as diagnostic. Verify training convention and sensor origin before considering a coordinate transform. If an independently verified reference also fails on the new sensor, evaluate a sensor-compatible export or retraining/fine-tuning with recording-disjoint evaluation.

A pretrained model that executes correctly is not guaranteed to match an Ouster distribution. However, the shared KITTI failure means sensor domain shift alone is not yet a sufficient explanation.

## Final implementation review: explicit offline point policy

Reviewed after the development and independent testing agents completed their work on 9 November 2026. Files inspected in full: `include/pp_infer/point_policy.hpp`, `src/point_policy.cpp`, `tools/prepare_points.cpp`, `tests/core/test_point_policy.cpp`, and the relevant `CMakeLists.txt` configuration.

**Review outcome: no blocking correctness or unnecessary-abstraction finding in this change.** This approval covers the explicit offline diagnostic preparation tool. It is not an accuracy acceptance or a claim that the live pipeline has been corrected.

- `prepare_points` defaults to passthrough, returns before grid validation, and leaves all input float bits untouched. The detector and Ouster adapter do not call it. Existing runtime preprocessing therefore remains unchanged.
- Bounded mode requires an explicit finite, increasing ROI, positive voxel sizes and capacities. It uses separate float32 subtraction/division and half-open ROI tests. It neither infers model attributes from tensor shape nor invents a sensor correction.
- First-encountered pillar and per-pillar selection uses a map for lookup rather than iteration; output order remains input order. Original XYZI is copied with `memcpy`, including signed-zero feature bits. The routine swaps the selected buffer only after successful processing.
- The removal counters form a mutually exclusive priority partition: nonfinite XYZI, zero XYZ, outside ROI, new-pillar limit, per-pillar limit, total point limit, or retained. A point can satisfy several conditions physically but is deliberately counted in only the first applicable category. Retained pillars are inserted only for retained points.
- The standalone CLI reads native-endian packed FLOAT32 XYZI with a 1 GiB input bound. Exclusive output creation refuses an existing file, including a source artifact. Partial write cleanup targets only the file it created.
- `PP_BUILD_POINT_DIAGNOSTICS` defaults OFF. CMake references the CLI source only when that option is ON, preserving the deployment build context that does not copy the tools directory. The shared CPU policy and focused test are small and require no extra framework.
- Focused tests cover unchanged default bytes, retained bit/order, nonfinite features, zero XYZ, half-open ROI, float32 boundary arithmetic, exact 10,000/32 limits, total capacity, empty input and invalid configuration. Separate development/testing records report the three passing CTest executables, minimal no-tools build-context check, real-scan C++/Python byte parity and artifact-overwrite refusal. This final review inspected those implementation guarantees without claiming to rerun those experiments.

No further production change is recommended solely from this review. Keep the CLI as a controlled experiment until an annotated comparison and model-feature/reference investigation justify any live input-policy change. The current capped/uncapped unlabeled results establish preparation behavior and aspects of repeatability, not a remedy for elevated 3D boxes.
