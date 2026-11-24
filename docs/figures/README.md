# Figures, captions and source records

## Retained images — 21 November 2026

The [latest investigation](../OUSTER_VERIFICATION_AND_PERSON_DIAGNOSIS_20261121.md) embeds actual user screenshots and generated measurement plots. [Named figure provenance](2026-11-21/provenance.json) records captions and SHA256 hashes. The [preservation guide and complete gallery](../IMAGE_ARCHIVE.md) retain all available originals, drafts and negative results.

| Figure | Evidential role |
| --- | --- |
| [Controlled comparison](2026-11-21/multi-agent-comparison.png) | Previously inspected 16 test scans, three repeats, gate 0.3; negative pedestrian result |
| [Exact person case](2026-11-21/exact-person-frame1403.png) | Verified source-point association and nearby candidate geometry; not full 3D ground truth |
| [Head](2026-11-21/user-head-point39860.png) / [partial lower body](2026-11-21/user-lower-point111712.png) | Same source frame; lower point is not feet |
| [Movement montage](2026-11-21/raw01-movement-montage.png) | Original XYZ over the user-provided interval; no semantic annotation |
| [Blue prediction](2026-11-21/user-moving-person-03.png) / [orange prediction](2026-11-21/user-moving-person-07.png) | Qualitative misplaced predictions; exact screenshot frames unverified |

Use the final exact-person plot for discussion. Its earlier published-only and wide-label versions remain retained as drafts. Captions must preserve score, class, projection and partial-occlusion limitations. RViz camera parameters are not physical calibration. The user corrected the first feet label to head.

Reviewed 9 November 2026. Use this catalog when adding an image to a presentation or thesis. Each figure has a different evidential role: an actual annotated comparison can support a diagnostic result, while a screenshot only demonstrates the view captured at that time.

## Current Ouster study

| Figure | Suggested use | Source record |
| --- | --- | --- |
| [Archived results summary](ouster-channel-results-summary.png) | Historical asset; current thesis uses an editable results table | [Summary provenance](ouster-channel-results-summary-provenance.json) |
| [Ground-truth scene comparison](ouster-channel-ground-truth-2026-11-08.png) | Methods/discussion: actual outputs against supplied boxes in a fixed scene | [Scene provenance](ouster-channel-ground-truth-provenance.json) |

Suggested caption for the summary:

> Vehicle result on the frozen 16-scan Dur360BEV-Extended test subset at confidence 0.4. Precision and recall are means of five run results. Reflectivity/255 has four qualifying BEV matches per run, whereas signal/65535 has none. The four first-repeat BEV matches have 3D IoU below the required Vehicle threshold of 0.7. Repeats and matches across scans are not necessarily independent scenes or unique physical vehicles.

Suggested caption for the scene:

> Fixed middle test frame 1000007660, first repeat. Green boxes are publisher annotations; orange and purple boxes are signal and reflectivity predictions. The top view shows footprint alignment, and the side projection makes vertical displacement visible. Points are subsampled for rendering only. Dashed annotations have centers outside the model z evaluation range. This is a LiDAR projection, not a calibrated camera overlay.

The scene was selected by position in the frozen frame list, not by its output quality. The quantitative summary was generated from [the committed study record](../../config/ouster_channel_decision.json), without new inference. Underlying source: TomEeee / Durham University, Dur360BEV-Extended, publisher-declared **CC-BY-4.0**. Preserve attribution and the annotation/split limitations from [the decision report](../OUSTER_CHANNEL_DECISION.md).

The current thesis presents these quantities in native LaTeX tables. The earlier summary image remains archived with its provenance.

## Verified RViz filtering example

[rviz-filter-counters-2026-10-23.png](rviz-filter-counters-2026-10-23.png) is a 1600×900 capture of the tested RViz window. It illustrates original points, accepted boxes and the count marker: three accepted boxes from 94 post-NMS candidates, with 91 removed at score 0.5. Cumulative values count detection events.

Use it in an implementation or visualization section. It does not contain reviewed object ground truth and does not establish accuracy. The camera is a separate panel, not a calibrated box projection. It predates the recorded shutdown and is not a current live view.

[filter-counters-provenance.json](filter-counters-provenance.json) records image, source, model/engine and capture identities. Data: KITTI raw `2011_09_26_drive_0005_sync`; attribution Andreas Geiger, Philip Lenz, Christoph Stiller and Raquel Urtasun, KIT/TTI-C, **CC-BY-NC-SA-3.0**. The window was captured with `xwd` and converted losslessly with FFmpeg; no added boxes or overlays were drawn onto the image.

## Earlier owner-supplied screencasts

| Image | Original screencast | Decoded position | Size |
| --- | --- | ---: | --- |
| [rviz-screencast-1.png](rviz-screencast-1.png) | `Screencast from 2026-10-20 14-09-09.webm` | 32.035 s | 1920×1080 |
| [rviz-screencast-2.png](rviz-screencast-2.png) | `Screencast from 2026-10-20 14-13-14.webm` | 16.023 s | 1920×1080 |

