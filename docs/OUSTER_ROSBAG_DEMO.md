# Non-KITTI Ouster ROS 2 bag demo

> **Status reviewed 23 October 2026.** The raw-signal failures below remain the baseline. Explicit reflectivity_div255 replay later matched all 556 input/output occurrences without recorded detector errors. Camera playback and the original-data detail view are available; raw_signal is still this helper’s default, and accuracy remains unmeasured. [Current results and evidence](CURRENT_STATUS_AND_RESULTS.md).

This separate helper uses Kenji Koide's (AIST) **LiDAR-camera calibration dataset, v3**, recorded with an **Ouster OS1-32** and an STC-MCS500POE camera. The source is [Zenodo record 7780490](https://zenodo.org/records/7780490), DOI `10.5281/zenodo.7780490`, licensed CC-BY-4.0. Preserve that attribution with redistributed data.

The publisher's `ouster.tar.gz` contains two native ROS 2 bags with `/points` (`sensor_msgs/msg/PointCloud2`), `/image`, and `/camera_info`. The download is **1,521,635,387 bytes** (about 1.52 GB), pinned by the publisher's MD5 `a0a56bbb93433f729a9e924744ad6b0c`. Extracted-file SHA256 hashes and a complete scan audit are saved locally. This is a different sensor and scene source from KITTI; it is calibration data, **not labeled object-detection evaluation data**.

## Prepare and inspect

Run from the project folder as your desktop user:

```bash
bash tools/rosbag_ouster.sh prepare
bash tools/rosbag_ouster.sh info
```

Default assets are under ignored `.recovery/rosbags/ouster_calibration_v3`. Preparation requires host ROS Jazzy Python packages and NumPy for deserialization/auditing, plus Python 3 and curl. Playback uses the existing `pp-infer:jazzy-trt10` Docker image. Docker access requests sudo if necessary; no software is installed automatically. Allow roughly 6 GB for archive and extracted bags. The archive download resumes interrupted transfers and must pass publisher size/MD5 checks before extraction. Extraction rejects archive links and traversal paths, and records SHA256 hashes. Reruns verify extracted bytes. Data are not committed or included in Docker builds; retain a separate backup.

`inventory.json` lists both sequence folder names, all point fields, frame IDs, cloud counts, min/max scan sizes, timestamp span, intensity range, nonfinite XYZI points, and any clouds exceeding the engine's 204,800-point input capacity. The input audit requires scalar FLOAT32 x/y/z/intensity. Incompatible inputs require a documented adapter rather than a hidden cast or sampling step.

## Switch from KITTI to Ouster

Keep the detector running. Stop the existing KITTI helper player first, in another terminal:

```bash
bash tools/rosbag_demo.sh stop
bash tools/rosbag_ouster.sh
```

The new helper starts a separately named container, `pointpillars-ouster-bag`, loops at half recorded speed, forces reliable cloud delivery, and remaps `/points` to `/point_cloud`. It refuses to start while another labeled project player feeds the same topic/domain. Unlabeled/manual players must be checked separately. It does not start, rebuild, restart, or modify the detector.

To select the other bag, use its exact name from `inventory.json`:

```bash
PP_OUSTER_SEQUENCE=sequence_folder_name bash tools/rosbag_ouster.sh
```

Both players cannot feed the same inference topic simultaneously if the results are to be interpretable. For a separate experiment, use a different `ROS_DOMAIN_ID` consistently for the detector, player and viewer. To stop only this helper's player:

```bash
bash tools/rosbag_ouster.sh stop
```

Ctrl+C in its foreground terminal also stops it. The stop action checks the ownership label before stopping any container.

## Sensor frame and visualization

Both downloaded bags use **`laser_data_frame`**. The separate `rviz/ouster.rviz` view selects that frame and enables score labels:

```bash
RVIZ_CONFIG="$PWD/rviz/ouster.rviz" bash tools/visualize.sh
```

RViz subscribes to `/point_cloud` and `/bbox`. Enable **Detections → Show Score** to inspect confidence. Match `ROS_DOMAIN_ID` to playback/inference. If using a fixed frame other than the sensor frame, provide a valid TF transform. Default playback publishes only point clouds. Set `PP_OUSTER_CAMERA=1` to include the original camera topics and use `rviz/ouster_camera.rviz` for a separate Image panel. See [camera videos and playback](OUSTER_CAMERA_VISUALS.md) for the exported MP4s and timing limits.

## Explicit processing limits

With the default `PP_OUSTER_FEATURE=raw_signal`, original cloud payloads, sensor frames, intensity values and acquisition timestamps are preserved; only the playback topic and publication QoS change. The later controlled experiment added explicit feature-conversion options, described in [the feature comparison](OUSTER_FEATURE_COMPARISON.md). These change only the fourth feature in a separate derived bag. No empirical z shift, confidence filter, point sampling or production pillar-capacity correction is added. The default detector intensity scale remains its configured value (currently 1.0 in Docker). This is a reproducible initial sensor comparison, not a claim that that value matches the model's training contract.

Input-point compatibility does not guarantee internal pillar compatibility. The export still has a 10,000-pillar/32-points-per-pillar limit, and that issue remains unresolved. Good visualization does not establish detection accuracy. Evaluate reviewed labels from representative target-sensor data before choosing thresholds or adapting the model.

## Short playback and other settings

