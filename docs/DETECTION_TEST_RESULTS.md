# Independent detection tests — 9 November 2026

These new tests narrow possible causes. They do not turn the current detector into an accepted accurate detector. The frozen 1,120-observation study is unchanged.

## What was tested

| Check | New observations | Result |
| --- | ---: | --- |
| Existing Ouster ground-truth CPU regression | 12 tests | Passed |
| Existing bounded point-policy CPU regression | 5 tests | Passed |
| Actual packaged DecodeBbox3DPlugin, known residuals | 3 GPU executions | Passed center-z and height control |
| Actual packaged VoxelGeneratorPlugin, independent feature calculations | 2 GPU executions | All ten features matched within 1e-5 on three valid points, then four points including an artificial zero return |
| Current production C++ inference/NMS, two unlabeled Koide scans | 18 GPU inferences | All completed; bounded selection had perfect numerical repeat matching in this limited control |

Do not add these different checks together as independent labeled scenes. The two plugin networks are artificial controls. The eighteen model inferences use two existing unlabeled scans, not eighteen new scenes.

## Decoder result

The actual packaged TensorRT 10 version-one decoder was exercised with the model's anchor attributes. With Vehicle anchor bottom -1.78 m and height 1.56 m, zero z residual produced center z=-1.00 m. Residuals +1 and -1 produced +0.56 m and -2.56 m. Every execution produced one box with height 1.56 m.

This directly supports treating this packaged decoder's z as a geometric center. It does not support subtracting half-height from every current prediction. It does not clear learned residuals, training conventions, other anchors, every layer or export parity.

## Voxel-feature result

For three points in two pillars, the packaged plugin's original XYZ/intensity, cluster-mean XYZ differences and pillar-center XYZ differences matched independent CPU calculations. Adding an artificial zero XYZ point also passed the numerical formula check: the zero point was treated as a real point and changed the cluster mean. Thus finite zero returns are not automatically invalidated by this plugin. Source-side valid-return handling matters, but this observation alone is not an accuracy experiment.

## Fresh production point-selection comparison

Only reflectivity/255 was used; there was no coordinate shift or feature rescaling between variants. Each variant ran three sequential times, with no warmups or randomized ordering. Both original scans had fewer than 10,000 occupied pillars. Bounded selection also limited each retained pillar to 32 points.

| Scan | Variant | Points | Zero XYZ | Post-NMS counts | Counts at score >=0.4 | Repeat match fractions |
| --- | --- | ---: | ---: | --- | --- | --- |
| 000000 | Original | 32,768 | 13,206 | 20/20/20 | 2/2/2 | 0.950 / 0.950 |
| 000000 | Remove zero XYZ only | 19,562 | 0 | 21/21/21 | 2/2/2 | 0.905 / 0.905 |
| 000000 | Bounded selection | 14,995 | 0 | 20/20/20 | 2/2/2 | 1.000 / 1.000 |
| 000008 | Original | 32,768 | 14,622 | 12/12/12 | 0/0/0 | 0.583 / 0.583 |
| 000008 | Remove zero XYZ only | 18,146 | 0 | 12/12/12 | 0/0/0 | 0.750 / 0.667 |
| 000008 | Bounded selection | 11,548 | 0 | 11/11/11 | 0/0/0 | 1.000 / 1.000 |

Matching is unique, class-aware component matching at tolerance 0.001 against repeat zero. It is not ground-truth matching. Constant counts concealed changed boxes in the original/nonzero variants. Removing zero returns alone did not consistently improve repeatability; deterministic per-pillar selection improved it on these two scans. None of these observations establishes better object accuracy.

## Reproduction and identities

Evidence directory: `.recovery/verification/detection-investigation-2026-11-09/testing/`.

- `decoder_plugin_probe.cpp`, `decoder-compile.log`, `decoder-gpu.log`: known-encoding decoder control.
- `voxel_plugin_probe.cpp`, `voxel-compile.log`, `voxel-gpu.log`, `voxel-zero-gpu.log`: voxel feature controls. The later source accepts `include-zero`; no argument tests the original three valid points.
- `run_point_controls.py`: complete preparation, compilation, Docker command recording, engine identity and comparison procedure. It intentionally refuses the already-used output directory; use a new output folder for a rerun.
- `production-compile.json`, `point-controls-gpu.json`: exact commands, outputs, elapsed time and exit codes.
- `point-controls/recipe.json`, `runtime.json`, `report.json`: inputs, source hashes, engine/image identities and per-observation results.
- `testing-review.json`: artifact hashes and scope.

Hardware: RTX 4060 Laptop, GPU-4219859e-3a54-d063-1435-a290cd5d28f3, driver 595.99.02. Existing diagnostic image: pp-infer:reference-trt10, immutable ID in runtime.json. Existing production engine SHA-256 is recorded by a read-only engine-volume query. The TensorRT shared libraries are extracted SDK files; dpkg-query found no registered packages, while SHA-256 checks succeeded. No driver/package installation, image pull, production engine rebuild or existing service change occurred. No containers were running before or after the tests.

## Practical next step

Keep bounded selection explicit and opt-in while evaluating it. It is supported here as a numerical repeatability control, not an accuracy repair. Resolve the verified training-domain/input/export contract before changing box coordinates, and test any model adaptation on new independent recordings with labels. A score threshold cannot repair the observed height error.

## Independent check of the new offline C++ helper

The newly developed pp_prepare_points helper was run on both original Koide inputs. Bounded outputs were byte-identical to the existing Python bounded_indices preparation (14,995 and 11,548 points). Passthrough preserved the original bytes. Retrying an existing output failed with exit1 and preserved the original output. Exact commands/source/binary identities: new-helper-independent-check.json. This does not add model inferences or enable a ROS input policy.

## Full same-bag confirmation

A separate [before/after comparison](OUSTER_BEFORE_AFTER_COMPARISON.md) now covers every 291 occurrence of one original Ouster bag, with 1,746 measured inferences. Candidate repeat matching improves 98.904%→100%; accepted-box repeat matching improves 99.761%→100% at the declared 0.001 tolerance. Accepted counts are unchanged on every scan (418 events per pass), and no labeled accuracy improvement is established. This later run uses the actual new C++ helper and does not replace the earlier 18-inference controls or frozen 1,120-observation study.
