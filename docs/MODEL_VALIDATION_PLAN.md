# Verifying the PointPillars model on KITTI

This is the plan for W01, started on 2 October 2026. The user chose labeled KITTI scenarios first, followed by their own LiDAR recordings when available. It separates correct implementation of the downloaded model from the model's accuracy on a new dataset. Neither result has been claimed complete.

## What the first investigation established

The actual local ONNX hash matches NVIDIA's deployable_v1.1 package metadata. That same package supplies label.txt, with the verified order:

| Numeric ID | NVIDIA label |
|---|---|
| 0 | Vehicle |
| 1 | Pedestrian |
| 2 | Cyclist |

The package's label hash also matches the existing repository label.txt. This closes the label-file provenance/order gap for this export. Runtime class_names still uses generic smoke labels; class IDs in ROS messages are numeric strings.

The NVIDIA model card describes proprietary solid-state LiDAR training/evaluation data. Some card instructions still describe older ETLT versions. We therefore use the exact v1.1 file manifest and ONNX attributes for artifact-specific facts, and treat KITTI performance as a separate measurement. We cannot reproduce the card's published accuracy from an unrelated KITTI sample.

TAO documents XYZI reflectance in [0,1] and a LiDAR frame with x forward, y left and z up. The release/10.16 decoder source emits box centers, dimensions along local x/y/z, yaw in radians, zero-based class ID and score. Its anchor z uses bottom height plus half anchor height; output z is not the anchor bottom. This supports the existing ROS center mapping, rather than an unverified extra half-height adjustment.

The exact ONNX embeds a range of approximately x/y [-51.2,51.2] m and z [-1.4,4.4] m, voxels [0.2,0.2,5.8], 10000 pillars, 32 points per pillar and a decode score threshold of 0.1. These are properties of this export. Do not replace them with the different example KITTI training range from the TAO manual.

A read-only audit of the first three existing bag clouds found intensity 0–0.99, with no samples outside [0,1]. They therefore support scale 1.0 for this bag. About 29.6–29.8 thousand of approximately 124 thousand points per cloud were inside the encoded range; many points were below the z range. This is an input-coverage observation, not proof of a bug or accuracy failure. Inspect where labeled objects fall before making any frame translation. Do not shift z or divide intensity by 255 merely to make the picture look different.

Evidence and remaining gaps are recorded in [model_contract.json](../config/model_contract.json). It is a partial validation record, not yet runtime enforcement or an accuracy certificate.

## Step 1: freeze the model and the evaluation rules

Keep the exact ONNX hash, TensorRT version, precision, plugin versions, point packing, output decoding, NMS policy and confidence thresholds in the validation manifest. Initially use the existing FP32 recipe and postprocessing so the comparison can isolate migration issues.

Bind the labels to the verified model hash. Confirm all incoming data sources separately: a future sensor can use another intensity scale or frame even though the current KITTI bag matches the documented reflectance range.

Remaining code for this step: enforce or validate the model contract at startup, integrate the verified labels into current configuration/documentation, and add focused geometry/coordinate mapping fixtures. Do not call every semantic check complete just because the label order is resolved.

## Step 2: prepare labeled KITTI frames

The existing raw-sequence bag and matching MP4 provide integration and scene context; this setup contains no object annotations. They cannot produce an accuracy score.

Use the KITTI **3D object detection training data**, whose annotations are public. Each selected frame needs matching:

- Velodyne point cloud;
- label_2 annotation;
- calibration matrices;
- image dimensions, and preferably the camera image for review.

The official download page currently lists 29 GB for the full point-cloud archive, 5 MB for labels and 16 MB for calibration. Downloads require the dataset's official access process. A preparation tool may select a subset through verified ZIP ranges if the endpoint supports it; do not assume range support, valid direct URLs or silently fetch the whole archive.

Keep assets outside Git, for example ../datasets/kitti_object. Record dataset source, hashes, frame IDs and split identity. The current bag helper does not already prepare labeled object-detection data.

Start with a small diagnostic set covering all three classes, near/far objects, isolated/crowded scenes and different occlusion/truncation levels available in KITTI. Then use a substantially larger fixed evaluation split. Small samples diagnose errors; they do not establish reliable overall AP. Do not promise night/rain coverage that the selected KITTI data does not provide.

