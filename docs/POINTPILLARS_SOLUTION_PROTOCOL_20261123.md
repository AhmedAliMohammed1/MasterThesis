# PointPillars diagnosis and deterministic solution protocol — 23 November 2026

No tested configuration has yet solved pedestrian 3D detection. The concrete next path is independent full-box labeling, verified coordinate/feature compatibility, and a compatible trained model or Ouster fine-tuning if the current checkpoint still fails. This is an executable decision sequence, not a promise that another intensity divisor, height offset or threshold will work.

The user's acceptance requirement is **“undecided, but should be improved from the current state.”** Compare with the frozen current baseline across precision, recall, false positives per frame, localization, distance and occlusion strata, repeatability and latency. Absolute operating-distance and acceptance targets remain pending. A score increase or a newly visible box is not sufficient evidence of improvement; conflicting metric changes must be reported, not collapsed into a passing verdict.

## Project and present problem

The ROS 2 Jazzy application converts LiDAR clouds into FLOAT32 XYZI, executes a pretrained PointPillars TensorRT engine and publishes Detection3DArray boxes and diagnostics for RViz. `src/ouster_adapter.cpp` selects and normalizes an Ouster channel; `src/pp_inference_node.cpp` packs input and synchronously invokes the runtime. GPU inference and decoding are followed by CPU rotated BEV NMS and the output confidence gate. `src/detection_output.cpp` owns per-frame/cumulative monitoring. Docker provides dependencies and model; a persistent engine cache avoids rebuilding for unchanged model/GPU identities. Raw bags, measurements and labels are separate from source control.

The production callback still uses reliable depth 700; there is no latest-frame worker. `src/point_policy.cpp` offers offline bounded preparation; the live callback does not call it. Its first32 selection can remove useful lower-body points. Fixing reproducibility alone cannot establish recognition or correct 3D placement.

Reflectivity/255 is the comparison baseline. The later clipped/100, gate-0.3 preview is diagnostic, not an accepted replacement. Historical notes about an active process or the `New Volume1` mount must be rechecked: the resumed checkout is `/media/ae/New Volume/MasterThesis`.

## What the latest evidence actually says

The preserved [22 November investigation](/home/ae/.codex/visualizations/2026/11/21/01a1fdf3-f289-76b1-9a56-9b376b45aaeb/deterministic-investigation/REPORT.md) is stored outside this checkout; use the absolute path below if this external local link is unavailable:

`/home/ae/.codex/visualizations/2026/11/21/01a1fdf3-f289-76b1-9a56-9b376b45aaeb/deterministic-investigation/REPORT.md`

It records **60 height trials plus 18 height-quantile follow-ups**, all completed. None produced a post-NMS Pedestrian box containing both selected landmarks, at any stored score. The exact cloud is ouster1 zero-based frame 1403, bag record `1794397517854145698 ns`, offset `70.05539416 s`, CDR SHA256 `bc4b08c105662e570aa73923710874515c1833d6ccfa6b79c01fb409be260117`. Header timestamps wrap/repeat; they alone are not unique identifiers. The lower landmark is not a verified foot or ground point.

A +1 m shift raised some nearby candidate scores above .3 after inverse transformation, but did not recover landmark coverage. Follow-ups were selected after earlier results, so these are development experiments. A nearest candidate may change identity between variants. This is not a full-box precision/recall measurement or 78 independent scenes. CPU first32 dropped the lower landmark at source rank 313/317 in its pillar while retaining the head at 26/231; that establishes a CPU-control information-loss mechanism, not the exact CUDA plugin's point choices. The reviewed application path did not establish a center/half-height bug. Earlier decoder checks covered Vehicle arithmetic, not every class/anchor.

The separate [person solution trials](PERSON_DETECTION_SOLUTION_TRIALS.md) include 30 pre-NMS observations on ten scans and 240 paired CPU NMS controls. No hidden nearby class1 score ≥.4 appeared in that frozen even-order selection. This narrows one explanation for those scans; it does not exclude NMS issues elsewhere. Do not repeat this as an untested new experiment or as measured person recall.

The exact v1.1 training sensor, mounting height and physical intensity calibration remain unestablished. Independent labels and a never-tuned recording/session are still required. Existing repeatedly inspected Dur360 test examples are development evidence for further model selection.

## A–Z sequence with artifacts and decision gates

Each step produces a saved artifact in a new experiment directory. Failure or missing information stops dependent steps; it never becomes an automatic pass. Preserve rejected variants and raw outputs.

