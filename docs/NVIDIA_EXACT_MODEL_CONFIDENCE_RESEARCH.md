# Exact deployed PointPillarNet and NVIDIA confidence research

Reviewed 21 November 2026 (Europe/Berlin). Read-only model inspection and authoritative source research; no live settings changed by this agent.

## Confirmed exact identity

Publisher endpoint fetched successfully:
https://api.ngc.nvidia.com/v2/models/nvidia/tao/pointpillarnet/versions/deployable_v1.1/files

Local file `/media/ae/New Volume1/MasterThesis/pointpillars_deployable.onnx`, 5,572,374 bytes, SHA256 `2dcabddc3a365e9608a112d7bbbb7db769a6dddeeaa59aa03611a83113326da1`, independently recomputed and identical to the decoded publisher SHA256.
`label.txt` SHA256 `0adaeb5a374421b61bf83b8fa4522e11abd68461f239a4c72cf5627de913b3da` also matches. Class order Vehicle, Pedestrian, Cyclist.
Version API https://api.ngc.nvidia.com/v2/models/nvidia/tao/pointpillarnet/versions/deployable_v1.1 gives creation 2024-09-20T07:42:00.965Z, update 2025-03-01T14:49:51.935Z and an empty version description. The version contains only two files, model and labels. No exact training configuration, sensor calibration, input/output reference fixture or confidence histogram is in that manifest.

## Exact ONNX attributes, freshly parsed locally

FLOAT32 points [batch,204800,4]; INT32 num_points [batch]. Runtime deployment guidance requires batch 1. Features are raw XYZ and reflectance, not precomputed pillars; VoxelGeneratorPlugin internally creates 10 features. Plugin attributes: XY range approximately -51.2 to +51.2 metres, z -1.4 to +4.4 metres; voxel size 0.2,0.2,5.8m; max_voxels 10000; max_num_points_per_voxel 32; scatter 512 by 512.
Output FLOAT32 boxes [batch,393216,9], INT32 num_boxes [batch]. Decoder score floor 0.10000000149. Anchor size L/W/H: Vehicle 3.9/1.6/1.56, Pedestrian 0.8/0.6/1.73, Cyclist 1.76/0.6/1.73. Rotations 0/1.57. Bottom heights -1.78/-0.6/-0.6 respectively. Boxes are geometric centers in NVIDIA deployment description, not bottoms. The lower ROS score gate 0.3 remains above embedded floor 0.1 and can recover existing outputs; changing it cannot create previously rejected internal outputs or improve coordinates.
Metadata parse saved `/tmp/pp-nvidia-exact-model-research/actual-onnx-metadata.json`.

## NVIDIA input contract versus uncertainty

Current official TAO documentation:
https://docs.nvidia.com/tao/tao-toolkit/6.26.03/text/cv_finetuning/pytorch/point_cloud/pointpillars.html

The guide describes floating XYZ/reflectance in [0,1], LiDAR-centered coordinates with x forward/y left/z up and counterclockwise yaw. These are framework conventions, not proof of the exact unpublished v1.1 intensity calibration or sensor mounting height. Its example config is not the exact export config; e.g. the guide example maximum input points differs. Never copy generic example ROI or input size over inspected ONNX dimensions.

NVIDIA blog, published 30 September 2022:
https://developer.nvidia.com/blog/detecting-objects-in-point-clouds-using-ros-2-and-tao-pointpillars/
The article body identifies a model trained on Zvision solid-state LiDAR and says coordinate and reflectance ranges must match between training/inference. It warns sensor changes can greatly reduce accuracy without adaptation. That 2022 demonstration does not certify exact 2024 v1.1 training identity.

Official ROS repository:
https://github.com/NVIDIA-TAO/ros2_tao_pointpillars
Recommends matching LiDAR and configuration to training; describes intensity_scale as a divisor (255 only as an example for data genuinely representing the expected [0,1] feature). It does not endorse clipping Ouster reflectivity at 100. Thus min(reflectivity/100,1) is a measured project trial, not a publisher-supported universal default. Physical intensity compatibility and target mounting remain unresolved.

## Published metrics versus average confidence

NGC shared model card:
https://catalog.ngc.nvidia.com/orgs/nvidia/teams/tao/models/pointpillarnet
Its KPI is mAP, not mean predicted confidence. Trainable .tlt BEV/3D mAP is 65.2167% / 51.7159%; deployable .etlt is 66.6860% / 52.8530%. These numbers describe detection quality over a labeled proprietary dataset and cannot be compared to an individual box score 0.3. The card explicitly lists v1.0 artifacts although latest download is v1.1 ONNX. Hence the published table is not independently certified as exact v1.1 ONNX performance, and it is not Ouster performance.
Version history https://catalog.ngc.nvidia.com/orgs/nvidia/tao/models/pointpillarnet/deployable_v1.0/version-history also shows an older v1.0 accuracy badge 66.86; it differs from the detailed shared-card 66.6860. Use the detailed table as a card-reported value and acknowledge model/version uncertainty, not an exact-v1.1 ground truth.
No mean confidence, per-class score distribution, confidence-by-range chart or calibration result was found in the inspected NGC card and API responses, NVIDIA ROS blog, TAO guide or official ROS README. This is a scoped search result, not proof that no unpublished NVIDIA report exists. NVIDIA supplies no verified average-confidence target for this local near-range person case in those resources.

## Limits and evidence

Fresh network API response bodies and retrieval UTC timestamps/SHA256 in `/tmp/pp-nvidia-exact-model-research/sources.json`. Web pages read using browser search/open; no page text is presented as a training configuration. Source quotes omitted in this note, only paraphrases. No retraining, inference, detection labeling or live intervention performed by this agent. No inference that min(reflectivity/100,1) detects the user is justified by NVIDIA sources alone.
