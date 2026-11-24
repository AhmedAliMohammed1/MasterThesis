# Validation plan: from working inference to trustworthy results

Reviewed 8 November 2026. The pipeline works, but its current 3D accuracy does not meet acceptance. This plan explains what evidence we already have, what the unresolved questions mean, and how to test the next change fairly.

The immediate development choice is **reflectivity/255**, supported by the labeled Ouster comparison. It remains an experimental input encoding. The recommendation is specific to this model, preprocessing and sample; it does not establish universal superiority over signal or an accurate 3D configuration. Read the [full channel decision](OUSTER_CHANNEL_DECISION.md) before using it as an accuracy claim.

## Three questions that need separate answers

| Question | Evidence available | Still needed |
| --- | --- | --- |
| Does the software move and preserve the intended data? | Adapter conversion tests, original-bag replay, ROS counters and RViz checks | Sustained target-sensor transport, failure recovery and resource tests |
| Does the migration preserve the intended model behavior? | Exact artifact/label identities, independent TensorRT 8/10 compatibility comparison, identical-candidate NMS agreement | Original-training/reference behavior, input semantics and bounded preprocessing |
| Are the detected objects correct? | Frozen labeled KITTI and Dur360 diagnostic measurements | A justified correction/model and fresh recording-disjoint acceptance evaluation |

A successful replay answers the first question. It cannot substitute for the other two. Similarly, repeating a wrong box reliably does not make it accurate.

## Current evidence

The exact ONNX matches NVIDIA's `deployable_v1.1` package identity. Its verified labels are ID 0 Vehicle, ID 1 Pedestrian and ID 2 Cyclist. The export encodes roughly x/y [−51.2,51.2) m and z [−1.4,4.4) m, voxels [0.2,0.2,5.8], 10,000 pillars, 32 points per pillar and a decode score threshold of 0.1. These are this artifact's attributes; generic training examples must not override them. The [partial model contract](../config/model_contract.json) records sources and gaps. Artifact-bound runtime enforcement remains unfinished.

The frozen [KITTI baseline](KITTI_ACCURACY_RESULTS.md) has zero moderate 3D matches for all three classes on 16 test frames. Its 16 tuning and 16 test frames are separated by recording drive. The [independent compatibility reference](MODEL_REFERENCE_COMPARISON.md) reproduces poor accuracy and roughly 1.53 m upward car error. NMS selects identical boxes on identical candidates, but exact inference/training parity is not established.

The [new Ouster study](OUSTER_CHANNEL_DECISION.md) adds 1,120 measured production-C++ GPU inferences. At confidence 0.4, reflectivity/255 matches four of 60 in-region test vehicles in BEV on every repeat; signal/65,535 matches none. Both have zero qualifying 3D matches and no recorded inference failures. The labeled scans are a frozen diagnostic subset of Dur360BEV-Extended; their published index splits are not verified as recording-disjoint. MOSEP weather runs are unlabeled numerical/transport evidence, not weather accuracy measurements.

Twenty of 32 primary labeled Ouster scans exceed the 10,000-pillar limit. A separate bounded-capacity sensitivity test reduces repeat changes but does not repair 3D accuracy. It is not deployed preprocessing. Both channels preserve identical geometry within each experiment, including the same explicit labeled-data capacity adaptation.

## Next experiment: resolve input and capacity handling

1. Write down the sensor schema, valid-return rule, coordinate frame, units and fourth-feature formula. Distinguish an original `intensity` field representing Ouster signal from a generic intensity field. Do not guess aliases.
2. Audit original and retained point counts, nonfinite/zero returns, occupied pillars and points per pillar. A total point count below 204,800 does not guarantee compliance with the internal pillar limits.
3. Implement any selected bounded preprocessing as a separate, reviewable change. Preserve source files and point identities; record exactly which points are retained and why. Use identical selected geometry when comparing channels.
4. Test boundary conditions and deterministic behavior. Compare the new path with the unchanged production baseline on development data before drawing an accuracy conclusion.
5. Freeze the resulting recipe and rerun independent annotations. Keep the current poor baseline available for comparison.

The existing first-encountered-pillar control is a diagnostic candidate. It does not reproduce CUDA thread encounter order and has not been selected as the final operational policy.

## Investigate height and training conventions

Trace sensor origin, calibration, training coordinates, anchor centers, decoder output and box conversion. The published decoder uses geometric centers derived from anchor bottom plus half height; an extra blanket half-height adjustment is not justified. KITTI annotations need their explicit calibrated bottom-to-center conversion. Dur360's loader convention uses geometric LiDAR centers directly.

