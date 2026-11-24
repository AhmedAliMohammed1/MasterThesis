# Detection investigation and practical repair plan

Reviewed 9 November 2026. **The pipeline runs, but its current 3D detections are not accurate enough to accept.** We have narrowed the investigation; we have not proved one complete root cause or deployed an accuracy fix.

## What this investigation is trying to answer

We need to separate three questions: does the application preserve the data correctly; do the packaged TensorRT plugins implement the expected small examples; and does this pretrained model fit the target sensor and coordinate convention? Changing all three at once would make an apparent improvement difficult to explain.

Development, independent testing, source review, model investigation and documentation are separate roles in this work. The reviewer recommended a small explicit input policy, not a new framework, automatic sensor classifier or rewrite of the working NMS. Existing source changes, original data, labels, models, engines and frozen experiments are preserved.

## Findings so far

| Question | Evidence | What it means |
| --- | --- | --- |
| Is RViz moving boxes upward? | Application review finds the candidate center copied directly into the ROS box. Elevated candidates also occur in the older TensorRT8 reference. | A viewer-only explanation is insufficient. |
| Is duplicate removal the cause? | The saved comparison selected identical boxes in all 192 same-candidate NVIDIA/project NMS observations. | Replacing NMS is not a supported height correction. This does not prove all inference parity. |
| Does the real packaged decoder add the wrong half-height? | New GPU control: Vehicle z residuals 0, +1 and −1 produce centers −1.00, +0.56 and −2.56 m with height 1.56 m, as expected. | The tested Vehicle anchor arithmetic is correct. Adding another half-height in application code would be wrong. |
| Does the packaged voxel plugin construct the expected features? | New GPU control: all ten features agree with the CPU calculation for three points in two pillars. | The tiny capacity-compliant example passes; this does not validate every layout, boundary or overflow case. |
| Are the evaluation routines responding correctly? | Twelve current CPU ground-truth tests passed. | Known coordinate/matching cases work. This does not make the predicted real objects correct. |
| Is the model known to be trained for Ouster or KITTI? | Exact deployable_v1.1 ONNX/label publisher hashes match locally. The model-level card describes proprietary solid-state LiDAR data; its version-specific description is empty. | There is no verified training-domain match for this exact export. Domain mismatch is plausible, not the sole proven cause. |
| Does the model keep all target geometry? | New read-only audit of 16 KITTI tuning frames measures point coverage inside annotated boxes. | Some lower geometry lies outside the model range; the magnitude differs by class and object. |
| Are internal capacities protected by the generic adapter? | It checks total point allocation, while the model also has 10,000-pillar and 32-points-per-pillar limits. Published NVIDIA source has an unguarded coordinate write before later clamping. | An explicit bounded-input policy is justified as a software protection. Packaged binary overflow and its contribution to height error are not yet proved. |

See the [model investigation](DETECTION_MODEL_INVESTIGATION.md) and [independent code review](DETECTION_CODE_REVIEW.md) for inspected implementation boundaries and primary sources.

## What the new geometry audit measures

The model encodes approximately x/y ±51.2 m and z from −1.4 to 4.4 m. We counted original points inside each oriented annotation, then counted how many remain in that range. Only the 16 existing KITTI **tuning** frames were used; no fitted correction was chosen from the test labels.

| Class | Boxes containing source points | Counted points inside boxes | Retained in model range | Removed below the lower z bound, inside XY |
| --- | ---: | ---: | ---: | ---: |
| Car | 44 | 41,329 | 34,698 (83.96%) | 6,618 |
| Pedestrian | 67 | 9,288 | 8,706 (93.73%) | 582 |
| Cyclist | 26 | 5,162 | 5,092 (98.64%) | 70 |

These are point-weighted counts, not the percentage of accurately detected objects. A point inside an annotation may belong to background; overlapping boxes may count a point more than once. Three Car boxes lose more than half their counted points. These findings motivate checking the sensor/training frame convention. They neither establish causation nor justify a universal 2.5 m translation.

## Fresh GPU input controls: repeatability improved, accuracy unmeasured

We ran **18 new GPU inferences** on two unlabeled Koide scans: three input policies × three sequential repetitions × two scans. The fourth feature was normalized reflectivity throughout. The original model/engine were reused, no warmups were added, and execution order was not randomized. The controls used the existing Python sensitivity policy; they do not validate the newly developed C++ helper by themselves.

