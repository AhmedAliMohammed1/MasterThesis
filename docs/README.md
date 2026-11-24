# Project documentation

## Current candidate result — 24 November 2026

[Independent model comparison](CANDIDATE_MODEL_COMPARISON_20261124.md) records genuine Ouster 3D pedestrian gains, vehicle regressions, complete repeat inventories and independent checks. It also identifies the unresolved exact person, pretraining overlap and primary-bag labels/calibration needed before acceptance.

## Current continuation — 23 November 2026

[PointPillars A–Z solution protocol](POINTPILLARS_SOLUTION_PROTOCOL_20261123.md) separates the failed height/sampling trials, relative-improvement requirement, model/data work still needed and local failure-output repair.

## Latest investigation and retained images — 21 November 2026

Start with [multi-agent verification and the exact person case](OUSTER_VERIFICATION_AND_PERSON_DIAGNOSIS_20261121.md): the exhaustive audit, controlled trials, corrected selections, frame-1403 diagnosis and limitations. The [complete image archive](IMAGE_ARCHIVE.md) preserves all available screenshots and generated images, including drafts. Older chapters retain their experiment dates.

Reviewed 21 November 2026; historical studies retain their original dates. Choose a reading path below rather than reading the project history from the beginning.

This project runs a pretrained PointPillars detector in ROS 2 Jazzy using TensorRT. The migration and sensor integration work, but the current model has not passed 3D accuracy acceptance. Reflectivity/255 is the better supported experimental Ouster input in the measured comparison.

## If you want to run the project

1. [Main README](../README.md): purpose, prerequisites and first commands.
2. [Startup and Ouster replay](STARTUP_AND_REPLAY.md): matching live/bag settings, shutdown and RViz.
3. [Docker details](../docker/README.md): image builds, caching, runtime settings and engine storage.
4. [Ouster adapter](LIVE_OUSTER_ADAPTER.md): fields, explicit conversion and diagnostics.
5. [Filtering and monitoring](CONFIDENCE_FILTER_AND_MONITORING.md): scores, box counts and freshness.
6. [Native builds](local_runtime.md): CPU, ROS and GPU build boundaries.
7. [Troubleshooting](LIVE_OUSTER_TROUBLESHOOTING.md): live discovery and earlier host-specific problems.

The main launchers do not all start the same components. `deploy.sh` builds/reuses an image and starts the detector unless optional `PP_BUILD_ONLY=1` is set. `start_ouster.sh` starts adapter plus detector; its `bag` profile matches the primary `raw01`/`ouster1` player on `/ouster1/points`. Neither starts RViz automatically.

## If you want to understand the implementation

- [Plain-language explanation](../README_PROJECT_EXPLANATIONS.md): model, engine, CPU/GPU roles and data flow.
- [Architecture](../IMPLEMENTATION_ARCHITECTURE.md): current components, state and ownership; planned worker clearly separated.
- [Practical LaTeX guide](PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex): editable setup and implementation narrative.
- [Filtering, visualization and timestamps](CHAT_FILTERING_RVIZ_AND_TIMESTAMPS.tex): editable explanation of output semantics.

## If you want the measured results

Start with [current status](CURRENT_STATUS_AND_RESULTS.md) and [the Ouster decision and proposal](OUSTER_CHANNEL_DECISION.md). For the new diagnosis, read [detection investigation and repair plan](DETECTION_INVESTIGATION_AND_PLAN.md), supported by the [model investigation](DETECTION_MODEL_INVESTIGATION.md) and [independent code review](DETECTION_CODE_REVIEW.md). Then use the experiment-specific pages:

| Topic | Read this | What it establishes |
| --- | --- | --- |
| Current Ouster signal/reflectivity choice | [Channel decision](OUSTER_CHANNEL_DECISION.md) | Numerical success and diagnostic ground-truth comparison; no accepted 3D configuration |
| Labeled KITTI baseline | [KITTI accuracy](KITTI_ACCURACY_RESULTS.md) | Poor diagnostic accuracy with original labels |
| KITTI data preparation | [Validation data](KITTI_VALIDATION_DATA.md) | Frozen split, calibration and class policy |
| Runtime comparison | [TensorRT reference study](MODEL_REFERENCE_COMPARISON.md) | Compatibility and repeatability evidence, not exact training parity |
| Earlier Ouster feature experiment | [Feature comparison](OUSTER_FEATURE_COMPARISON.md) | Same-scan numerical comparison on older unlabeled recordings |
| Fresh Ouster visual test | [MOSEP replay](FRESH_OUSTER_VISUAL_TEST.md) | Original-bag conversion and integration, not labeled weather accuracy |
| Earlier Ouster bags | [Koide bag demo](OUSTER_ROSBAG_DEMO.md) | Dataset preparation and historical replay workflow |
| Camera context | [Ouster camera visuals](OUSTER_CAMERA_VISUALS.md) | Sensor views and clock limitations |
| Detailed RViz view | [Frontal comparison](FRONTAL_COMPARISON_AND_RVIZ_DETAIL.md) | Rendering and message integration, not new ground truth |
| Next evaluation | [Validation plan](MODEL_VALIDATION_PLAN.md) | How to separate implementation, input compatibility and accuracy acceptance |