Select scenarios from annotations and scene information before seeing detector results. Do not choose only frames where the detector succeeds. Keep a separate tuning split and an untouched test split. Without the pretrained training manifest, we cannot certify that every KITTI frame is unseen by that pretrained model.

## Step 3: put annotations and predictions in the same frame

KITTI labels use camera-coordinate conventions and box locations that differ from ROS center-based LiDAR messages. A direct comparison of their numeric x/y/z values would be wrong.

Use each frame's calibration to transform annotations and predictions into a common coordinate frame. Handle bottom-to-center conversion, dimension ordering and orientation explicitly. Test a known box's center, corners and heading with an independent construction, then visually check projected/3D overlays.

Account for KITTI's camera-visible labeling scope: this model has a much wider x/y range, and a rear-facing prediction is not directly comparable with a front-camera label set. Declare and freeze visibility/ignore rules. Report coverage of the model's spatial range rather than quietly dropping inconvenient ground-truth objects. A separate region-restricted score must be labeled as such.

## Step 4: verify reference parity

Run exactly the same packed points through:

1. an independent inference/reference path for this same ONNX and compatible plugins; and
2. the migrated node.

Compare point count and packed values, decoded boxes before NMS, scores/classes, and final boxes after identical NMS/top-N settings. Use class-aware matching by geometry with declared tolerances rather than raw array order: the decoder uses an atomic output counter, so row ordering is not a reference identity.

The independent path should not call the same migrated runtime and postprocessing code, or it would merely compare the implementation with itself. The old NVIDIA sample is a reference for semantics but needs an isolated compatible runtime/adaptation before it is runnable on the current stack. An unrelated trainable TLT is not a proven reference for the pruned deployable ONNX unless their pairing/export history is established.

Reference parity answers “did our migration change the model's behavior?” It does not answer “does this model detect KITTI objects well?”

## Step 5: measure accuracy

Compute precision, recall, missed detections, false positives and AP for each class, with 3D and bird's-eye-view overlap. Report the defined sample split and scenario/difficulty breakdowns.

For official KITTI-compatible reporting, follow its evaluator, ignore/visibility/difficulty rules and AP_R40 protocol. KITTI uses overlap 0.7 for Car and 0.5 for Pedestrian/Cyclist. This model's Vehicle label is broader than Car: define the mapping before evaluation. Do not silently rename all vehicles Car or merge Van/Truck while still calling the result an official KITTI score.

A useful alternative is a clearly named custom Vehicle/Pedestrian/Cyclist evaluation with declared class groups, overlap thresholds and ignored categories. Its AP is not interchangeable with official KITTI Car AP or NVIDIA's proprietary-dataset mAP. TAO also documents that its general metric differs from KITTI's official difficulty-based metric.

Tune confidence/NMS only on the tuning split. Evaluate the final fixed settings on the untouched split. If parity passes but KITTI accuracy is poor, investigate sensor/data differences and model suitability before blaming TensorRT. Fine-tuning or a KITTI-trained replacement may become appropriate after that evidence; it is not required merely to start validation.

## Step 6: define and record acceptance

W01 becomes verified only when:

- the artifact-bound class, input and box conventions are resolved and tested;
- the known fixtures match an independent reference within declared tolerances;
- the dataset/mapping/evaluator/splits are frozen and identifiable;
- per-class/scenario accuracy is measured and meets the agreed targets;
- the result can be reproduced from saved commands/configuration and evidence.

The project does not yet have agreed accuracy targets. We will measure the baseline, propose useful thresholds, and agree on them before claiming acceptance. A score alone cannot choose what is acceptable for the future application.

Later, record and annotate representative clouds from the user's actual sensor, audit intensity/frame/range again, and repeat the same protocol. Passing KITTI validation will not validate that sensor automatically.

## Preparation implemented on 3 October 2026

