# KITTI accuracy baseline and live RViz comparison

On 3 October 2026, the current deployed PointPillars node was measured on the 32 frozen labeled KITTI diagnostic frames. **The baseline is poor. There were no accepted 3D matches on the 16 test frames at KITTI's class-specific overlap thresholds.** Some cars and cyclists matched in bird's-eye view. Integration and visualization work, but this model/runtime combination has not passed accuracy acceptance.

This measurement uses original XYZI values, intensity scale 1.0, the existing FP32 engine, class-agnostic NMS at 0.01 and pre-NMS top-N 4096. No confidence tuning, intensity rescaling or coordinate shift was applied after inspecting results. The first observed detections for each frame were saved and hashed; subsequent live playback does not overwrite them.

## Test results

The primary table is the **16-frame test split, moderate difficulty**. The separate 16-frame tuning split is retained in the full report. The splits share no original recording drive. Both were selected from annotations to cover varied scenarios before predictions were inspected.

| Evaluated class | Valid GT | 3D TP / FP / FN | 3D AP_R40 | BEV TP / FP / FN | BEV precision | BEV recall | BEV AP_R40 |
|---|---:|---|---:|---|---:|---:|---:|
| Car, from model Vehicle | 54 | 0 / 146 / 54 | 0.00% | 12 / 128 / 42 | 8.57% | 22.22% | 5.75% |
| Pedestrian | 31 | 0 / 53 / 31 | 0.00% | 0 / 53 / 31 | 0.00% | 0.00% | 0.00% |
| Cyclist | 19 | 0 / 206 / 19 | 0.00% | 2 / 203 / 17 | 0.98% | 10.53% | 0.0258% |

TP means a valid matched detection, FP an unmatched counted detection, and FN a missed counted annotation. BEV measures the footprint from above; 3D also requires vertical overlap. Precision/recall counts here use every published prediction surviving the camera-visibility and official difficulty/ignore rules. AP uses score-ranked thresholds from the upstream KITTI evaluator. Small class populations make AP_R40 particularly sparse, so direct counts are essential context.

The tuning split also has zero moderate 3D true positives. Moderate BEV counts are Car 5 TP / 173 FP / 14 FN, Pedestrian 0 / 33 / 49, and Cyclist 1 / 103 / 18. Its BEV AP_R40 is about 0.658%, 0%, and 0%, respectively. No parameter selection was performed using either split.

The full report preserves easy/moderate/hard results for 3D and BEV, per-frame counts, and overlapping scenario breakdowns. The [accuracy inventory](../config/kitti_accuracy_inventory.json) records exact identities, commands, evidence hashes, findings and limits. The actual report is under `.recovery/accuracy/kitti-baseline-v1/evaluation/report.json`; large/local evidence is ignored and needs an independent backup.

## What these scores mean

The explicit mapping is model ID 0 Vehicle → KITTI Car, ID 1 → Pedestrian, and ID 2 → Cyclist. This is a **Car compatibility measurement**, not a measurement of every vehicle. Original Van, Truck, Person_sitting and DontCare labels remain unchanged; we use the corresponding upstream neighboring-class/ignore behavior. We do not merge all vehicles into Car and present the result as an official leaderboard score.

