# Primary-bag detection discovery — 21 November 2026

The raw01 player, Ouster adapter, PointPillars GPU detector and desktop RViz were
started with Fast DDS/domain 99, reflectivity/255 and confidence 0.4. Playback loops
at 0.5 speed. RViz uses frame `ouster1_lidar`. Startup used the saved image without a
build or model change; original MCAPs were mounted read-only.

## Live baseline

A 25-second host ROS observation received 60 detection arrays, with 0–2 accepted
boxes per scan (mean 0.3833). The latest sampled detector diagnostic reported
101 processed scans, zero invalid clouds and zero inference errors. The latest
adapter diagnostic reported 99 received/converted and zero rejected clouds;
these snapshots are asynchronous, not a matched end-to-end delivery count.
A later snapshot showed 376 converted and 377 processed scans, again without
rejections/errors. Adapter logs also contain intermittent no-recent-cloud warnings.
Reception remains active, but replay delivery rate and gaps need a separate check;
no sustained throughput or low-latency acceptance is claimed.
The desktop capture verifies that RViz rendered the cloud, detections interface
and live counter. Generic class_0/class_1/class_2 labels remain in the image.

## Input audit

Five scans per recording were selected at 0%, 25%, 50%, 75% and 99% of MCAP
recording duration. Each organized cloud has 131,072 points. The samples contain
7,424–7,894 nonfinite XYZ points, removed by existing detector packing. Nonzero
finite points occupy 2,893–3,079 model-ROI XY pillars, below 10,000. An explicit
first-32-per-pillar policy removes 84,766–87,089 additional points and retains
36,207–37,915 points. These are sample measurements, not an exhaustive bag audit.

## Controlled same-scan experiment

The existing production C++ runtime/NMS was compiled in the saved reference image.
It reused the exact engine currently loaded by the live detector. Four input
variants crossed reflectivity/255 versus signal/65535 with baseline finite-point
packing versus the existing Python bounded-selection control. The bounded control
also crops to the encoded ROI. Geometry selection is identical across channels.
Three repeats of ten scans made **120 measured GPU inferences**, with two excluded
warmups, all successful. Jobs were shuffled with seed 20261121; outputs and source,
engine, image and sampled-CDR identities were saved.

| Bag | Feature | Policy | Median candidate repeat matching | Accepted events at 0.4 |
| --- | --- | --- | ---: | ---: |
| raw01 | Reflectivity/255 | Baseline | 8.33% | 1 |
| raw01 | Reflectivity/255 | Bounded | 100% | 0 |
| ouster1 | Reflectivity/255 | Baseline | 8.57% | 9 |
| ouster1 | Reflectivity/255 | Bounded | 100% | 6 |
| raw01 | Signal/65535 | Baseline | 0% | 0 |
| raw01 | Signal/65535 | Bounded | 100% | 0 |
| ouster1 | Signal/65535 | Baseline | 4.55% | 0 |
| ouster1 | Signal/65535 | Bounded | 100% | 0 |

Each table row covers 15 inferences: five scans × three repeats. Accepted events
are repeated detections, not unique objects. Matching uses the existing maximum
one-to-one matcher and 0.001 component tolerance, comparing each repeat to repeat 0.
100% tolerance matching does not mean identical binary outputs or correct boxes.
Bounded selection strongly improves measured numerical repeatability, but does
not increase accepted counts. No ground truth was available; accuracy is unknown.
Timings overlap live inference and are not a performance benchmark.

## Next changes supported by this evidence

1. Integrate the existing bounded C++ preparation helper into an explicit opt-in
   live mode, with counters and default baseline preserved. Verify ROS delivery,
   selected-point parity and repeated outputs before enabling it by default.
2. Annotate representative cars, people and cyclists actually present in these
   recordings. This model only supports Vehicle, Pedestrian and Cyclist. Measure
   precision/recall, 3D overlap and vertical alignment on a held-out recording.
3. Keep reflectivity/255 as the current baseline. Signal/65535 produced no accepted
   boxes in these sampled trials. Lowering the score gate to 0.2 exposes many more
   candidates but is a diagnostic preview, not demonstrated accuracy improvement.
4. Check sensor orientation, mounting height and expected training coordinates
   against annotations. If stable, correctly prepared inputs still fail, evaluate
   an Ouster-compatible model or fine-tuning. Do not fit a display-only box shift.

The live pipeline remains on its original baseline settings. No runtime source,
weights, engine or original recording was changed. Fourteen focused CPU tests
passed (five point-policy and nine reference/voxel controls). Prior frozen studies
retain their original datasets and results.

[Machine-readable summary](../config/primary_bag_detection_discovery.json).
Raw inputs, observations, desktop capture, scripts, exact identities and SHA-256
index are in `.recovery/verification/primary-bags-20261121-1301/` (ignored by Git).
The preparation scripts preserve original invocation paths under `/tmp`; use a
new output directory and adjust those paths when reproducing the experiment.