| Scan and input | Points | Post-NMS boxes | Boxes above 0.4 | Matches to first repeat at tolerance 0.001 |
| --- | ---: | ---: | ---: | --- |
| 000000, original | 32,768 | 20 | 2 | 19/20, 19/20 |
| 000000, zero-XYZ removed | 19,562 | 21 | 2 | 19/21, 19/21 |
| 000000, bounded policy | 14,995 | 20 | 2 | 20/20, 20/20 |
| 000008, original | 32,768 | 12 | 0 | 7/12, 7/12 |
| 000008, zero-XYZ removed | 18,146 | 12 | 0 | 9/12, 8/12 |
| 000008, bounded policy | 11,548 | 11 | 0 | 11/11, 11/11 |

All 18 observations completed without recorded inference failure. Each pair compares one later repeat with the first, using the larger box count as denominator. Bounded outputs match at the stated tolerance; their binary hashes still differ. Thus this is improved measured numerical repeatability, not bitwise determinism. Zero-return removal alone was not consistently better.

Neither scan exceeded 10,000 pillars. The bounded policy also removes out-of-range points and caps each retained pillar at 32 points, so this experiment cannot isolate the effect of pillar-count overflow. Its retained nonzero/ROI pillars were 2,906 and 2,030; it removed 1,873 and 4,866 additional points at the per-pillar limit. There are no annotations, so the same 2/0 high-score box counts cannot establish precision, recall, vertical correction or an accuracy improvement.

## Keep the existing accuracy result separate

The frozen 8 November study contains 1,120 measured GPU inferences plus 18 excluded warmups. At confidence 0.4, its 16 labeled test scans contain 60 in-region Vehicle annotations: reflectivity/255 finds four qualifying BEV matches per repeat; signal/65,535 finds none. Neither has qualifying 3D matches. The four first-repeat reflectivity footprint matches are 0.60–1.14 m too high.

The new tiny-plugin controls and tuning-input audits are diagnostic engineering checks. They are not additional independent labeled scenes and must not be added to the frozen study's measurement totals. Reflectivity/255 remains an experimental baseline, not accepted 3D accuracy or a universal sensor-channel recommendation.

## What we are developing

A small CPU input-policy component is now implemented in `include/pp_infer/point_policy.hpp` and `src/point_policy.cpp`, with an offline `pp_prepare_points` executable. It makes passthrough versus bounded selection explicit, preserves retained XYZI bits and order, and reports removals by cause. Its default is passthrough. The bounded policy checks finite XYZI, removes zero XYZ, applies a half-open ROI and retains the first encountered pillars/points under explicit capacities. **It is not called by the live detector or adapter; their defaults are unchanged.**

The developer reports a fresh CPU build with all three CTest executables passing. The helper writes a new file exclusively and refuses to overwrite an existing output. Its native-endian FLOAT32 XYZI input has a 1 GiB file-size bound. This is an offline engineering tool, not an installed automatic correction or accepted accuracy fix.

The policy is intended to protect known model capacities and enable controlled comparisons. It does not move boxes, select the best channel automatically or claim to fix pretrained weights. Retaining the legacy path allows old measurements to remain reproducible.

## Minimal next steps and their acceptance checks

1. **Keep the tested offline policy explicit.** Three C++ test executables now pass, including half-open model bounds, float32 cell edges, zero/nonfinite returns, first encountered pillar selection, exactly 10,000 pillars and 32 points, bit/order preservation and unchanged legacy behavior. Independently checked C++ outputs match the Python preparation byte for byte on both real scans. Evaluate a separately declared live integration before enabling it in ROS.
2. **Compare original and controlled inputs on development data.** Freeze engine/model/source identities; retain every failed observation. Run matched zero-return and capacity controls, report repeatability and labeled geometry separately, and avoid changing thresholds or coordinates at the same time.
3. **Complete the original-model contract.** Obtain an independently trusted training-framework input and expected outputs. Compare voxel membership/features, scatter positions, network residuals and decoded centers. The passing tiny plugin examples narrow the search but do not replace that reference.
4. **Choose a model suitable for the target sensor if the verified reference still performs poorly.** Use an independently validated Ouster export or fine-tune on training/tuning recordings with declared coordinate and feature scales. A different model should come with matching preprocessing and decoder assumptions.
5. **Evaluate once on new recording-disjoint annotated data.** Agree precision/recall and 3D-overlap targets in advance. Include negatives, distances, class coverage and weather. Treat the already inspected KITTI/Dur360 subsets as diagnostics, not a fresh acceptance set.
6. **Handle live scheduling separately.** The synchronous reliable depth-700 callback can accumulate old frames; worker/QoS and sustained end-to-end age require their own tests. That issue does not explain the saved direct-run height errors.

