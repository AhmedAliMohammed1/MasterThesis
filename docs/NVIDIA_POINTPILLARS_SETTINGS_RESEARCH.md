# NVIDIA PointPillarNet settings research — 21 November 2026

Research only; no repository/live changes. Read local README, config/model_contract.json, MODEL_REFERENCE_COMPARISON.md and MODEL_INPUT_MISMATCH_AND_SOLUTIONS.md. Browsed official NVIDIA docs, catalog, version history and maintained source. Negative findings mean not found in the reviewed publisher material.

## Actionable conclusions

No publisher-supported Ouster setting guarantees higher confidence. NVIDIA's strongest advice is to match the LiDAR/configuration used in training. Clipped reflectivity/100 is a user-requested local experiment, not NVIDIA's recommended normalization. Use 0.3 as the requested live threshold, record it independently of encoding, and evaluate with labeled precision/recall and 3D/BEV matching. Higher scores alone do not establish improvement. If the adapter emits normalized values, detector intensity divisor must be 1, avoiding double division.

Preserve this exact export's feature order, point count, spatial grid and anchors. Verify real frame/mounting/ground measurements before applying a transform. Exact training sensor height and intensity calibration are not documented in reviewed sources. For durable target-domain adaptation, verify a compatible training checkpoint, label representative Ouster data, fine-tune and re-export/rebuild. A guessed height shift or patched voxel geometry is not a verified repair.

## Official evidence

[TAO 5.2 PointPillars](https://docs.nvidia.com/tao/tao-toolkit-archive/5.2.0/text/point_cloud/pointpillars.html) specifies four floating-point XYZI features, reflectance [0,1], LiDAR-center origin, x front/y left/z up, centered boxes and yaw around z. Its KITTI example uses ROI [0,-39.68,-3,69.12,39.68,1] and voxels [0.16,0.16,4], unlike our export. Do not overwrite our contract with it. It documents labeled training/validation data and explicitly says its mAP BEV/3D protocol differs from official KITTI. Thus local KITTI AP is not directly comparable to publisher KPIs. It does not establish Ouster normalization or original mounting height.

[NVIDIA ROS README](https://github.com/NVIDIA-TAO/ros2_tao_pointpillars) recommends the same sensor/configuration as training. It explains intensity_scale divides inputs; 255 is an example for [1,255] input versus [0,1] training. It does not establish physical equivalence of Ouster signal/reflectivity. It describes batch 1 and 204800 points with four features; demonstrations use Zvision bags.

[Official launch source](https://raw.githubusercontent.com/NVIDIA-TAO/ros2_tao_pointpillars/main/launch/pp_infer_launch.py) sets intensity_scale=255, NMS IoU=0.01, pre-NMS top N=4096 and Vehicle/Pedestrian/Cyclist. These are example parameters, not measured optimal Ouster settings.

[Current TAO docs](https://docs.nvidia.com/tao/tao-toolkit/latest/text/cv_finetuning/pytorch/point_cloud/pointpillars.html) document score_thresh=0.1, visualization threshold=0.1, NMS IoU=0.01 and multi_classes_nms=False; example pre/post maxima are 4096/500. Therefore current class-agnostic 0.01 NMS matches a publisher example. Class-aware NMS is an experiment, not a required NVIDIA correction. NMS changes retention, not neural scores. These thresholds do not predict average confidence. Pruning followed by retraining targets speed/size with recovered accuracy, not a direct confidence fix.

## Exact-export facts: local inspected contract, not a new binary parse

Local contract identifies ONNX deployable_v1.1 SHA256 2dcabddc3a365e9608a112d7bbbb7db769a6dddeeaa59aa03611a83113326da1; points FLOAT32 [batch,204800,4], actual num_points INT32 [batch]; 10000 pillars maximum, 32 points/pillar, voxel [0.2,0.2,5.8], ROI [-51.2,-51.2,-1.4,51.2,51.2,4.4]. Embedded decoder floor is approximately 0.1; ROS 0.3 is separate. Pedestrian anchor is 0.8×0.6×1.73 m with bottom -0.6 m. Anchors are learned priors plus offsets, not proof of a universal sensor height or mandatory z correction. Existing reports document dense-pillar instability and an independent TRT8 run with poor accuracy; a version downgrade alone is not established as a repair.

## Published metrics and important documentation discrepancies

[NGC overview](https://catalog.ngc.nvidia.com/orgs/nvidia/tao/models/pointpillarnet/-) reports proprietary solid-state-LiDAR data and mAP BEV/3D 65.2167%/51.7159% (trainable TLT), 66.6860%/52.8530% (deployable ETLT). It lists 7481 training scenes and 7581 evaluation scenes, with duplicated object counts and evaluation text saying training. Current selection is v1.1 but its model-version section names v1.0 and deployment instructions still describe ETLT/TRT8.2/OSS22.02. Therefore those KPIs do not prove exact v1.1 ONNX accuracy. It names TAO 5.2, model key tlt_encode and target-data fine-tuning through the trainable TLT. Local TLT identity/loadability remain unverified.

[Version history](https://catalog.ngc.nvidia.com/orgs/nvidia/tao/models/pointpillarnet/-/version-history) lists deployable_v1.1 (20 September 2024) without Accuracy; trainable_v1.1 Accuracy 65.21 and deployable_v1.0 Accuracy 66.86. The latter differs from overview 66.6860. Preserve attribution rather than silently reconciling. Accuracy/mAP is not average detection confidence. No mean-confidence target, pedestrian score distribution, Ouster benchmark or 1.5–2 m pedestrian success rate was found in reviewed sources.

[Explainability card](https://catalog.ngc.nvidia.com/orgs/nvidia/tao/models/pointpillarnet/-/model-card/explainability) identifies boxes, labels and confidence outputs and accuracy/mAP/recall as metrics. It names crowded traffic as a limitation and supplies no average confidence.

[Official TensorRT sample](https://raw.githubusercontent.com/NVIDIA-TAO/tao_toolkit_recipes/main/tao_pointpillars/tensorrt_sample/README.md) documents older ETLT, TRT8.2+, OSS22.02, FP16, 1×204800×4. This is a compatibility reference, not exact v1.1 ONNX certification or a reason to replace the working runtime. Some catalog old NVIDIA-AI-IOT links returned 404; sources now resolve under NVIDIA-TAO. Model API and pinned plugin URLs failed in this web pass; no independent fresh plugin verification is claimed.

Unresolved: exact train-time sensor and intensity calibration, trustworthy original output fixture, measured mounting, checkpoint identity/loadability, confirmed person annotation and false positives/negatives after the live change. No GPU experiments or accuracy evaluation were run by this research agent.
