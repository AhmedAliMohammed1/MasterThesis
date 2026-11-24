# Missed-person solution trials — 21 November 2026

The user identifies a person in a cropped RViz screenshot, says both primary
recordings contain them, and estimates distance 1.5–2m. The screenshot is from the
running raw01 replay. Exact time, direction, XYZ and 3D extent are unknown. The
user could not associate the separate recording-start reference map with their
position. The screenshot establishes a user-reported missed person, not a paired
3D ground-truth annotation for the frozen experiment frames.

## Work actually executed

Three specialist agents independently tried sampling, intensity and geometry.
The parent tested suppression and combinations. Five branches made **390 measured
GPU inferences**, plus six excluded warmups, all successful:

| Branch | Trials | What changed |
| --- | ---: | --- |
| Sampling agent | 90 | Five raw01 scans, six policies, three repeats |
| Intensity agent | 120 | Ten scans, four encodings, three repeats; identical even-order geometry |
| Geometry agent | 90 | Ten scans, input z0/−0.25/+0.25m, three repeats |
| Parent NMS observation | 30 | Ten scans, three repeats; export decoded candidates before CPU NMS |
| Parent combination control | 60 | Five raw01 scans, four combinations, three repeats |

Six warmups were excluded in sampling/NMS/combination branches (two each).
Intensity/geometry branches did not exclude separate warmups. No latency claim
is made, and GPU work overlapped the live pipeline. The current engine, model
weights and production inference sources were retained. The parent NMS harness
used an explicitly isolated source copy that bypasses CPU suppression for
observation; it is not installed into the running node.

Eight NMS policies (class-aware/agnostic × IoU .01/.1/.3/.5) were applied to each
of 30 identical saved candidate arrays: **240 CPU controls**, plus the unsuppressed
observations. Ground fitting and geometric clustering were also executed.

## Evaluation definition

The proxy target region is predicted class1 Pedestrian with horizontal radius
1.2–2.5m. This intentionally wider interval accommodates approximate user range.
It includes furniture and other surfaces, and predicted box centers can be displaced.
The evaluation measures scores, candidate retention, geometry and repeatability.
It does **not** measure actual person recall, precision or 3D IoU, because there
is no spatial/time-matched target annotation. Repeated events are not independent
people. A candidate with the highest score may be a different physical object
under each variant. No numeric score gain is called an accuracy gain.

## Measured results

| Solution | Highest nearby pedestrian score, raw01 | ouster1 | Interpretation |
| --- | ---: | ---: | --- |
| Current all-finite baseline (sampling branch) | .149 | not tested in this branch | No nearby accepted box |
| Stable even source-order geometry + reflectivity/255 | .178 | .193 | Baseline for intensity/geometry/NMS |
| New balanced-height-bin selection | .195 | not tested | Modest proxy-score increase |
| New height-quantile selection | .197 | not tested | Modest proxy-score increase |
| Same even geometry + clipped reflectivity/100 | .320 | .268 | Largest individual proxy-score increase |
| Constant intensity0 | .159 | no nearby candidate | No supported fix |
| Constant intensity0.5 | no nearby candidate | no nearby candidate | No supported fix |
| Same even geometry, input z+0.25m | .232 | .254 | Unverified height sensitivity, not calibrated transform |
| Same even geometry, input z−0.25m | .134 | .147 | Proxy scores decreased |
| NMS removed / alternate NMS policies | .178 | .193 | No hidden nearby score≥.4 |

Every tested solution had **zero nearby pedestrian events above the production
0.4 threshold** in these sampled trials. This is a proxy statement, not a measured
0% person recall. Clipped /100 improves some local scores while worsening some
other predictions and shrinking some nearby boxes, so higher scores alone do not
support a new default. Constant-intensity ablations demonstrate sensitivity to the
fourth feature, not its exact required physical calibration.

### Combination follow-up

These were exploratory settings selected after seeing individual results, not a
held-out comparison. All use clipped reflectivity/100 on the five raw01 scans:

