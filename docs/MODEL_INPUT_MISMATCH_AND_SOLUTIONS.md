# Model/input mismatch and detection improvement options

Reviewed 21 November 2026. Three specialist subagents independently reviewed the
model contract, input algorithms/geometry and alternative detector families. The
parent ran fresh controlled GPU trials. The live raw01 adapter/detector/RViz were
preserved; the player was verified at rate 1.0. This report proposes experiments,
not an accepted accuracy repair.

## Finding

The current ROS adapter produces a compatible tensor layout. Low confidence is
not explained by the presence of extra Ouster fields or by ONNX as a file format.
The leading concerns are dense-pillar point selection, unknown physical intensity
alignment, unverified target/training domain and unverified mounting coordinates.
Model confidence, probability calibration, repeatability and correct 3D detection
are separate outcomes. More or higher-score boxes can be more confident mistakes.

## Exact model versus current data

The actual ONNX was parsed read-only and its SHA-256 matched both the local model
and `/opt/models/pointpillars.onnx` in the running image:
`2dcabddc3a365e9608a112d7bbbb7db769a6dddeeaa59aa03611a83113326da1`.
Inference uses the cached TensorRT engine built from this model.

| Contract | Model / runtime expectation | Primary-bag observation |
| --- | --- | --- |
| Features | FLOAT32 x,y,z,intensity, exactly four features | Raw FLOAT32 XYZ, UINT16 signal, UINT8 reflectivity; adapter writes FLOAT32 XYZI |
| Tensor | Batch 1, capacity 204800 points, INT32 actual count | 131072 organized raw points; finite points packed with correct count and zero padding |
| Coordinates | TAO documents metres, x forward/y left/z up at LiDAR origin | Frame named ouster1_lidar; numerical XYZ passed unchanged; physical orientation/extrinsics unverified |
| ROI | XY about ±51.2m, z [-1.4,4.4)m | Most finite sampled points inside; lower-z clipping alone is not established as the primary cause |
| Pillars | 0.2m XY, full-height pillar; max 10000, max 32 points each | 2893–3079 pillars, but 583–601 pillars per scan exceed 32 points |
| Intensity | TAO guidance [0,1]; exact training calibration absent from ONNX | Reflectivity/255 is bounded, not demonstrated equivalent to training reflectance |
| Classes | Vehicle, Pedestrian, Cyclist | No labels available for the ten sampled scans; presence of supported targets unconfirmed |
| Decoder | Geometric box centers; embedded score floor about 0.1 | ROS copies centers correctly; ROS gate is 0.4 |
| NMS | Current class-agnostic rotated BEV IoU threshold 0.01 | Verified configuration; effect on target recall unmeasured |
| Training domain | Exact v1.1 provenance not fully established | Publisher model-level card describes proprietary solid-state LiDAR; no verified Ouster match |

The current adapter is not a coordinate transformer or motion compensator. Extra
raw channels (ring, time, range, near-IR, flags) are intentionally not inputs to the
four-feature export. Adding them requires a different trained model and interface.
Changing RViz frame text or generic class labels does not change network scores.

Saved tiny packaged-plugin GPU tests pass the ten derived features and limited
Vehicle decoder center-z cases. Earlier TensorRT8 results also had poor geometry.
These checks narrow likely bugs but do not establish full training-framework parity.
Some older manifest fields still say decoder parity is pending; the newer tests
cover specific fixtures, not the full unknown original training pipeline.

## New geometry and GPU experiments

Five scans from each recording were reused from the frozen primary-bag selection.
No new independent scenes were added. A within-pillar audit shows that first32
raises mean z by a median **0.2665–0.3032m** in overfull pillars; 98.66–99.00% of
these pillars shift upward. Median retained/full vertical span is 35.28–40.34%.
This proves selection bias, not that it caused inaccurate boxes. CPU first32 and
CUDA atomic encounter order are different policies.

The parent executed **180 measured inferences plus two excluded warmups**:
six variants × ten scans × three repeats. The same active engine and production
runtime/NMS were used, jobs shuffled with seed 20261121, no coordinate shift or
weight change. All 180 succeeded. Fourteen focused point-policy/reference/voxel CPU
tests also passed. This is separate from the preceding 120-inference experiment.

| Variant | raw01 accepted events ≥0.4 | ouster1 accepted events ≥0.4 | Median candidate repeat matching |
| --- | ---: | ---: | --- |
| Baseline reflectivity/255, all finite points | 2 | 11 | 8.57% / 8.33% respectively |
| First 32 per pillar | 0 | 6 | 100% in each bag |
| Evenly spaced source-order indices per pillar | 0 | 3 | 100% in each bag |
| Fixed-seed random points per pillar | 0 | 3 | 100% in each bag |
| Farthest XYZ points per pillar | 0 | 3 | 100% in each bag |
| First32 + min(reflectivity/100,1) | 3 | 3 | 100% in each bag |

