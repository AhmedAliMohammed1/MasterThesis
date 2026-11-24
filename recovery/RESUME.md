# Resume work without losing the current state

## Completed candidate development comparison — 24 November 2026

Read [candidate comparison and next evidence](../docs/CANDIDATE_MODEL_COMPARISON_20261124.md). Dur360 continuation is complete: 96 unique records, original 67 preserved plus 29 missing records, identical repeated boxes. Final paired scoring and independent integrity/metric checks are in `.recovery/verification/candidate-eval-20261124/`. At gate 0.3, historical Ouster test pedestrian counts improve from 0 TP / 12.667 FP / 6 FN to 3 / 11 / 3. Vehicle false positives worsen; frame 1403 still has no pedestrian box containing both landmarks. KITTI has concrete overlap with upstream split lists. These are development results, not unseen acceptance. Next required evidence: independent complete primary-bag 3D labels, verified calibration, frozen held-out scenes, extension/export parity and live checks. Preserve original artifacts and all existing changes. The extracted offline runner is `tools/experimental_pointpillars.py`; its new implementation checks are separate from the original inference evidence.

## Current continuation — 23 November 2026

Read [the A–Z protocol](../docs/POINTPILLARS_SOLUTION_PROTOCOL_20261123.md). The checkout is now `/media/ae/New Volume/MasterThesis`; recheck historical mount/process claims. The 78 preserved height/quantile trials did not fix landmark coverage. Accuracy remains open; absolute targets are undecided, and improvement must be measured against the frozen baseline. Local failure-output clearing is a separate freshness repair; consult `.recovery/verification/solution-20261123` for current checks. Preserve the many preexisting modifications.

## Latest evidence handoff — 21 November 2026

Read `docs/OUSTER_VERIFICATION_AND_PERSON_DIAGNOSIS_20261121.md`, `config/ouster_verification_20261121.json` and `config/user_person_point_measurements_20261121.json`. The exact identified case is ouster1 frame 1403, record time 1794397517854145698 ns, offset +70.05539416 s. Head and partial lower body are verified in the same source scan; feet and full height remain unmeasured. No live height correction or sampling policy was enabled.

Retain all images: the gallery is under `.recovery/documentation-images/2026-11-21`, named figures under `docs/figures/2026-11-21`, controlled evidence under `.recovery/verification/ouster-multi-agent-20261121`, and the exact case under `.recovery/verification/user-person-exact-scan-20261121`. The last configured preview was ouster1, rate 1, clipped /100, gate 0.3; check actual process state. Use record timestamps and source hashes because headers wrap and repeat. Preserve unrelated existing changes.

Reviewed 8 November 2026. Start here after an interrupted session. This is a handoff guide, not a record of currently running processes.

## Read these first

1. [Current status and measured results](../docs/CURRENT_STATUS_AND_RESULTS.md).
2. [Ouster channel decision and proposal](../docs/OUSTER_CHANNEL_DECISION.md).
3. [Architecture](../IMPLEMENTATION_ARCHITECTURE.md) and [task ledger](tasks.json).
4. [Startup and replay](../docs/STARTUP_AND_REPLAY.md) for runnable commands.

The latest published research snapshot at this review is `15a82bc`; deployment fixes are in `493bdf0`. Check `git status` and `git log` before assuming either still describes the checkout. Documentation edits do not rebuild a saved runtime image.

## Current conclusion

The ROS 2 Jazzy/TensorRT 10 migration, Docker startup, Ouster adapter and monitoring are implemented and have recorded checks. The latest channel study made 1,120 measured GPU inferences plus 18 warmups. Both normalized channels completed the tested numerical runs without inference failure.

Reflectivity/255 is the better supported experimental input for this configuration. On 16 labeled Ouster test scans it gives four qualifying Vehicle BEV matches per run, versus zero for signal/65535, among 60 in-ROI Vehicle annotations. Both have zero qualifying 3D matches. This is not accuracy acceptance.

The current detector is synchronous with reliable depth 700. The bounded worker, sustained benchmark, complete memory/failure acceptance and CI remain open. The deterministic capacity experiment is not deployed preprocessing. Do not mark tasks verified merely because the study finished.

## Preserve the evidence

Small summaries and provenance are in `config/`; large evidence is ignored and needs an independent backup:

| Directory | Contents |
| --- | --- |
| `.recovery/accuracy/ouster-production-mosep-v1` | 480 current-code weather observations |
| `.recovery/accuracy/ouster-production-dur360-v2` | 320 primary labeled observations and evaluation |
| `.recovery/accuracy/ouster-production-dur360-bounded-v1` | 320 separate capacity-control observations |
| `.recovery/dur360bevet-study` | Original annotated subset, publisher checksums and frozen selection |
| `.recovery/accuracy/kitti-baseline-v1` | Frozen first KITTI predictions and evaluation |
| `.recovery/accuracy/kitti-reference-v1` | TensorRT compatibility and repeatability evidence |

Do not overwrite frozen outputs to make new code appear consistent. A changed model, engine, source, preprocessing rule or evaluation policy requires a new output directory. Preserve failed attempts as well as successful runs. Keep original bags and labels unchanged.

## Before starting or stopping anything

Run `git status --short --branch`, inspect Docker containers and check the selected image. Saved ownership/PID records are historical until matched against actual process identity. Stop only the intended resources. Use the startup guide's explicit bag profile so topic, domain and middleware agree.

A working host GPU was verified during the study. A restricted tool session can still hide GPU access; distinguish that from a host driver failure. Do not install or upgrade host drivers merely because a sandbox cannot query them.

## Checkpoint routine

`tools/recovery.py` stores limited source checkpoints and reports drift; it does not restore files, execute experiments, enforce task acceptance or back up datasets. Use its current `--help` before issuing commands. Its ignored output is not a substitute for Git or an external evidence backup.

