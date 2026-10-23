# Camera reference for the Ouster bags

> **Latest update — 23 October 2026:** confidence filtering and counters were pushed/deployed from `8a87a73`; 73 Python tests, five C++/ROS tests and 60 deployed GPU replay frames passed. The trial detector, KITTI player and RViz were then stopped at the user's request (19:47 UTC); image, engine cache and frozen results are preserved. Accuracy acceptance remains open. [Verified results and restart instructions](CURRENT_STATUS_AND_RESULTS.md#trial-shutdown-and-restart--23-october-2026).

> **Status reviewed 23 October 2026.** Both exported previews and merged playback are recorded: 111 image payloads, 111 CameraInfo payloads and 556 normalized clouds were preserved. Sensor header clocks remain unaligned; there is no calibrated detection overlay. New screencast figures illustrate RViz rendering without proving camera synchronization. [Current results and evidence](CURRENT_STATUS_AND_RESULTS.md).

Both source recordings contain `/image` and `/camera_info`. The images are original 2448×2048 BGR8 camera frames from Kenji Koide's AIST [LiDAR-camera calibration dataset v3](https://zenodo.org/records/7780490), DOI `10.5281/zenodo.7780490`, licensed **CC-BY-4.0**. Preserve that attribution with shared videos/data.

## Extracted videos

The project now provides H.264 MP4 previews, each 1280×1070:

| Recording | Original camera frames | Preview duration | Local path relative to project |
| --- | ---: | ---: | --- |
| First | 58 | 29.000 s | `.recovery/rosbags/ouster_calibration_v3/camera/rosbag2_2023_03_28-16_25_54/camera.mp4` |
| Second | 53 | 26.433 s | `.recovery/rosbags/ouster_calibration_v3/camera/rosbag2_2023_03_28-16_26_51/camera.mp4` |

The source camera is approximately **2 Hz**. Videos hold each image until the next recorded image; a 30 fps output container does not create new camera observations or motion interpolation. Preview frames are PNGs resized from the original images; full-resolution images remain in the source bags. The video starts at the first cloud's bag-record time, shows black for 0.271 s (first recording) or 0.393 s (second) before the first image, and holds the last image until the cloud timeline ends. Actual MP4 duration differs from the requested timeline by less than one video frame.

Export/reuse both videos:

```bash
bash tools/rosbag_ouster.sh videos
```

This checks source hashes, exports frames/timestamps, encodes pending videos, verifies codec/dimensions/duration using ffprobe, and promotes completed files. Reruns verify and reuse completed artifacts. Extraction requires host ROS Jazzy Python packages and Pillow. Encoding uses host FFmpeg if available, otherwise the existing `pp-infer:demo-tools` image (build it with `docker build -t pp-infer:demo-tools -f docker/demo-tools.Dockerfile .` if missing). Generated data remain ignored by Git and require independent backup.

Open either MP4 in a video player. A standalone player does not automatically synchronize with ROS playback. At the default bag rate 0.5, the ROS scene advances at half recorded speed; the exported video plays at recorded speed unless its player speed is adjusted.

## Camera and LiDAR in one ROS playback

For the tested normalized candidate and original camera payloads:

```bash
# Stop an existing Ouster helper player before switching its topic set:
bash tools/rosbag_ouster.sh stop
PP_OUSTER_CAMERA=1 PP_OUSTER_FEATURE=reflectivity_div255 bash tools/rosbag_ouster.sh
# In another terminal:
RVIZ_CONFIG="$PWD/rviz/ouster_camera.rviz" bash tools/visualize.sh
```

If no Ouster player is running, omit the stop command. Keep the inference node running separately. Match `ROS_DOMAIN_ID` across the player, inference and RViz. The new saved view contains the point cloud, detections with scores, and a **separate Camera image panel** on `/image`. It uses the ordinary RViz Image display, which requires no invented camera-to-LiDAR transform. Boxes are not projected onto the camera image.

Select the second recording with:

```bash
PP_OUSTER_SEQUENCE=rosbag2_2023_03_28-16_26_51 \
  PP_OUSTER_CAMERA=1 PP_OUSTER_FEATURE=reflectivity_div255 bash tools/rosbag_ouster.sh
```

`PP_OUSTER_CAMERA` defaults to 0, preserving the lighter cloud-only playback. With `raw_signal`, camera-enabled playback uses the original bag directly. With a feature conversion, a separate visual bag is generated under `.recovery/rosbags/ouster_calibration_v3/visual/<feature>/<sequence>/`. It merges original `/image` and `/camera_info` with the already verified converted `/points`, in bag-record timestamp order. Source payloads and headers are not reserialized or retimed during this merge. Reliable publication QoS is explicit for all three topics.

## Timing and interpretation

Camera and LiDAR headers use different clock values in these recordings: the first camera header is around 756 s, while the first LiDAR header is around 1744 s; bag record times are epoch-based. The helper preserves all of them. **Playback coordination uses recorded arrival times, not proven acquisition-time synchronization.** Camera intrinsics are present, but the bags do not establish the verified extrinsic/time calibration needed for detection overlays. These videos are unannotated scene references, not object-detection ground truth. The normalized feature candidate retains its previously documented accuracy/calibration limits.

## Verification and source files

Both MP4s passed codec/resolution/duration checks. The first PNG from each recording was visually inspected for orientation, colors and scene content. All 111 image messages and all 111 CameraInfo messages in the combined bags were verified byte-for-byte against the original serialized payloads and record timestamps. All 556 cloud payloads were verified against the previously prepared normalized bags. Video/export and merged-bag hashes are indexed in `config/ouster_camera_inventory.json`.

Implementation: `tools/export_ouster_camera.py` extracts/encodes videos; `tools/prepare_ouster_visual.py` builds combined replay bags; `tools/rosbag_ouster.sh` selects camera/video modes; `rviz/ouster_camera.rviz` adds the Image display. Camera timeline/payload controls are in `tests/test_ouster_camera.py`. Actual host camera/cloud reception is checked separately; no new actual desktop RViz rendering claim is made by the configuration file alone.

Host transport checks passed separately for each combined bag on isolated ROS domain 99: each received at least 20 normalized clouds, four original camera images and four CameraInfo messages with no validation errors. Twelve focused controls passed, along with Python compilation, Bash syntax and source whitespace checks. Short test players exited; the existing main-domain player was preserved.