The tool extracts metric routines from the SHA256-pinned official KITTI development kit. Overlap, cleanData, matching, difficulty and score-threshold routines are unchanged. A small adapter reads our actual frame IDs and writes JSON; it does not run the upstream server submission, email, plotting or deletion code. AP_R40 averages precision entries 1–40 from the upstream 41-entry array. Car overlap is 0.7; Pedestrian/Cyclist overlap is 0.5. The [KITTI benchmark](https://www.cvlibs.net/datasets/kitti/eval_object.php?obj_benchmark=3d) explains the protocol and requires student/reimplementation work to evaluate a training-set split.

Predictions are converted into KITTI's rectified-camera format using each frame's calibration. Centers transform exactly. Camera yaw is fitted from the transformed length-axis heading, dimensions remain length/width/height, and camera y gets half the height to represent KITTI's bottom center. KITTI's upright, yaw-only representation cannot retain a LiDAR box's small calibration tilt; that approximation is declared in the policy. Ground-truth reports retain their complete orientation and corners.

Visibility uses actual calibrated prediction corners, clipping edges at the near plane and bounding rectangles to the matching image. A nonempty camera rectangle is required. Across 32 frames there were 2,876 final ROS predictions: 862 were camera-visible and 2,014 were excluded from this camera-labeled evaluation. RViz still displays all predictions, so a box behind the sensor is not automatically a counted false positive in this report. There is no extra model-range filter that removes inconvenient ground truth.

This is a deliberately varied **diagnostic sample**, not an unbiased population score, a public KITTI submission, or evidence for the user's future sensor. NVIDIA's exact pretrained training-frame list is unavailable, so pretrained overlap is unknown. Accuracy targets and a larger acceptance design remain unagreed.

## Findings and checks

For the 12 test-set car pairs that match BEV at the required overlap, the median predicted center is about **1.53 m above** the ground truth in rectified-camera vertical coordinates. Their median 3D IoU is about 0.043. For the two matched cyclists, the median vertical error is about 1.46 m. This describes a small matched subset; it does not establish one correct global translation for every class or frame. The preparation report also shows many ground-truth boxes partly outside the export's z range.

A separate NVIDIA `trtexec` execution used the same engine and one exact padded input frame, 005876. It emitted 528 raw candidates with median z about 0.714 m. The saved ROS output contained 68 final boxes with median z about 0.706 m. Forty-six ROS boxes had a same-class raw candidate within 0.001 in every compared component after wrapping yaw. This supports the finding that elevated centers already appear before the ROS display. It does **not** certify full independent inference or postprocessing parity: both executions share the engine/plugins, the JSON floats are rounded, matching is not one-to-one, and repeated execution varies.

During repeated live inference, final counts varied for 31 of the 32 observed frames, with a maximum observed span of seven boxes. First-pass measurements remain frozen. Numerical repeatability and an independent original-model/reference comparison are unfinished. We cannot yet attribute all poor performance to the pretrained model rather than plugin/runtime or input-domain differences.

Six evaluator controls passed: known camera conversion, outside-camera filtering, near-plane clipping, exact boxes giving 100% 3D/BEV AP_R40, missing predictions giving all false negatives, and duplicates counting false positives. All 41 Python tests passed, including the earlier dataset/recovery tests. The report was rerun from frozen inputs and reproduced. RViz startup and actual desktop rendering of points, predictions and green calibrated ground truth were verified.

The next investigation is to establish the export's original input/reference behavior, check the sensor origin/height/domain against its training contract, and verify plugin/preprocessing parity. Then choose a documented input adaptation or a KITTI-trained/fine-tuned model using tuning data and evaluate on a larger untouched split. We did not guess a z shift from test results, lower overlap thresholds, or call a poor baseline a pass.

## Reproduce the measurement

First complete the existing driver/Docker/ROS setup and build the inference image. Host ROS Jazzy with rclpy, sensor/vision/visualization messages is required by the player. The evaluator additionally needs a compiler and Boost headers:

```bash
sudo apt install build-essential libboost-dev ros-jazzy-vision-msgs \
  ros-jazzy-visualization-msgs
```

Those dependencies were already available on the current computer; no host package installation was performed for this measurement. Python data preparation still requires only the standard library.

From the project folder:

```bash
bash tools/kitti_accuracy.sh prepare
bash tools/kitti_accuracy.sh collect
bash tools/kitti_accuracy.sh report
```

The wrapper starts a dedicated `pointpillars-validation` container on ROS domain 42, remapping the input and output to `/kitti/point_cloud` and `/kitti/predictions`. It uses the already-built image; it does not build or publish uncommitted source. It checks image, model and node settings before recording runtime identity. The default output is `.recovery/accuracy/kitti-baseline-v1`.

An active player prevents starting another in the same domain. Stop the current player before `collect` or use the saved report command directly. If runtime identity, exporter code or frozen recipe differs, use a new `PP_KITTI_OUTPUT` folder. Never silently overwrite an earlier measured run. A completed first observation is reused; an interrupted pass saves completed frame outputs and resumes the missing ones.

For a new measurement directory:

```bash
PP_KITTI_OUTPUT="$PWD/.recovery/accuracy/kitti-repeat-v1" \
  bash tools/kitti_accuracy.sh collect
PP_KITTI_OUTPUT="$PWD/.recovery/accuracy/kitti-repeat-v1" \
  bash tools/kitti_accuracy.sh report
```

Keep input/model/postprocessing settings fixed when interpreting repeat differences. Repetition does not turn the small diagnostic set into independent acceptance data.

## Live RViz comparison

In one terminal, run live inference/playback:

```bash
bash tools/kitti_accuracy.sh live
```

In another:

```bash
bash tools/kitti_accuracy.sh view
```

Green edges show original calibrated ground-truth boxes. Prediction colors identify model IDs: orange Vehicle, blue Pedestrian, yellow Cyclist. Point colors show intensity. White text identifies the current KITTI frame and split. Points and boxes use `velodyne`, so no world transform is invented. A global TF warning can remain in this sensor-frame-only view.

Use the mouse to move around, or disable **Detections** or **Ground truth (green)** to inspect one layer at a time. Playback defaults to three seconds per frame and loops the fixed set. Live inference is repeated; the scoring report continues to use the first saved observation. This is direct labeled-frame playback, not conversion into a new rosbag. The old bag/video/viewer workflow remains available separately.

RViz and live inference were left running after implementation. The helper records identities of its detector/player/viewer so this command stops those resources without touching unrelated containers or applications:

```bash
bash tools/kitti_accuracy.sh stop
```

For manually started instances with no matching ownership record, stop the intended process/container explicitly after inspection. Default stop targets domain-42 validation resources; it does not stop the ordinary deployment or the earlier bag player.

Optional descriptive diagnostics and the one-frame utility probe are reproducible:

```bash
python3 tools/kitti_diagnose.py \
  --dataset ../datasets/kitti_object_diagnostic_v1 \
  --evaluation .recovery/accuracy/kitti-baseline-v1/evaluation \
  --output .recovery/accuracy/kitti-baseline-v1/diagnostics
python3 tools/kitti_reference_probe.py \
  --dataset ../datasets/kitti_object_diagnostic_v1 \
  --predictions .recovery/accuracy/kitti-baseline-v1 \
  --output .recovery/accuracy/kitti-baseline-v1/reference-reviewed
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The utility probe requires the running validation detector and its cached engine. It is an exploratory consistency check whose output can change between executions; preserve earlier probe files if comparing runs. It is not the full reference-parity acceptance test.

## Status after measurement

Data preparation, calibrated ground-truth playback, prediction export and a diagnostic accuracy baseline are implemented. **Accuracy acceptance is not achieved.** Independent original-model parity, repeatability investigation, larger evaluation data/targets, runtime contract enforcement, the bounded worker, QoS/metrics, memory/failure checks, performance benchmarks and CI remain. Source tools and documentation are local edits until the user commits and pushes them; Docker continues to build the published Git source.


## Independent reference update: 3 October 2026

A separate TensorRT8.6 engine for the exact ONNX reproduced the poor KITTI baseline and approximately1.53m upward car error. Three repeats per runtime (192 raw inferences) still produced zero moderate 3D matches in both runtimes. NVIDIA's unchanged NMS and our NMS selected identical boxes on all192 same-candidate observations. Strict numerical parity remains unmet: both runtimes vary, and12 frames exceed the export's10,000-voxel limit. Two tuning-only capacity controls improved repeat matching to roughly99.6–100%; no production adaptation was installed. Two actual CUDA12.9 allocation probes reported zero errors, which does not clear the internal tensor-bounds concern or complete GPU memory validation. Read [independent comparison](MODEL_REFERENCE_COMPARISON.md) for commands, results, source evidence and limits. Pretrained weights alone are not established as the cause; bounded voxelization and the original input/training contract are next.
