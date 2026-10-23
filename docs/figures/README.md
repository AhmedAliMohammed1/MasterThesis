# Documentation figures — 23 October 2026

These full-resolution PNGs were extracted from the user's local screencasts in `/media/ae/New Volume/datasets/vedios`. Source filenames indicate 20 October 2026; no acquisition date or experiment identity is inferred beyond that filename.

| Figure | Source WebM | Decoded offset | Size |
| --- | --- | ---: | --- |
| [rviz-screencast-1.png](rviz-screencast-1.png) | `Screencast from 2026-10-20 14-09-09.webm` | 32.035 s | 1920×1080 |
| [rviz-screencast-2.png](rviz-screencast-2.png) | `Screencast from 2026-10-20 14-13-14.webm` | 16.023 s | 1920×1080 |

[provenance.json](provenance.json) records exact SHA256 hashes for both videos and PNGs, source byte counts, requested offsets and extraction details. Decode was sequential with OpenCV 4.6.0's FFmpeg backend because timestamp seeking failed for these WebM files. The first decoded frame at or after each requested offset was saved losslessly after BGR-to-RGB conversion. No cropping, resizing, overlays or synthetic imagery were applied. Contact sheets were used only for selection and remain ignored under `.recovery/verification/docs-2026-10-23/`.

The visible RViz windows show points, candidate boxes and scores. They support the illustration of rendering; they do not establish which bag, feature encoding, engine or runtime revision was used. They contain no reviewed ground truth or calibrated image projection and do not establish accuracy, sensor synchronization or real-time performance. See [current results](../CURRENT_STATUS_AND_RESULTS.md) for measured experiment evidence.

Retain these images beside the LaTeX sources when compiling outside the built-in editor. The LaTeX sources locate `figures/` from the `docs/` directory, or `docs/figures/` from the repository root, and provide a labeled placeholder if the compiler cannot access project images. A standalone preview that omits these assets is not the complete illustrated document.

The recordings were supplied by the project owner for this documentation. The depicted dataset cannot be authenticated from these screenshots alone. Preserve the existing KITTI and Ouster source attributions when sharing associated data or derivatives; their experiment-specific provenance remains in the respective guides and inventories.

## Verified filtering/counters capture — 23 October 2026

[rviz-filter-counters-2026-10-23.png](rviz-filter-counters-2026-10-23.png) is a separate **1600×900** capture of the actual tested RViz window, not a frame from the supplied WebM recordings. `xwd` captured that window and FFmpeg converted it losslessly to PNG; no crop, resize or added overlay was applied. It shows the KITTI front camera, original LiDAR, accepted boxes/scores and the published counter marker: 3 accepted, 94 post-NMS before filtering, 91 removed at 0.5. Cumulative values are detection events. The image predates the requested shutdown and is not a current live view or accuracy measurement.

[filter-counters-provenance.json](filter-counters-provenance.json) records the PNG SHA256, exact source/image/engine identities and shutdown. Data: KITTI raw `2011_09_26_drive_0005_sync`; attribution Andreas Geiger, Philip Lenz, Christoph Stiller and Raquel Urtasun, KIT/TTI-C, **CC-BY-NC-SA-3.0**. Camera is a separate panel, not a calibrated box projection; no ground truth is shown. Original screencast provenance remains unchanged.