## If you are writing the thesis

1. [Readable thesis draft](THESIS_DRAFT.md): chapter structure, draft prose, result tables and open items.
2. [Editable LaTeX thesis draft](THESIS_DRAFT.tex): standalone working manuscript with references and figures.
3. [Presentation](PROJECT_MIGRATION_PRESENTATION.tex): concise account for a supervisor meeting.
4. [Evidence and terminology](EVIDENCE_AND_TERMINOLOGY.md): what each claim means and where its evidence lives.
5. [Figure catalog](figures/README.md): captions, provenance, attribution and permitted interpretations.

The drafts deliberately include negative results. Do not replace “zero qualifying 3D matches” with “accurate detection” because a screenshot contains boxes. Retain experimental settings, sample sizes, exclusions and limitations when moving text into a thesis template. The title page records Ahmed Elsaify, THI and Master of International Automotive Engineering. Supervisor details, university formatting, final acceptance targets and larger evaluation results remain to be completed.


The thesis now includes a full [engineering journey](ENGINEERING_JOURNEY.md): 21 sections explaining the problems, investigations, corrections and remaining gaps, followed by an [illustrated casebook](THESIS_CASEBOOK.md) with 50 problem groups and four detailed subcases. Start there to understand how each experiment led to the next. Its timeline and diagnostic map are available as editable SVGs and PNGs in the figure catalog.

## Historical records and recovery

[Project history](PROJECT_HISTORY_AND_DECISION_RECORD.md), [discussion record](CHAT_DISCUSSION_RECORD.md) and [the original modernization brief](../PROJECT_REVIEW_AND_UPDATE_PLAN.md) preserve dated decisions. Their old commands, process states and publication notes are historical. The [legacy Foxy README](LEGACY_FOXY_README.md) is for understanding the original environment, not current installation.

For a new development session, read [the resume guide](../recovery/RESUME.md), [task ledger](../recovery/tasks.json) and [chronological progress](../recovery/PROGRESS.md). No saved PID or “left running” note proves a process is active now.

The contributor agreement and original user instructions are preserved in `CLA.md` and `prompt.md`. They are not rewritten as project tutorials. Models, recordings, raw observations and historical PDFs remain separate from the current source documents.

## Documentation status

The latest dated report describes measurements through 21 November 2026; earlier guides and thesis chapters retain their original study scope. They do not assert that every saved image was rebuilt or that a service is running. [Documentation review](../config/documentation_review.json) records file coverage, static checks and the latest built-in LaTeX compilation attempts. A missing TeX dependency or unavailable image in a standalone preview is reported explicitly; old PDFs are not silently treated as newly compiled outputs.

### Illustrated problem-and-solution appendix — 9 November

The thesis now includes 257 small solution steps across 50 groups and four subcases. The appendix uses 54 editable comparison tables and selected flowcharts to explain what went wrong and what the checks established. Four preserved original RViz captures and two actual terminal captures remain where they support the explanation. The older report screenshots are retained only as historical assets and are no longer embedded in the thesis. Unsafe driver and disk faults were not recreated. [The original evidence review](../config/thesis_casebook_review.json) separates the checks from the frozen accuracy experiments; [the presentation revision](../config/thesis_native_panels_review.json) records the replacement of report screenshots with native tables and flowcharts.

An earlier index referenced `OUSTER_BEFORE_AFTER_COMPARISON.md`, which is absent from this checkout. Its stated 291-scan / 1,746-inference comparison was not revalidated in this refresh. Use the [available measured investigation](OUSTER_VERIFICATION_AND_PERSON_DIAGNOSIS_20261121.md) for the latest verified results.

## Primary recordings — 21 November 2026

[Live raw01 baseline and same-scan detection discovery](PRIMARY_BAG_DETECTION_DISCOVERY.md)
records the first live run and 120 new diagnostic inferences on raw01/ouster1.
Bounded inputs improve repeatability; new detection accuracy remains unmeasured.

[Model/input mismatch and improvement options](MODEL_INPUT_MISMATCH_AND_SOLUTIONS.md)
adds three specialist reviews, a within-pillar geometry audit and 180 same-engine
preprocessing trials. Alternative neural networks are researched, not executed;
no new accuracy acceptance is claimed.

[Missed-person solution trials](PERSON_DETECTION_SOLUTION_TRIALS.md) records three
agents trying sampling/intensity/geometry, plus NMS and combination controls:
390 measured GPU trials. Nearby scores improve under some settings, but no tested
variant reaches .4 nearby; exact screenshot-target accuracy remains unmeasured.

[NVIDIA exact-model confidence research](NVIDIA_EXACT_MODEL_CONFIDENCE_RESEARCH.md)
and [NVIDIA settings research](NVIDIA_POINTPILLARS_SETTINGS_RESEARCH.md) distinguish
the v1.1 ONNX contract from generic/stale publisher examples and mAP from mean confidence.

[Live clipped-reflectivity preview](LIVE_REFLECTIVITY_PREVIEW.md) records the
requested /100-clipped encoding, score gate0.3, raw01 playback1.0 and actual live checks.