| Step | Action and required output | Decision gate |
| --- | --- | --- |
| A | Inventory Git status, instructions, source, bags and current processes; save a read-only state manifest. | Preserve unrelated edits and prove identities before any process action. |
| B | Freeze baseline ONNX, engine, image, runner, preprocessing, thresholds and source hashes. | No baseline comparison with an unknown or changing artifact. |
| C | Index original scans by recording, stream, record timestamp, ordinal and CDR hash. | Uniquely recover every evaluated scan despite repeated headers. |
| D | Define classes, coordinate conventions, ROI, box origin, occlusion/ignore rules and matching policy in a versioned annotation guide. | Ambiguous label semantics resolved before annotation. |
| E | Independently annotate complete oriented 3D boxes for all target objects in selected positive and negative scenes, including occlusions. Preserve original clouds and annotator disagreements. | Two landmarks or model predictions cannot substitute for full labels. |
| F | Review annotations independently; adjudicate discrepancies and mark genuinely unknowable extents/regions explicitly. | No tuning on uncertain labels presented as definitive truth. |
| G | Split by recording/session before experiments; freeze train/development/held-out lists and hashes. | Nearby frames and repeated scenes must not leak across splits. Obtain fresh sessions if necessary. |
| H | Predeclare relative comparison policy, thresholds, distance bins, uncertainty method and regression handling. | Absolute requirements remain pending; any tradeoff needs an explicit decision, not invented targets. |
| I | Obtain sensor mounting/extrinsics and checkpoint coordinate/feature contract; audit axes, units, box centers and yaw. | Unknown training calibration remains an uncertainty, not an assumed correction. |
| J | Verify geometry independently with measured calibration or a declared ground mask/seed and residual/coverage report. | Roofs, walls and partial legs cannot establish sensor height. |
| K | Freeze valid-return masking on original coordinates; remove zero XYZ and nonfinite returns before any transform. | Translating zero returns must not turn them into artificial valid points. |
| L | Apply the physically justified transform exactly once; save forward/inverse matrices and round-trip fixtures. | Reject blind score-selected shifts; transform labels/predictions consistently. |
| M | Recompute ROI and deterministic capacity selection after transformation; save point-loss counts and selected indices. | Do not hide body-geometry loss or claim CPU selection equals plugin selection. |
| N | Recreate prepared float32 inputs repeatedly and compare hashes. Run at least three GPU repetitions per fixed input. | Report matched box/score variation separately from hashes; bitwise GPU determinism is not assumed. |
| O | Evaluate the unchanged baseline against complete development labels: per-class BEV/3D TP/FP/FN, precision/recall, FP/frame, localization and miss streaks. | Missing/failed scans remain failures; they cannot silently disappear from denominators. |
| P | Run paired, one-factor development comparisons using the same scans/labels and saved candidates. | Only label-supported gains justify retaining a preprocessing candidate. |
| Q | If alignment is verified but accuracy remains poor, select a documented target-compatible independent checkpoint or plan Ouster fine-tuning. | Architecture name alone does not establish compatible training inputs. |
| R | Train/fine-tune only on training sessions with frozen preprocessing, seeds, dependencies and checkpoints; select using development data. | No held-out selection or implicit reuse of target labels. |
| S | Compare framework, exported model and TensorRT on identical fixed inputs, intermediate tensors where available, and decoded outputs. | Resolve numerical/class/axis/size/yaw/NMS differences before accuracy attribution. |
| T | Freeze the candidate and evaluate the untouched held-out sessions against the baseline at identical gates and matching rules. | Retuning after inspection consumes the holdout; acquire a fresh one for confirmation. |
| U | Report paired metrics and recording/session-level uncertainty across repeats and distance/occlusion strata. | Claim improvement only where supported; zero baseline TP does not make any new box a correct match. |
| V | Have an independent verifier recompute provenance, matching, exclusions, summaries and regression decisions from raw artifacts. | Author-written summary alone is insufficient verification. |
| W | Integrate only a supported candidate explicitly; preserve original message headers and inverse geometry and freeze rollback identities. | No display-only offset or threshold reduction presented as model repair. |
| X | Replay at rate 1.0; measure source-to-output age, drops, sustained latency, memory and recovery. Inject invalid-cloud/inference failures and verify cleared output plus warning diagnostics. | Clearing boxes on failure is freshness behavior, not accuracy improvement; silence still needs a freshness policy. |
| Y | Test intended live sensor conditions and failure/load cases; compare with the same acceptance record. | Stop/roll back on unsupported behavior or material regression. Absolute deployment targets must be agreed before claiming operational acceptance. |
| Z | Archive code/model/data manifests, labels, metrics, rejected trials, reviewer findings, commands and rollback recipe; update status. | Declare only demonstrated scope complete. If no candidate improves reliably, record failure and return to data/model adaptation. |

## Model-adaptation references

The coordinating agent checked NVIDIA’s current [TAO PointPillars guide](https://docs.nvidia.com/tao/tao-toolkit/latest/text/cv_finetuning/pytorch/point_cloud/pointpillars.html) on 23 November: it documents four-feature points, separate LiDAR/label training and validation directories, data conversion, and LiDAR yaw conventions that differ from KITTI camera yaw. Use the documentation for the selected installed release when implementing training. The [2022 ROS/TAO demonstration](https://developer.nvidia.com/blog/detecting-objects-in-point-clouds-using-ros-2-and-tao-pointpillars/) describes Zvision data and matching reflectance ranges; it does not prove the exact packaged v1.1 checkpoint’s training provenance.

## Runtime repair and verification boundary

The local `DetectionOutput::report_failure` now publishes an empty array carrying the failed cloud header and retains warning diagnostics with unavailable counts. Successful-frame and detection totals are not incremented. This requests removal of stale geometry on explicitly reported invalid input or inference failure. It does not address upstream Ouster adapter rejection before publication, sensor silence, DDS loss, queued stale scans or invalid TF, prove RViz rendering, or improve neural accuracy. Consumers must associate output with status and enforce age checks; the three ROS topics are not an atomic transaction.

Independent verification passed **8/8 native CPU/ROS CTests** (2.89 s) and **12/12 Ouster evaluator tests**. The strengthened test fails against the original output source with the expected delivery timeout (10.38 s), and passes against the repair (0.43 s). An earlier sandbox attempt failed on DDS socket permissions and is explicitly excluded from that negative-control evidence. See [the compact verification record](../config/solution_verification_20261123.json) and [independent report](../.recovery/verification/solution-20261123/verification-report.md). The latter and detailed logs are ignored evidence and need separate backup. These checks establish publication behavior, not GPU inference, actual rendered RViz pixels or accuracy. Historical test totals in older reports are separate. No new learned checkpoint, fine-tuning, held-out accuracy result, production deployment or acceptance wrapper is claimed here.