```bash
PP_BAG_LOOP=0 PP_BAG_DURATION=10 bash tools/rosbag_ouster.sh
PP_BAG_RATE=1 bash tools/rosbag_ouster.sh
ROS_DOMAIN_ID=99 bash tools/rosbag_ouster.sh
```

`PP_BAG_DURATION` is recorded-time seconds, not wall-clock seconds. Other settings: `PP_OUSTER_DIR`, `PP_OUSTER_SEQUENCE`, `PP_OUSTER_CONTAINER`, `PP_IMAGE`, `POINT_CLOUD_TOPIC`. Use `--help` for defaults. Unknown sequences and oversized scans fail rather than changing the data.

Implementation: `tools/prepare_ouster_demo.py` handles preparation/audit; `tools/rosbag_ouster.sh` handles modes and playback. Focused controls live in `tests/test_ouster_demo.py`.

## Measured preparation (13 October 2026)

| Sequence | Clouds | Points per scan | Cloud timestamp span | Intensity range |
| --- | ---: | ---: | ---: | ---: |
| `rosbag2_2023_03_28-16_25_54` (default) | 291 | 32,768 | 29.014 s | 0–9,059 |
| `rosbag2_2023_03_28-16_26_51` | 265 | 32,768 | 26.435 s | 0–6,910 |

All 556 clouds had native FLOAT32 XYZI, consistent layout, zero nonfinite XYZI points and no total-point-capacity excess. The source cloud topic is `/points` and frame is `laser_data_frame`. These intensity ranges differ markedly from KITTI: using the existing scale 1.0 preserves source data but does not establish training-compatible normalization. Ouster also supplies a separate UINT16 `reflectivity` field; the current detector uses the FLOAT32 `intensity` field, not reflectivity. No model/input adjustment was made. Archive and extracted assets occupy about 3.8 GiB locally.

## Runtime observations and limits

The existing deployment image/engine was tested on isolated ROS domain 99, with ten recorded seconds of each sequence at rate 0.5. Host subscribers received **25 timestamp/frame-matched valid detections for each bag** with no invalid fields in those received messages. This confirms that both prepared bags can travel through playback, inference and publication. It is **not a clean all-frame inference pass**: the full temporary-detector log recorded **51 frame drops** with `Invalid output box` across the two runs.

Among the first run's matched frames, published counts ranged from 431 to 819 boxes (median 650), with median score 1.0. For the second run, counts ranged from 672 to 755 (median 724), with median score approximately 1.0. These excessive, saturated predictions and invalid outputs need investigation of the input/training contract, features and model behavior; high confidence here is not evidence of correctness. No threshold or input correction was installed to hide the behavior. The dataset has no detection labels, so accuracy is unmeasured.

Five focused controls passed: valid XYZI/capacity reporting, explicit refusal of integer intensity, malformed/overlapping fields, archive traversal/link rejection, and refusal to stop an unowned container. Bash syntax, Python compilation, publisher checksum and Jazzy bag inspection passed. Test playback and the temporary detector were stopped.

Exact source, extraction hashes, engine/image identity, scan audit, helper hashes and observations are recorded in `config/ouster_demo_inventory.json`; raw logs live in ignored `.recovery/verification/ouster-*`. Sensor frame/score-label display is configured in `rviz/ouster.rviz`; no new actual RViz rendering check was claimed during this run.

## Optional normalized feature replay

The [same-scan feature experiment](OUSTER_FEATURE_COMPARISON.md) identified unscaled Ouster signal as a contributor to nonfinite box lengths and excessive saturated predictions. To view the tested bounded reflectivity encoding without overwriting the source bags:

```bash
PP_OUSTER_FEATURE=reflectivity_div255 bash tools/rosbag_ouster.sh
RVIZ_CONFIG="$PWD/rviz/ouster.rviz" bash tools/visualize.sh
```

This is an explicitly selected diagnostic candidate, not a validated model calibration. The default remains `raw_signal`; other experiment options are `signal_div65535` and `reflectivity_fraction`. Conversion prepares a cloud-only derived bag, preserves all non-intensity cloud bytes and timestamps, and requires the detector's intensity scale to stay 1.0. The launcher now includes a two-second publisher-discovery delay (`PP_BAG_DELAY`). The original high-score/invalid-output measurements above remain the historical raw-input baseline.

## Camera videos and visual playback

Both camera recordings are now extracted as MP4 previews. Run `bash tools/rosbag_ouster.sh videos` to verify/reuse them. For combined normalized LiDAR and camera playback, use `PP_OUSTER_CAMERA=1 PP_OUSTER_FEATURE=reflectivity_div255 bash tools/rosbag_ouster.sh`, then open `rviz/ouster_camera.rviz` through `RVIZ_CONFIG`. See [the camera guide](OUSTER_CAMERA_VISUALS.md) for video paths, sequence selection, attribution, the approximately 2 Hz camera rate and different sensor header clocks.

## Original scene-detail view

Use `tools/rosbag_ouster_detail.sh` and `rviz/ouster_detail.rviz` to display original `/ouster/raw_points` independently of normalized inference. The brighter, closer profile exposes original signal colors as an optional display. Source scans are preserved in full; many source zero-range entries still overlap at the origin. See [the detail and frontal comparison guide](FRONTAL_COMPARISON_AND_RVIZ_DETAIL.md) for the separate, denser KITTI road recording and commands.
