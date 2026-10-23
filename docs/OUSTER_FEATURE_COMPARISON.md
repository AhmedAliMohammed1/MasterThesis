# Ouster input-feature comparison

> **Status reviewed 23 October 2026.** The recorded comparison remains 192 observations, including 15/48 raw-signal rejections and 0/144 rejections across normalized variants. Full reflectivity_div255 replay matched 556/556 occurrences. These results demonstrate numerical/message-flow improvement, not calibrated features or detection accuracy. [Current results and evidence](CURRENT_STATUS_AND_RESULTS.md).

Measured on 13 October 2026. **The unscaled Ouster signal is a demonstrated contributor to numerical failures in this model.** Changing only the fourth input feature removed infinite box lengths in all tested normalized observations and sharply reduced the excessive predictions. This establishes a numerical/input improvement on these recordings, not detection accuracy or an accepted sensor calibration.

## What the sensor fields mean

The [official Ouster ROS point definition](https://github.com/ouster-lidar/ouster-ros/blob/master/include/ouster_ros/os_point.h) identifies its FLOAT32 `intensity` as **signal**, with a separate `reflectivity` field. [Ouster's sensor documentation](https://static.ouster.dev/sensor-docs/image_route1/image_route2/sensor_data/sensor-data.html) distinguishes signal photons from range/sensitivity-compensated reflectivity. Reflectivity codes 0–100 map linearly to diffuse-target reflectivity percentages; 101–255 use a nonlinear mapping for retroreflectors. Firmware/profile and factory-calibration status were not included in these bags.

[NVIDIA's TAO PointPillars input documentation](https://docs.nvidia.com/tao/tao-toolkit/6.26.03/text/cv_finetuning/pytorch/point_cloud/pointpillars.html) specifies a fourth feature between 0 and 1. The existing detector scale 1.0 passed Ouster signal values up to 9,059 directly to the network. A full scan audit found recorded reflectivity in 0–255, despite UINT16 storage.

Four conversions were compared:

| Variant | Fourth feature | Meaning and limit |
| --- | --- | --- |
| `raw_signal` | Original FLOAT32 intensity | Frozen baseline; values far outside the documented model feature range |
| `signal_div65535` | Signal / 65,535 | Numeric-range control inspired by a 16-bit signal representation; actual profile is unavailable, and this is not calibrated reflectance |
| `reflectivity_div255` | Reflectivity code / 255 | Bounded 8-bit encoding; **not a physical linear reflectance fraction**, because the source mapping is nonlinear |
| `reflectivity_fraction` | min(reflectivity / 100, 1) | Diffuse-target fraction with retroreflectors clipped; neither that clipping nor exact training-feature equivalence is established |

No conversion uses the maximum observed value or a per-scan normalization. None has been selected by labeled accuracy. A small output count is not a reason to declare one variant correct.

## Controlled experiment

Eight scan indices evenly spaced from first to last in each original bag were frozen: **16 scans × four variants × three repeats = 192 lossless raw inferences**. Original CDR bytes and packed inputs were saved and hashed. Every variant preserved XYZ bits, point order and point count (32,768). Zero-return points were intentionally retained so that only the fourth feature changed. The engine/image identities were fixed, and the deployment engine volume was read-only.

The existing TensorRT 10 diagnostic runner executed the same production engine, saved actual FLOAT32 candidate rows (including invalid values), and checked output counts. The current CPU NMS source was compiled unchanged and applied with IoU 0.01, top-N 4096, class-agnostic suppression and no additional confidence threshold. Any invalid candidate rejects the entire observation, matching the deployment's output-contract behavior; invalid rows were not silently filtered before NMS.

| Feature | Observations rejected by output contract | Invalid raw rows | Median final boxes, accepted observations | Median of final-score medians |
| --- | ---: | ---: | ---: | ---: |
| Original signal | 15 / 48 | 33 | 590 | ≈1.000 |
| Signal / 65,535 | 0 / 48 | 0 | 15 | 0.164 |
| Reflectivity / 255 | 0 / 48 | 0 | 18.5 | 0.166 |
| min(reflectivity / 100, 1) | 0 / 48 | 0 | 26 | 0.173 |

All 33 invalid raw rows had **nonfinite length**; no other component was nonfinite, and no nonpositive dimension was found. The raw baseline's box-count statistic excludes its 15 rejected observations. Each normalized variant's count includes all 48 observations. Lower scores after normalization are not worse calibrated accuracy: the earlier near-1.0 values were saturated predictions on incompatible inputs, not proof of correct detections.

Median one-to-one repeat matching of valid raw rows at the diagnostic 0.001 component tolerance was 78.91% for original signal, 98.19% for signal/65,535, 98.72% for reflectivity/255 and 98.92% for clipped reflectivity fractions. This is a repeatability measurement, not exact numerical parity or an agreed accuracy criterion. Invalid raw rows were excluded only from that repeat-matching metric, while whole-frame rejection remained in the deployment/NMS comparison.

## Remaining input concerns

The selected scans occupied 2,031–2,907 pillars, below the 10,000-pillar limit, so there was no total-pillar-capacity overflow in this selected experiment. They still had 6–63 pillars above 32 points. Each selected scan also contained 13,206–15,775 zero-range, zero-XYZ points. These are retained in every variant and require a separate sensor-return/point-selection investigation. Their removal would change another factor and was deliberately not mixed into this feature experiment.

The dataset has no object-detection labels. Sensor geometry, training-domain compatibility, zero-return handling, remaining repeat variation and the earlier KITTI vertical error remain unresolved. High precision/recall, corrected box placement or deployment reliability cannot be inferred from this table.

## Reproduce and replay

The comparison needs host ROS Jazzy Python packages, NumPy, g++, Docker/GPU access, the existing `pp-infer:reference-trt10` image and the baseline production container named `pointpillars`. It verifies the recorded image/engine hashes. No retraining, engine rebuild, or host SDK installation is performed.

```bash
source /opt/ros/jazzy/setup.bash
python3 tools/compare_ouster_features.py
python3 tools/compare_ouster_repeats.py
```

Default observations live under ignored `.recovery/accuracy/ouster-feature-v1`. Completed raw files are indexed by hash and reused only after verification. Changed source/configuration requires a fresh `--output` directory. Interrupted unindexed raw outputs are preserved and require inspection/a fresh directory. The report, recipe, input snapshots, binary raw/final boxes, inference logs and repeatability report are retained; back them up separately from Git. The direct raw/NMS comparison is separate from the actual ROS replay check.

For an **explicit diagnostic replay** with the bounded reflectivity encoding:

```bash
PP_OUSTER_FEATURE=reflectivity_div255 bash tools/rosbag_ouster.sh
# In another terminal:
RVIZ_CONFIG="$PWD/rviz/ouster.rviz" bash tools/visualize.sh
```

Stop any existing player on the same input topic/domain first. The helper creates a cloud-only derived bag under `.recovery/rosbags/ouster_calibration_v3/derived/reflectivity_div255/`. It verifies that every byte outside the FLOAT32 intensity slots, all metadata, and recorded timestamps are preserved. Source bags remain untouched. Its manifest records conversion/source hashes and states that training calibration and accuracy are unvalidated.

`PP_OUSTER_FEATURE=raw_signal` remains the baseline default. Other tested variants can be selected explicitly using the names in the table. The playback launcher gives subscribers two seconds to discover publishers before playback (`PP_BAG_DELAY`). The normalized detector should retain intensity scale **1.0**, avoiding a second division of already converted values. Confidence and NMS thresholds remain unchanged.

An initial full-bag verifier counted unique headers and incorrectly treated duplicate source timestamps as missing messages. The source contains 291 messages with 289 unique headers in the first bag and 265 messages with 264 unique headers in the second. The corrected verifier counts message occurrences separately and preserves source timestamps; the initial verifier outputs remain saved for the audit trail.

## Complete ROS replay results

The explicit `reflectivity_div255` candidate was replayed through the unchanged production ROS node/engine on isolated domain 99, at recorded speed with a two-second discovery delay:

| Recording | Input occurrences | Matching output occurrences | Median boxes | Median score |
| --- | ---: | ---: | ---: | ---: |
| First | 291 | 291 | 21 | 0.1644 |
| Second | 265 | 265 | 15 | 0.1673 |

**All 556 occurrences matched; no invalid message fields, feature-conversion discrepancies or detector log errors were recorded.** The verifier checked actual published intensity against FLOAT32 reflectivity/255 and counted repeated headers separately. This confirms numerical/message-flow improvement across both complete recordings; it does not certify object correctness, training parity, synchronized external clocks, or real-time acceptance. Test playback and the temporary detector were stopped, and the original detector was retained.

Nine focused input/archive/feature controls passed, including preservation of negative-zero XYZ bits, point order/count, header, row padding and all non-intensity bytes. Python compilation, Bash syntax and source-diff whitespace checks passed. Exact hashes, the 192 raw observations, complete native replay records, original failed unique-header verifier records, engine/image identity and summary are indexed by `config/ouster_feature_inventory.json`. Original raw-bag measurements remain in `config/ouster_demo_inventory.json`.