A proper solution may require both bounded preprocessing and a sensor-compatible model. We will not present an output z offset, a cleaner screenshot or an empty high-threshold output as an accuracy repair.

## Commands and evidence

Run commands from the repository root. Existing metric controls can be repeated without launching the sensor:

```bash
python3 -m unittest discover -s tests -p 'test_ouster_gt_evaluation.py' -v
```

Build and test the new offline helper without ROS, CUDA or TensorRT:

```bash
cmake -S . -B /tmp/pp-point-policy-build \
  -DPP_BUILD_RUNTIME=OFF -DPP_BUILD_ROS_ADAPTER=OFF \
  -DPP_BUILD_POINT_DIAGNOSTICS=ON -DBUILD_TESTING=ON
cmake --build /tmp/pp-point-policy-build -j2
ctest --test-dir /tmp/pp-point-policy-build --output-on-failure
```

For an already packed native-endian FLOAT32 XYZI `.bin`, create a **new** bounded output file. The following numbers describe the inspected model; verify them against the exact export when using another model:

```bash
/tmp/pp-point-policy-build/pp_prepare_points \
  INPUT.bin NEW_OUTPUT.bin bounded \
  -51.2 -51.2 -1.4 51.2 51.2 4.4 \
  0.2 0.2 10000 32 204800
```

Replace `INPUT.bin` and `NEW_OUTPUT.bin` with actual paths; do not use an original dataset path as output. The tool prints JSON counts. Replacing `bounded` with `passthrough` preserves the original point bits, including zero/nonfinite entries, for explicit baseline reproduction. These files are not ROS bags, and running this command does not reconfigure `deploy.sh` or `start_ouster.sh`.

The new GPU plugin probes are diagnostic programs saved with their actual compilation commands and logs, not installed ROS executables. They require the inspected TensorRT libraries and GPU; do not substitute a different engine or library and call the result identical.

| Record | Location |
| --- | --- |
| Publisher responses, hashes, available/unavailable reference sources | `.recovery/verification/detection-investigation-2026-11-09/model/` |
| Actual packaged decoder probe and GPU output | `.recovery/verification/detection-investigation-2026-11-09/testing/decoder_plugin_probe.cpp`, `decoder-compile.log`, `decoder-gpu.log` |
| Actual packaged voxel probe and GPU output | `.recovery/verification/detection-investigation-2026-11-09/testing/voxel_plugin_probe.cpp`, `voxel-compile.log`, `voxel-gpu.log` |
| Twelve CPU evaluation controls | `.recovery/verification/detection-investigation-2026-11-09/testing/ground-truth-tests.log` |
| Eighteen new unlabeled GPU input-policy controls | `.recovery/verification/detection-investigation-2026-11-09/testing/point-controls/report.json`, `recipe.json`, `runtime.json` |
| Tuning-only model-range coverage and source hashes | `.recovery/verification/detection-investigation-2026-11-09/roi/report.json` |
| Prior frozen numerical/accuracy experiment | `config/ouster_channel_decision.json` and its referenced observations |

Unavailable reference material is part of the record: the shared card mentions `102.bin`, but it was absent from the inspected pinned recipe tree and a historical raw URL returned 404. We did not invent an expected output. Existing incomplete large-cloud ROS A/B delivery remains excluded; direct-run success does not certify that live transport path. Large evidence directories are ignored by Git and need an independent backup.

## Final regression and deployment-context check

The fresh full Python regression suite passed 119 tests. A separate parent-agent CPU build passed all three CTest executables. The offline tool is optional: `PP_BUILD_POINT_DIAGNOSTICS` defaults to `OFF`, so the existing minimal Docker source context does not need the `tools/` directory. An early unconditional tool target was caught during review and corrected before completion; a copied no-tools context then configured, built and passed all three CTest checks. These checks establish build compatibility and helper behavior, not target-sensor accuracy.

## Full same-bag confirmation

A separate [before/after comparison](OUSTER_BEFORE_AFTER_COMPARISON.md) now covers every 291 occurrence of one original Ouster bag, with 1,746 measured inferences. Candidate repeat matching improves 98.904%→100%; accepted-box repeat matching improves 99.761%→100% at the declared 0.001 tolerance. Accepted counts are unchanged on every scan (418 events per pass), and no labeled accuracy improvement is established. This later run uses the actual new C++ helper and does not replace the earlier 18-inference controls or frozen 1,120-observation study.
