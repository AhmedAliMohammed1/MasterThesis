# Evidence and terminology

Use this page when reading results or moving a paragraph into the thesis. The goal is to make each claim easy to check.

## What the main claims mean

| Claim | Evidence needed | What it does not establish |
| --- | --- | --- |
| The package builds | Compiler and test logs from the stated configuration | GPU access, delivery or accurate objects |
| Inference completes | Valid runtime outputs on recorded inputs | Correct labels or acceptable latency |
| ROS integration works | Matched input/output occurrences with headers and schema checks | Object accuracy or indefinite reliability |
| Results repeat | Declared matching rule across repeated identical inputs | Correct objects or stability across a moving scene |
| BEV match | Prediction overlaps a labeled footprint at the stated threshold | Correct height or sufficient 3D overlap |
| 3D match | Prediction and label meet the stated volumetric overlap threshold | Generalization to an independent collection |
| Accuracy accepted | Agreed metrics and targets on fresh, appropriate held-out data | A universal guarantee for every sensor or operating condition |

A clean log, high confidence score, small box count or attractive RViz view cannot replace object annotations.

## Current source-of-truth map

| Question | Recorded evidence |
| --- | --- |
| Which Ouster input is recommended? | [Channel summary](../config/ouster_channel_decision.json), interpreted in [the decision report](OUSTER_CHANNEL_DECISION.md) |
| What does the model expect? | [Model contract](../config/model_contract.json), actual runtime checks and engine metadata |
| What was the KITTI accuracy? | [KITTI inventory](../config/kitti_accuracy_inventory.json) and frozen evaluation report |
| What was compared between TensorRT versions? | [Reference inventory](../config/kitti_reference_inventory.json) |
| Did the adapter preserve data? | [Adapter bag validation](../config/ouster_adapter_bag_validation.json) |
| Did the fresh original bag replay work? | [Fresh visual validation](../config/ouster_fresh_visual_validation.json) |
| Were startup/cache/shutdown fixes tested? | [Launcher validation](../config/launcher_fix_validation.json) |
| Where did the figures come from? | [Figure catalog](figures/README.md) and adjacent provenance JSON |

Small summaries are versioned. Full recordings, first predictions, engine files and logs are generally ignored under `.recovery`, so they need a separate backup. A summary's hash references cannot be independently rechecked on another computer unless the corresponding evidence is available.

## Glossary

| Term | Plain-language meaning |
| --- | --- |
| Point cloud | A set of measured positions, often with additional channels |
| XYZI | x, y, z and one fourth feature called intensity |
| Signal | In the tested Ouster schema, a return-strength channel; some recorded drivers name it intensity |
| Reflectivity | A distinct Ouster channel with sensor-dependent compensation and encoding |
| Normalization | A numerical transformation such as division by 255; it is not automatically physical calibration |
| ONNX | A saved neural-network graph and weights |
| TensorRT engine | A GPU execution plan built from the model for a stated environment |
| Pillar | An XY cell grouping points vertically for the model's encoder |
| NMS | Non-maximum suppression: removing overlapping candidate detections according to a declared policy |
| Confidence gate | Keeping predictions whose score is at least a chosen threshold |
| BEV | Bird's-eye view, which evaluates the footprint from above |
| IoU | Intersection over union: overlap divided by the combined area or volume |
| TP / FP / FN | Matched prediction / unmatched counted prediction / missed counted annotation |
| Precision | The fraction of counted predictions that match labels |
| Recall | The fraction of counted labels that are detected |
| AP | Area under a precision-recall construction; its exact definition matters |
| ROI | Region of interest: the declared part of space included in an input or evaluation |
| QoS | ROS delivery settings such as reliability, history and durability |
| ROS domain | A discovery boundary; participating processes must use compatible settings |

## Numbers that must keep their context

The new Ouster study contains **1,120 measured inferences**, but only **80 distinct scans** across its two primary datasets. The 320-observation capacity control reuses the same 32 labeled scans. Five repeats are not five new scenes.

The labeled study uses 16 published train and 16 published test scans from one collection. Their indices are disjoint, but independent-drive separation is unverified. The test evaluation ROI contains 60 Vehicle and six Pedestrian annotations. Eleven of the original 77 test labels are outside the stated ROI. There are no Cyclist labels in the subset.

At confidence 0.4, primary reflectivity Vehicle BEV precision is **27.81% as the mean of five run ratios**. The paired-bootstrap aggregate-count precision is **27.78%**. The capacity-control precision is a different result, **21.99%**. These values must not be swapped or merged. Vehicle BEV recall is 6.67%; qualifying 3D matches remain zero for both channels.

The older KITTI result uses an upstream-style AP_R40 policy. The new Ouster evaluator uses a diagnostic continuous precision envelope. These are different definitions and datasets, so their AP percentages are not a direct leaderboard comparison.

## Thesis writing rules

- Describe the migration, integration and evaluation method as separate contributions.
- Say “completed all tested numerical observations” rather than “fully reliable.”
- Say “better Vehicle BEV agreement in this frozen comparison” rather than “reflectivity is always more accurate.”
- Say “zero qualifying 3D matches” rather than “zero 3D overlap.” Some boxes overlap but fail the required threshold.
- Describe the Dur360 annotations as publisher-supplied, model-assisted and human-reviewed according to the original paper; the Extended annotation process is not separately documented.
- Label the bounded point-selection experiment as a sensitivity control, not deployed preprocessing.
- Keep proposed acceptance targets separate from agreed requirements and achieved results.
- Cite primary research and dataset sources for background; cite project evidence for project-specific numbers.

## Engineering history and thesis coverage

The [engineering journey](ENGINEERING_JOURNEY.md) links 50 documented problems to their implementation or experimental evidence. It distinguishes an implemented remedy, a diagnostic finding and an unresolved proposal. The same narrative and register appear in both thesis drafts. [History-review coverage](../config/thesis_history_review.json) records the sources reviewed and the limitations of the native PDF check.