Each cell counts events over 15 inferences, not unique objects. Matching compares
repeats with repeat 0 at component tolerance 0.001. Stable bounded results are
not necessarily bit-identical. Baseline variation across experiments is consistent
with its measured repeatability problem. Spatial sampling preserves actual points;
farthest-point selection may favor noise. The intensity control reconstructs exact
8-bit reflectivity codes from the saved float32 encoding before rescaling.

No policy consistently improved confidence across both bags. Clipped /100 causes
one raw01 sampled scene to cross the score gate, repeated three times, but reduces
accepted events on ouster1. It is not a supported new production default. The earlier
signal/65535 control produced no accepted boxes in either bag's sampled trials.
Labels are required to decide whether any of these events represents a real object.
GPU trials overlapped live inference; timings are not performance benchmarks.

## Practical solution space

### Correct and stabilize the existing model input

1. **Use an explicit capacity-compliant live policy.** Integrate the existing C++
   helper as opt-in, compare first32/even/random/spatial selection using labels,
   report removed points and match CPU/GPU preparation. Do not equate deterministic
   selection with accuracy. Reject or explicitly handle pillar overflow.
2. **Verify physical coordinates.** Recover sensor configuration, actual frame
   convention, mounting height/roll/pitch/yaw and independent gravity/ground estimate.
   Apply confirmed input transforms and transform predictions back. Ouster's Sensor
   and LiDAR frame conventions can differ; a frame name alone cannot establish axes.
3. **Calibrate the fourth feature.** Compare documented reflectivity mappings,
   /255 baseline, /100-clipped control, constant-intensity ablation and physically
   justified signal mappings. Verify firmware/calibration before interpreting codes.
   Do not fit scaling on held-out labels or maximize unlabeled scores as the objective.
4. **Validate the full original execution contract.** Obtain a trusted publisher
   input/output fixture or training-framework reference; compare voxel membership,
   derived features, scatter, network residuals and decoder. Test crowded pillars
   and ROI boundaries. ONNX shape compatibility alone cannot establish this parity.
5. **Filter only measured artifacts.** Test sensor-body masks, invalid-return,
   range-image, statistical or radius filters separately. Aggressive denoising can
   remove sparse object returns. Ground estimation is useful immediately; removing
   ground may hurt a detector trained with it and must be evaluated independently.
6. **Deskew where justified.** Use synchronized per-point time, IMU/odometry and
   extrinsics if the sensor moves and clouds are not already compensated. These two
   MCAP summaries contain only the point-cloud topic, so motion data must come from
   another verified source. Do not invent ego-motion or deskew twice.

### Improve the trained detector

7. **Fine-tune PointPillars on target Ouster data.** Label supported objects across
   range, occlusion, mounting and environment. Start from a verified compatible
   training checkpoint, adapt preprocessing/anchors/ROI/augmentation, then re-export
   ONNX and rebuild TensorRT. A local `pointpillars_trainable.tlt` file exists, but its
   loadability, decryption requirements and version compatibility were not verified.
   The deployed ONNX is not an ordinary training checkpoint.
8. **Retrain/configure a better representation.** Change pillar/voxel size or limits,
   vertical representation, anchor priors or use an anchor-free head. Match training,
   export plugins, scatter and decoder. Merely editing ONNX attributes is not a
   validated substitute for training; it can break spatial/learned assumptions.
9. **Improve supervision and adaptation.** Use recording-disjoint splits, class
   balance, hard-negative mining, target beam/dropout/intensity augmentations and
   active learning. Mixed-domain training, self-supervised pretraining, teacher
   distillation and cautious pseudo-label adaptation can reduce labeling effort.
   Current weak predictions are unsuitable as unquestioned ground truth.
10. **Use more information where available.** A newly trained multi-feature model
    could exploit reflectivity, signal, range or near-IR; camera–LiDAR fusion needs
    synchronized images and calibrated extrinsics. Current bags alone do not provide
    a verified camera stream. These are model/interface changes, not a fifth-column patch.

### Alternative algorithms to benchmark

| Candidate | Purpose | Main cost / limitation |
| --- | --- | --- |
| Independent OpenPCDet PointPillars | Separate current TAO implementation/weights from the algorithm | Its checkpoint still needs matching coordinates and target evaluation |
| Target-fine-tuned PointPillars | Lowest-change learned challenger | Requires compatible checkpoint and labeled Ouster training data |
| CenterPoint-Pillar | Anchor-free challenger reducing fixed-anchor dependence | Own preprocessing, weights and decoding; no drop-in TAO engine compatibility |
| SECOND / CenterPoint-Voxel | Preserve more vertical structure | Sparse operators, memory and deployment effort |
| PV-RCNN / Voxel R-CNN | Offline accuracy reference or teacher | Greater compute/deployment cost; 8GB feasibility must be measured |
| DSVT-Pillar | Transformer-based alternative with official deployment example | Port/version/memory work; checkpoint/data terms need checking |
| Range-view detector | Use organized LiDAR structure | Different representation/training and integration; Ouster YOLO demos are not proof of equivalent oriented 3D detection |
| Ground segmentation → clustering → oriented boxes | Independent obstacle/geometry baseline | Weak semantics, split/merge/occlusion errors; cluster confidence is not neural class probability |