The [labeled-data preparation guide](KITTI_VALIDATION_DATA.md) describes the implemented standard-library tool, pinned official sources, deterministic annotation-based scenario selection, raw-drive-disjoint tuning/test partitions, atomic asset recovery and full calibration conversion. The initial 32 real frames have matching annotations, clouds, calibration and images, with all configured buckets present in both splits. Fifteen focused fixtures and eight existing HTTP/recovery regressions passed. The [validation inventory](../config/kitti_validation_inventory.json) indexes exact manifests and evidence. This supersedes the initial investigation's “no labeled downloads” status.

The raw KITTI annotations remain unchanged, including DontCare and other classes. Full orientation/corners retain calibration tilt; no yaw-only approximation, intensity rescaling or coordinate shift was applied. The observed object/model-range coverage is documented separately from accuracy.

## What remains to implement next

Prediction export, explicit evaluator policy and baseline scoring are delivered. A separate TensorRT8.6 compatibility reference is also measured; it is not a trusted training-framework fixture. Next resolve bounded voxelization, shared repeatability and tensor-bounds concerns, verify the original input/training contract and decoder behavior, and define a larger untouched acceptance evaluation. Runtime contract enforcement and verified-label configuration integration remain. The original preparation phase performed no inference; the dated updates below record later measurements.

## Sources

- [NVIDIA exact deployable_v1.1 file manifest](https://api.ngc.nvidia.com/v2/models/nvidia/tao/pointpillarnet/versions/deployable_v1.1/files)
- [Exact model label file](https://api.ngc.nvidia.com/v2/models/nvidia/tao/pointpillarnet/versions/deployable_v1.1/files/label.txt)
- [NVIDIA model card](https://catalog.ngc.nvidia.com/orgs/nvidia/tao/models/pointpillarnet/-?_lr=1)
- [TAO PointPillars input/annotation/evaluation documentation](https://docs.nvidia.com/tao/tao-toolkit/6.26.03/text/cv_finetuning/pytorch/point_cloud/pointpillars.html)
- [TensorRT release/10.16 decoder kernel](https://github.com/NVIDIA/TensorRT/blob/release/10.16/plugin/common/kernels/decodeBbox3DKernels.cu)
- [TensorRT release/10.16 decoder documentation](https://github.com/NVIDIA/TensorRT/blob/release/10.16/plugin/decodeBbox3DPlugin/README.md)
- [Official KITTI 3D detection data and evaluation rules](https://www.cvlibs.net/datasets/kitti/eval_object.php?obj_benchmark=3d)

Exact source identities and the ignored input-audit log are indexed by the partial contract and recovery records. Generic documentation and old model-card deployment commands must not override the exact ONNX attributes or be mistaken for a current TensorRT installation procedure.


## Measurement update: 3 October 2026

The first labeled 32-frame diagnostic baseline is now measured. The 16-frame test split has zero moderate 3D matches; moderate BEV AP_R40 is Car 5.75%, Pedestrian 0%, Cyclist 0.0258%. Vehicle is explicitly mapped to Car compatibility. The evaluator's exact/missing/duplicate controls passed, and 41 total Python tests passed. Green calibrated ground truth and live predictions render together in RViz on domain 42. First-pass detections are frozen; repeated counts vary and full independent original-model parity remains pending. Read [accuracy results and commands](KITTI_ACCURACY_RESULTS.md) and [inventory](../config/kitti_accuracy_inventory.json). Earlier “not measured” statements describe preparation or the initial investigation, not this new baseline. Accuracy acceptance remains unmet.


## Independent reference update: 3 October 2026

A separate TensorRT8.6 engine for the exact ONNX reproduced the poor KITTI baseline and approximately1.53m upward car error. Three repeats per runtime (192 raw inferences) still produced zero moderate 3D matches in both runtimes. NVIDIA's unchanged NMS and our NMS selected identical boxes on all192 same-candidate observations. Strict numerical parity remains unmet: both runtimes vary, and12 frames exceed the export's10,000-voxel limit. Two tuning-only capacity controls improved repeat matching to roughly99.6–100%; no production adaptation was installed. Two actual CUDA12.9 allocation probes reported zero errors, which does not clear the internal tensor-bounds concern or complete GPU memory validation. Read [independent comparison](MODEL_REFERENCE_COMPARISON.md) for commands, results, source evidence and limits. Pretrained weights alone are not established as the cause; bounded voxelization and the original input/training contract are next.