| Sampling | Input z change | Maximum nearby score |
| --- | ---: | ---: |
| Even source order | 0 | .320 |
| Even source order | +.25m | .299 |
| Height quantiles | 0 | .308 |
| Height quantiles | +.25m | .269 |

Combining the apparent improvements did not compound their score gains. No nearby
candidate reached .4. Centers from translated inputs were transformed back to the
original sensor frame before geometric reporting. Selection happens before shifting,
so shifts can also alter model ROI retention; this is a sensitivity, not a clean
isolated test of a known mounting error.

### Suppression control

The highest nearby class1 score is .178/.193 in decoded candidates before NMS and
remains .178/.193 after all tested NMS settings. Looser/class-aware suppression keeps
more low-score hypotheses but exposes no nearby high-confidence pedestrian. Thus
NMS is not hiding a ≥.4 nearby candidate in these frozen even-order controls.
This does not prove NMS is irrelevant to every object or every source frame.

A synthetic coincident-different-class fixture verified that agnostic NMS keeps
one box while class-aware NMS keeps both. Standard-NMS replay matched the previous
stable run completely at tolerance .001 in9/10 cross-harness baseline comparisons;
one matched94.74%. Current suppression policies share exactly the same saved
candidate arrays, so their comparison remains paired, but full cross-harness parity
or bitwise determinism is not claimed.

## Geometry and possible occlusion

Constrained near-horizontal RANSAC was ambiguous: dense surface fitting suggested
z≈−.41m with only16–18% support; lower-envelope fits often suggested≈−.82m but
were unstable. No independently justified leveling correction was established.
The ±.25m trials are therefore explicit hypotheses only.

Ground/Euclidean clustering found one size-plausible nearby obstacle in sampled
raw01-.75 around XYZ(−.80,−1.51,−.26)m, extent(.96,.81,.97)m. It could be an
occluded person, furniture or a merged cluster; its height is insufficient to
identify it as a standing human. The independently selected nearby neural box in
this frame was around(−.52,−1.31,.44)m with dimensions(.54,.59,1.60)m and score.178.
Proximity does not establish identity, correct localization or a ground-truth match.

The reference-map A/B/C locations were extracted at recording start, not the
screenshot time; they are not annotations. The user could not identify their
location in that view. Preserve that uncertainty rather than selecting whichever
candidate makes a method appear successful.

## What the tests support next

1. **Create an exact paired target annotation.** Pause a frame where the user can
   point out the person. Save the original cloud header/bag record time and identify
   a person point/3D extent in that same cloud. This avoids asking the user to guess
   coordinates or time from a crop. Use separate annotated frames for tuning and
   untouched evaluation, and report occlusion/retained body geometry.
2. **Use the intensity and stable-sampling controls on that target.** Compare
   localized score, box position/height, BEV/3D overlap and false positives. If a
   .3 gate is previewed, label it diagnostic: it reveals existing candidates and
   does not improve the network or establish correct recognition.
3. **Verify mounting/feature semantics before promoting transforms.** A score
   response to an arbitrary height shift is not proof of an incorrect extrinsic.
4. **Train or benchmark a target-compatible detector if the paired target remains
   weak.** Target-sensor PointPillars fine-tuning and an independent CenterPoint-
   Pillar reference remain justified next learned-model experiments. The current
   branches used the existing PointPillars network; no new neural architecture was
   executed or retrained in this turn.

No tested setting is promoted to production. The live raw01 pipeline/RViz remain
on reflectivity/255, score gate.4 and playback rate1.0. Tests isolate an unconfirmed
nearby score response, not a solved detection miss. Fourteen focused point-policy/
reference/voxel tests passed; hash/status checks preserve all raw observations.

## Evidence

- Summary: `config/person_solution_trials.json`.
- Full scripts, prepared inputs, raw model outputs, sensor-frame outputs, CPU
  controls, agent reports and SHA256 index:
  `.recovery/verification/person-solution-trials-20261121/`.
- The user screenshot is retained with the evidence; no timestamp was invented.
- Prior reports remain separate. This work reuses the same10 frozen scans and does
  not add390 independent scenes or overwrite the earlier studies.