No alternative neural network was executed in this review. Three subagents researched
these choices; the actual GPU runs tested preprocessing algorithms on the current
network. Checkpoint suitability, export compatibility and RTX4060 8GB latency/memory
remain unverified. Train or benchmark challengers sequentially with isolated outputs.

### Improve decisions and temporal use

11. **Tune postprocessing on labels.** Compare class-aware NMS and IoU thresholds,
    class/range-specific operating gates and possibly soft-NMS/box merging. Current
    0.01 class-agnostic NMS may suppress adjacent objects. NMS changes retention,
    not the neural score or systematic box-height error.
12. **Calibrate score reliability.** Fit temperature/Platt/isotonic calibration on
    labeled tuning data, evaluate calibration on held-out data, and use precision/
    recall targets for operating thresholds. Raising displayed numbers does not
    improve localization. A ROS gate below about 0.1 cannot recover anchors already
    discarded by the model's decoder.
13. **Add temporal evidence.** Track confirmed objects, apply motion gating and
    track-level score fusion. Distinguish track confidence from single-scan scores.
    Multi-sweep aggregation requires ego-motion compensation, moving-object handling
    and rechecking point/pillar capacity; naive accumulation can create ghost objects.
14. **Fix freshness and transport separately.** Measure bag publication, adapter
    reception, detector processing, drops and matching timestamps. Replace large
    backlog behavior with explicit latest-frame scheduling only after measuring it.
    Replay gaps affect apparent smoothness but do not explain weak offline scores.
15. **Optimize deployment after correctness.** FP16, pruning, distillation, quantization
    or smaller ROI may improve runtime and memory. They are not confidence fixes and
    require accuracy checks. Current FP32 results already demonstrate the mismatch.

## Recommended next sequence

1. Confirm which Vehicle/Pedestrian/Cyclist targets are physically present; annotate
   a small development set and a separate recording-disjoint acceptance set. Split
   by recording/session, not adjacent frames. If both bags share the same collection,
   collect a genuinely independent acceptance session.
2. Verify coordinate/mounting and feature semantics; obtain original reference parity.
3. Compare stable sampling policies on labeled development data, then add the selected
   policy as an explicit opt-in live mode with diagnostics and parity tests.
4. Establish independent PointPillars plus a ground/clustering baseline; compare
   target-fine-tuned PointPillars and CenterPoint-Pillar. Use a voxel model as an
   offline teacher/reference if justified by results.
5. Lock preprocessing/model/NMS/gates, evaluate once on held-out data, and only then
   optimize real-time behavior. Report precision/recall, BEV/3D overlap, class/range
   breakdown, calibration, repeatability and latency separately.

The current evidence supports input stability work and target-domain evaluation.
It does not support a universal height shift, score multiplier, blindly larger
ONNX ROI, or declaring more boxes to be better detections.

## Evidence and primary sources

- Local exact contract: `config/model_contract.json`; model parser and production
  adapter/runtime sources. New numerical report: `config/detection_algorithm_review.json`.
- New raw inputs/outputs, scripts, source identities and hash index:
  `.recovery/verification/algorithm-review-20261121/` (ignored; back up separately).
- [NVIDIA TAO input/training documentation](https://docs.nvidia.com/tao/tao-toolkit/6.26.03/text/cv_finetuning/pytorch/point_cloud/pointpillars.html).
- [NVIDIA model card](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/tao/models/pointpillarnet).
- [Ouster reflectivity documentation](https://docs.ouster.com/sensor-docs/firmware/calibrated-reflectivity),
  [Ouster coordinate documentation](https://static.ouster.dev/sensor-docs/image_route1/image_route2/sensor_data/sensor-data.html).
- [OpenPCDet](https://github.com/open-mmlab/OpenPCDet),
  [CUDA-PointPillars](https://github.com/NVIDIA-AI-IOT/CUDA-PointPillars),
  [CenterPoint](https://github.com/tianweiy/CenterPoint),
  [DSVT](https://github.com/Haiyang-W/DSVT),
  [RangeDet](https://github.com/tusen-ai/RangeDet).
- [Ouster YOLO demo](https://github.com/ouster-lidar/ouster-yolov5-demo),
  [PCL clustering](https://pointclouds.org/documentation/tutorials/cluster_extraction.html),
  [Patchwork++](https://github.com/url-kaist/patchwork-plusplus),
  [ST3D adaptation](https://github.com/CVMI-Lab/ST3D).