The four first-repeat reflectivity BEV matches are 0.60–1.14 m too high. This supports investigation of vertical behavior; it does not identify a correction for all objects. Confirm a proposed fix against a mathematical fixture and a validated reference, then measure its effects on independent labeled scenes. Do not infer a fixed z offset from the inspected test labels or change only the rendered boxes.

If the current export remains unsuitable after these checks, evaluate an Ouster-compatible trained model or fine-tune on labeled Ouster development recordings. Model suitability and software migration are separate research questions.

## Freeze an acceptance evaluation

Select data before looking at predictions. Use recording-disjoint tuning and test groups, retain negative scenes, and include representative distances, weather and supported classes. The current inspected KITTI and Dur360 test frames are now diagnostic material. A larger selection containing them is not automatically untouched acceptance data. The original model's training-frame list is unavailable, so pretrained overlap cannot be certified.

Record the following before the final run:

| Item | Required record |
| --- | --- |
| Input | Dataset identity, checksums, frame IDs, split and excluded-label counts |
| Geometry | Frame, units, valid returns, capacity policy, spatial coverage and calibration |
| Model | ONNX/engine hashes, classes, precision, plugins, GPU and software |
| Postprocessing | NMS/top-N, class mapping, confidence gate and matching thresholds |
| Metrics | Per-class BEV/3D precision, recall, AP definition, localization errors and confidence intervals |
| Reliability | Failed inputs/inferences, delivery loss, repeat variation, latency and memory behavior |

Use official KITTI AP_R40 only with its declared difficulty, ignore and visibility rules. The Ouster diagnostic continuous-envelope AP is a different measure. Never compare the two as if they were one benchmark. Repeated inference measures variability; it does not increase the number of independent scenes.

## Proposed acceptance and completion criteria

No project-wide accuracy target has been approved. The channel proposal suggests a pilot gate of zero invalid-input/inference failures, verified capacity compliance and at least 80% precision and recall per supported class at the declared 3D IoU and fixed threshold. This is a proposal requiring agreement, not an established requirement or a safety standard. Current results are far below it.

Validation is complete only when the artifact-bound input/class/box conventions are tested, the independent reference checks pass within declared tolerances, and a frozen untouched dataset meets agreed application targets. Preserve both successes and failures with runnable commands and hashes. Two clean allocation probes do not establish internal tensor-bounds safety or race freedom.

## Reproduction routes and sources

Start with [KITTI data preparation](KITTI_VALIDATION_DATA.md), [KITTI scoring](KITTI_ACCURACY_RESULTS.md), [TensorRT reference comparison](MODEL_REFERENCE_COMPARISON.md), or [Ouster channel reproduction](OUSTER_CHANNEL_DECISION.md#reproduction-and-evidence). These guides distinguish prerequisite preparation, inference, evaluation and viewing. Use fresh output directories when source, model, recipe or dataset identity changes.

Primary sources used for the recorded contract:

- [NVIDIA deployable_v1.1 manifest](https://api.ngc.nvidia.com/v2/models/nvidia/tao/pointpillarnet/versions/deployable_v1.1/files) and [label file](https://api.ngc.nvidia.com/v2/models/nvidia/tao/pointpillarnet/versions/deployable_v1.1/files/label.txt).
- [NVIDIA model card](https://catalog.ngc.nvidia.com/orgs/nvidia/tao/models/pointpillarnet/-?_lr=1) and [TAO PointPillars input/evaluation documentation](https://docs.nvidia.com/tao/tao-toolkit/6.26.03/text/cv_finetuning/pytorch/point_cloud/pointpillars.html).
- [TensorRT 10.16 decoder source](https://github.com/NVIDIA/TensorRT/blob/release/10.16/plugin/common/kernels/decodeBbox3DKernels.cu) and [decoder documentation](https://github.com/NVIDIA/TensorRT/blob/release/10.16/plugin/decodeBbox3DPlugin/README.md).
- [KITTI benchmark rules](https://www.cvlibs.net/datasets/kitti/eval_object.php?obj_benchmark=3d).
- [Dur360BEV-Extended](https://huggingface.co/datasets/TomEeee/Dur360BEV-Extended) and its pinned loader/paper references in the channel report.

Source identities are preserved in the inventories. This documentation update does not re-fetch or re-validate external publications.