When resuming an implementation task:

1. Read the source involved and its callers/tests, then inspect existing changes.
2. Identify the smallest correctness question to resolve.
3. Record source/model/input identities and use a new evidence directory if they differ.
4. Run checks appropriate to that change; state failures and unverified areas explicitly.
5. Update the status, evidence summary and task ledger together.

## Thesis and documentation work

The [documentation index](../docs/README.md) separates current guides, research, the thesis draft and historical records. Use the [thesis draft](../docs/THESIS_DRAFT.md) as an editable structure, retaining its limitations and source references. Figure provenance lives beside the images in `docs/figures`.

LaTeX sources remain editable in the built-in editor. Previous compilation attempts failed while fetching missing TeX resources. A failed preview does not establish a source error or a successful PDF. Consult the latest documentation review record for the current attempt; do not install a separate TeX distribution to conceal an unverified native preview.

## Thesis history expansion — 9 November 2026

The engineering chapter and 50-item register are saved in both thesis drafts, with a separately readable `docs/ENGINEERING_JOURNEY.md` and two new explanatory figures. Check `config/thesis_history_review.json` for coverage and compiler status. The verified project volume is currently mounted at `/media/ae/New Volume1/MasterThesis`; the earlier mount path is occupied by another volume. Confirm the mount and Git identity before using historical absolute commands. These documentation edits remain local.

## 9 November 2026 — illustrated thesis completion pass

Expanded the existing THESIS_DRAFT.tex and readable manuscript with 50 illustrated problem groups, four subcases and 257 small solution steps. Added 54 evidence-report captures, four byte-identical historical RViz captures and two actual new terminal captures. Their labels distinguish a report from an original incident screenshot. No physical driver, disk-full or destructive data fault was induced. The full Python regression run passed 119 tests; six separate one-scan GPU demonstrations reproduced raw-signal decoder rejection and normalized-reflectivity acceptance without changing the frozen 1,120-observation study. Author details supplied: Ahmed Elsaify, THI, Master of International Automotive Engineering; supervisor pending. Current work remains local and uncommitted. Consult config/thesis_casebook_review.json for final source checks and the native compiler result.

## 9 November 2026 — replace report screenshots in thesis

At the author’s request, replace all 54 J-series report screenshots with editable comparison tables and selected explanatory flowcharts. Preserve the original problem history, 257 small steps, recorded checks and limitations. Retain genuine RViz/terminal captures and numerical plots; keep old report PNGs and provenance as historical evidence, no longer embedded in the manuscript. No runtime or experiment result is changed. The native-panel review is recorded in config/thesis_native_panels_review.json.

## 9 November 2026 — multi-agent detection investigation

Five roles covered model provenance, development, independent testing, minimal code review and documentation. Exact-version model/label hashes match; the shared model-level card describes proprietary solid-state data, but its empty version-specific description leaves v1.1 training identity unverified. Actual packaged decoder and tiny voxel-feature controls pass; no blanket z correction was installed. A tuning-only oriented-box point audit measured lower-ROI geometry loss. Eighteen new unlabeled Ouster production inferences show bounded selection improves repeat matching on two scans, while removing zero returns alone does not consistently do so. These are separate from the frozen 1,120-observation study and establish no new accuracy result.

Added a pure CPU `prepare_points` helper and optional offline CLI, enabled with `PP_BUILD_POINT_DIAGNOSTICS=ON`. Live adapter/runtime behavior is unchanged. New C++ outputs match Python preparation byte for byte on both real scans; passthrough and existing-output protection pass. Current Python regression119 tests and CPU CTest3/3 pass. Review caught and corrected an unconditional offline target that would have required tools absent from the Docker context; a minimal no-tools build also passes. Read docs/DETECTION_INVESTIGATION_AND_PLAN.md, docs/DETECTION_TEST_RESULTS.md, docs/DETECTION_MODEL_INVESTIGATION.md and docs/DETECTION_CODE_REVIEW.md. Large logs/inputs remain under .recovery/verification/detection-investigation-2026-11-09. No production accuracy fix, package installation, engine replacement or push is claimed.

## 9 November 2026 — full original Ouster before/after comparison

User asked exactly what changed and whether it improves detections. All 291 cloud occurrences from original Koide/AIST rosbag2_2023_03_28-16_25_54 were decoded read-only, using reflectivity/255 in both variants. The after inputs invoke the actual new C++ helper and match Python preparation on all 291 scans. A shuffled paired-job run made 1,746 measured inferences plus four excluded warmups with one unchanged production engine and runtime. Original bag hash stayed unchanged; all 1,746 raw output hashes pass verification. Candidate repeat matching 98.904%→100%; confidence 0.4 accepted repeat matching 99.761%→100%. Accepted counts are unchanged on every scan: 418 events per pass. No labeled accuracy improvement is established; live defaults remain unchanged. Read docs/OUSTER_BEFORE_AFTER_COMPARISON.md and config/ouster_before_after_20261109.json. Original/after raw outputs, exactcommands and identities remain ignored under .recovery/verification/ouster-before-after-20261109-v1. No containers remained after the run.

## Primary experiment inputs — 21 November 2026

New experiments use `raw01` (default) and `ouster1` from
`/media/ae/New Volume1/rosbags`. The replay launcher opens their original standalone
MCAPs read-only; the shared bag profile now uses `/ouster1/points`, domain 99 and
Fast DDS. Sampled clouds use frame `ouster1_lidar` and have literal signal and
reflectivity channels. See [startup and replay](../docs/STARTUP_AND_REPLAY.md) for commands and inspection limits.
Historical datasets and frozen results remain unchanged; this input selection
does not establish new inference or accuracy results.
