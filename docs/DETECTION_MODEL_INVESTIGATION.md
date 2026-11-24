# Why detections remain inaccurate: model and input investigation

Reviewed 9 November 2026. This is a diagnosis, not an accuracy fix. No production source, model, engine, original cloud, annotation or frozen result was changed in this investigation.

## What the evidence establishes

The problem starts before RViz. TensorRT 8 and 10 both returned elevated candidates on labeled KITTI data. The current output adapter copies the candidate z directly into the ROS center; it adds no half-height. NVIDIA and project NMS selected identical boxes in all 192 same-candidate comparisons. These observations make a viewer-only or NMS-only explanation insufficient. They do not establish exact original-training parity.

The annotated Ouster comparison also finds poor geometry: reflectivity/255 obtains four qualifying Vehicle footprints per repeat, but none qualifies in 3D. Their centers are 0.60–1.14 m above annotations. A threshold can remove a box; it cannot repair its center. Numerical completion of both normalized channels is not accurate localization.

## The pretrained artifact is not established as a KITTI model

A fresh request to NVIDIA's exact `deployable_v1.1` files API confirms the local ONNX and labels against publisher SHA-256. The model identity remains `2dcabddc3a365e9608a112d7bbbb7db769a6dddeeaa59aa03611a83113326da1`.

The associated model-level card describes proprietary data collected by solid-state LiDAR. It does not establish Ouster or KITTI training. The version-specific description is empty. The shared card still names older artifact versions and has inconsistent train/evaluation sample counts. Consequently, the defensible statement is **there is no verified KITTI/Ouster training match for this exact export**. The model card supports a sensor-domain concern; it does not independently prove which exact training files or mounting height produced v1.1.

The upstream ROS guide recommends matching the training LiDAR and configuration. NVIDIA's demonstration blog describes Zvision data, but that demonstration alone cannot certify the exact downloaded export's training identity. Its published KPI must not be treated as this project's expected KITTI/Ouster score.

Sources: [NVIDIA model card](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/tao/models/pointpillarnet), [exact-version file identities](https://api.ngc.nvidia.com/v2/models/nvidia/tao/pointpillarnet/versions/deployable_v1.1/files), [upstream input guidance](https://github.com/NVIDIA-AI-IOT/ros2_tao_pointpillars), [NVIDIA demonstration](https://developer.nvidia.com/blog/detecting-objects-in-point-clouds-using-ros-2-and-tao-pointpillars/).

## Trace the height through the code

| Stage | Verified behavior | Consequence |
| --- | --- | --- |
| Model voxel range | z in approximately [−1.4,4.4), XY ±51.2 m | Points outside it are not encoded, even if the ROS cloud was accepted. |
| Published decoder | `z = residual_z * anchor_height + anchor_bottom + anchor_height/2` | The decoder returns a geometric center, not a bottom coordinate. |
| Zero-residual Vehicle anchor | Bottom −1.78 m; height 1.56 m; center −1.00 m | Adding another half-height in application code would be wrong. |
| Zero-residual pedestrian/cyclist anchor | Bottom −0.60 m; height 1.73 m; center 0.265 m | Different class priors make a universal shift especially questionable. |
| Production `decode_boxes` | Reads columns 0–8 directly; validates geometry and class | There is no application z translation. |
| ROS message adaptation | Copies `box.z` into `bbox.center.position.z` | Display receives the same center convention. |

The anchor arithmetic was freshly recomputed from the inspected ONNX metadata on 9 November. This is a mathematical/source check, not a fresh decoder GPU parity test. Source: `config/model_contract.json`, `include/pp_infer/output_contract.hpp`, `src/pointcloud_adapter.cpp`, and preserved `.recovery/reference-upstream/trt8-decodeBbox3DKernels.cu`.

The range's low boundary can remove lower vehicle/ground geometry when the target sensor sits higher than the training sensor. That is a plausible contributor, not a proven cause or justification for translating all points. An anchor extending below the input range is not by itself a decoder defect: boxes and point regions have different roles.

## Capacity is a separate implementation concern

The preserved NVIDIA voxel kernel increments `current_pillarId` and writes a coordinate before a later stage clamps the count to the configured maximum. The plugin allocates that coordinate output for only 10,000 pillars. Thus the published source contains a concrete over-capacity tensor-bounds concern. This does not prove that every installed proprietary plugin binary executes identical code or that an observed height error is caused by that branch.

The frozen audits found 12/32 KITTI and 20/32 primary labeled Ouster scans above the pillar bound. Capacity controls improved repeatability but retained poor 3D accuracy. Therefore capacity needs protection, while a capacity-only explanation of all inaccurate detections is unsupported. Crowded pillars can also select different first 32 points through GPU atomics; deterministic CPU controls change the selection policy.

## Small experiments that can distinguish the causes

1. **Protect the model's actual capacities.** Measure points, occupied pillars and per-pillar occupancy before inference. Reject or explicitly select bounded inputs under a declared policy. Compare original and controlled inputs using tuning data, bit-identical channel geometry, and saved output identities. This addresses a specific software risk; it is not an accuracy claim.
2. **Measure target geometry before changing it.** On tuning frames, report how many annotated-object points are removed by each model boundary, distance to the measured ground, and how many objects have enough retained points. Infer ground from geometry independently of predictions. Do not optimize a point/box shift on the inspected test labels.
3. **Check intermediate plugin outputs.** With a tiny capacity-compliant artificial cloud, compare the plugin's ten point features against the documented XYZ, intensity, cluster offsets and voxel-center offsets. Use zero box residuals to check the full decoder against the anchor values above. Save intermediate tensors and compare exact slot order before attributing errors to pretrained weights.
4. **Obtain an independent reference in the model's documented domain.** The shared card mentions `102.bin`, but it is absent from the inspected pinned recipe tree; an attempted historical raw path returned 404. Do not fabricate a sample or describe that control as completed. Obtain a publisher-provided input with expected raw outputs, or recover a validated training-framework export reference.
5. **Choose a compatible model only after that separation.** If implementation checks agree but target performance remains poor, use an independently validated Ouster-compatible model or fine-tune using training/tuning recordings. Lock preprocessing and operating threshold, then evaluate a new recording-disjoint test set. Retain the current inspected test results as diagnostics.

A proper solution can require both capacity-safe preprocessing and a model trained for the target sensor. The evidence does not support a display-only height correction, changing labels to improve scores, arbitrary normalization sweeps on test data, or claiming that retraining alone will fix a plugin defect.

## Reproduction and remaining uncertainty

Fresh primary-source HTTP responses, retrieval times, SHA-256 identities and the exact local/publisher comparison are saved under `.recovery/verification/detection-investigation-2026-11-09/model/`. `sources.json` records successful responses and the unavailable sample URL; `verified-model-identity.json` records the file matches and anchor arithmetic. These large evidence files are ignored and require separate backup.

No new inference was performed by this model-investigation agent. The testing agent's new controls and measurements must be reported separately. The root cause of vertical localization remains unresolved until intermediate features/decoder behavior and a trustworthy in-domain reference agree. The target feature's physical calibration, training mounting convention, packaged plugin tensor behavior and expected original outputs remain material unknowns.