These images illustrate the rendered points, boxes and scores. The filenames do not authenticate the recording, engine, feature recipe or experiment, so do not use them as an accuracy comparison. The supplied recordings originally lived under `/media/ae/New Volume/datasets/vedios`.

[provenance.json](provenance.json) records video/image hashes, byte counts and extraction details. Sequential decoding selected the first frame at or after each requested position because timestamp seeking failed. The PNGs preserve the decoded pixels without cropping, added overlays or synthetic imagery. Selection contact sheets remain ignored in local evidence.

## Archived engineering journey diagrams

| Historical figure | Former thesis use | Editable source |
| --- | --- | --- |
| [Development timeline](project-journey-timeline.png) | Opening of the engineering chapter: six recorded work periods and their distinct outcomes | [SVG](project-journey-timeline.svg) |
| [Diagnostic map](project-diagnostic-map.png) | Discussion of numerical failures, height error, capacity variation and missing ROS data | [SVG](project-diagnostic-map.svg) |

The timeline and diagnostic map are no longer embedded in the thesis or readable engineering chapter. They have been replaced with native chronology and diagnostic tables, plus a native diagnostic workflow in the LaTeX thesis. The archived images below are project-authored explanatory figures, based on the historical records and frozen reports. They contain no synthetic detections or newly measured benchmark results. The [provenance record](project-journey-figures-provenance.json) identifies sources and hashes. Arrows indicate the reasoning behind the next check, not proof of a unique root cause. The timeline does not imply that every earlier issue was solved.

Suggested timeline caption:

> Recorded stages of migration, integration and evaluation, October–November 2026. Each stage establishes a different level of evidence. Software migration and successful rendering precede, and do not replace, labeled accuracy assessment. Accurate 3D perception, production capacity handling and sustained latency acceptance remain open.

Suggested diagnostic caption:

> Observed symptoms, what the controlled checks establish, and the next justified investigations. Feature normalization removes the tested raw-signal numerical failure; the TRT8/NMS studies narrow the height-error investigation; capacity controls improve repeat behavior without repairing 3D accuracy. Matching ROS profiles fixes the measured discovery mismatch, while later large-cloud A/B delivery remains incomplete.

For final print layout, use the SVG originals in a suitable graphics workflow, retain readable text size and consider a landscape figure page. The thesis sources embed the PNG counterparts for compatibility; a static source check does not verify their final printed layout.

## Reusing figures in the thesis

Keep each image with its source record and caption. Distinguish project-generated plots from screenshots, and distinguish supplied annotations from model predictions. Do not relabel historical screenshots as the latest experiment. Maintain source attribution when copying any figure into another document.

The LaTeX sources search `figures/` from the docs directory and `docs/figures/` from the project root. The built-in standalone compiler may receive only the source file; an explicit placeholder then replaces an unavailable external image. A preview with placeholders is not the complete illustrated manuscript. The full project assets are required when compiling the final thesis template.

## Thesis casebook: editable tables and flowcharts — 9 November 2026

The current thesis explains all 50 problem groups and four detailed subcases using editable comparison tables, with native flowcharts for the main diagnostic workflows. The older `thesis/Jxx-evidence.png` report screenshots are no longer embedded in either thesis version or the casebook. They remain in the folder as historical assets. Every archived report identifies its evidence type and states that it is not an original incident screenshot. [Capture provenance](thesis/evidence-report-captures.json) records the browser command, source HTML hash and image hash. These reports summarize actual logs, preserved evidence or source inspection; their explanatory layout is not a recreated application interface.

Four original RViz images are preserved byte for byte, with dates, limitations and attribution in [original-capture provenance](thesis/original-captures-provenance.json). Two additional terminal images show actual current validator/decoder checks: `J03-live-validator-terminal.png` and `J37-live-decoder-terminal.png`. The J37 GPU outputs come from six new unlabeled numerical demonstrations, separately recorded from the frozen 1,120-observation study.

Use the individual captions in [the casebook](../THESIS_CASEBOOK.md). A diagram or screenshot does not establish object accuracy, a historical screenshot does not prove a service is running now, and a fixture does not prove that a physical driver failure was recreated.

The current tables and flowcharts are typeset directly in LaTeX; the readable drafts use Markdown tables and Mermaid diagrams. They explain recorded checks and decisions, and do not represent a newly executed experiment. Diagram branches distinguish observed corrections from proposed or unresolved work. See [the presentation review](../../config/thesis_native_panels_review.json).

## Actual same-scan before/after plot — 9 November 2026

An earlier catalog entry described `ouster-before-after-2026-11-09.png` and `ouster-before-after-provenance.json`, but neither file is present in this checkout. Their claimed occurrence-145 visualization was not reconstructed or revalidated. Use the available [21 November figures](2026-11-21/provenance.json) with their actual provenance; retain this note as an availability correction.
