# Start the project and replay Ouster data

Reviewed 8 November 2026. This guide starts with a working host NVIDIA driver, Docker and NVIDIA Container Toolkit. For a live sensor, its ROS driver must already work. Run commands from the project root. The current checkout is `/media/ae/New Volume1/MasterThesis`; quote that path because it contains a space.

**Current research choice:** use reflectivity/255 for development. It gave better vehicle localization from above than signal/65,535 on the annotated diagnostic subset, but both had zero qualifying 3D matches. [Results and proposal](OUSTER_CHANNEL_DECISION.md).

## 1. Prepare the image

```bash
sudo env PP_BUILD_ONLY=1 bash tools/deploy.sh
```

This checks the host GPU and Docker, then prepares or reuses `pp-infer:jazzy-trt10`. `PP_BUILD_ONLY=1` is **optional**: without it, deployment starts the detector only. Stop that detector before starting the combined Ouster launcher. Deployment does not start a driver, adapter, bag player or RViz automatically.

The default build uses local runtime source, including uncommitted changes. Matching runtime inputs reuse the image without invoking a build; documentation-only edits do not trigger one. Source changes reuse independent Docker dependency/model layers when available. First builds or missing caches need downloads. Drivers are never installed by this script. See [build controls](../docker/README.md#what-an-image-build-does).

## 2. Choose live sensor or recorded bag

| Profile | Raw input | ROS domain | Middleware | Prerequisite |
| --- | --- | ---: | --- | --- |
| Live: `start_ouster.sh` | `/ouster1/points` | 0 | `rmw_zenoh_cpp` | Working driver and reachable Zenoh router |
| Bag: `start_ouster.sh bag` | `/ouster1/points` | 99 | `rmw_fastrtps_cpp` | Primary `raw01` or `ouster1` MCAP on disk |

The settings come from `tools/ouster_profile.sh`. A visible topic requires matching middleware, domain and name. Host networking alone does not solve mismatches.

### Live sensor

```bash
sudo bash tools/start_ouster.sh
```

This starts the adapter and detector together, choosing reflectivity/255. For a driver using Fast DDS or another domain/topic, supply its actual settings:

```bash
sudo env RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_DOMAIN_ID=7 \
  OUSTER_POINT_CLOUD_TOPIC=/ouster/points bash tools/start_ouster.sh
```

Use `sudo env` because sudo can discard exported variables. Keep all consumers on the same settings. [Conversion details and signal selection](LIVE_OUSTER_ADAPTER.md).

### Primary experiment recordings: raw01 and ouster1

These are the primary inputs for new experiments as of 21 November 2026.
Use only one player at a time. Terminal 1:

```bash
sudo bash tools/start_ouster.sh bag
```

Terminal 2:

```bash
sudo bash tools/start_ouster_bag.sh        # raw01, default
# Or select the second recording:
# sudo bash tools/start_ouster_bag.sh ouster1
```

Default data root: `<checkout>/../rosbags`, currently `/media/ae/New Volume1/rosbags`:

```text
raw01/ouster1_raw_01_0-001.mcap
ouster1/ouster1_raw_02_0-001.mcap
```

The original MCAP file is mounted read-only and opened directly with `--storage mcap`;
`metadata.yaml` is not required. Playback selects `/ouster1/points`, defaults to
half speed, loops, and waits three seconds. It does not download or rewrite data.
For another location or a single full-speed pass:

```bash
sudo env PP_ROSBAGS_DIR='/absolute/path/to/rosbags' \
  PP_BAG_LOOP=0 PP_BAG_RATE=1 bash tools/start_ouster_bag.sh raw01
```

MCAP summaries report 2,783 clouds for raw01 and 1,841 for ouster1. The first decoded
cloud in each has frame `ouster1_lidar`, 1024 × 128 points, FLOAT32 XYZ, UINT16
`signal`, UINT8 `reflectivity`, and a 48-byte point stride. This schema fits the
existing adapter; the default remains reflectivity/255. Both files also opened successfully through ROS MCAP storage, with their first
cloud decoded. [Input inventory](../config/primary_rosbags.json). These checks establish
input identity and sampled layout, not full-recording inference or labeled accuracy.
New results must use new evidence directories and record which primary input was used.

### Historical MOSEP recordings

Explicit `dry`, `rain30` and `rain100` choices remain available. Their root is still
`PP_OUSTER_FRESH_DIR`, defaulting to
`.recovery/rosbags/ouster_mosep_fresh_20261107/original`. Their original topic
`/sensing/lidar/points` is remapped to the bag profile's `/ouster1/points`.
These bags name signal `intensity`; do not use the literal `signal` selector on them.
The frozen MOSEP, Koide, KITTI and Dur360 experiments retain their original identities
and results. [Historical download record](FRESH_OUSTER_VISUAL_TEST.md).

## 3. Open RViz

In another terminal on the graphical desktop, as your normal user:

```bash
bash tools/visualize.sh bag
```

This bag-specific command needs host ROS Jazzy, RViz and `vision_msgs_rviz_plugins`. For live data, match the actual middleware/domain and use the cloud's `header.frame_id`. The saved profile displays adapted points, detections and counts. The `bag` shortcut selects Fast DDS, domain 99 and the Ouster configuration with fixed frame `ouster1_lidar`; explicit environment overrides are preserved.

The viewer opens a new window. For an existing window, select **File → Open Config**. Rendering confirms message delivery; it does not validate object accuracy. [Measured prediction/ground-truth figure](OUSTER_CHANNEL_DECISION.md#why-3d-accuracy-still-fails).

## 4. Check processing

```bash
sudo docker logs --tail 80 pointpillars
sudo docker exec pointpillars /entrypoint.sh ros2 topic echo /ouster_adapter/stats --once
sudo env PP_MONITOR_BACKEND=docker bash tools/monitor_detections.sh once
sudo env PP_MONITOR_BACKEND=docker bash tools/monitor_detections.sh threshold
```

Adapter `received`/`converted` should increase; inspect `rejected` and its error message. Detector statistics distinguish successfully processed scans from invalid inputs and inference failures. A valid scan can have zero accepted boxes. A retained counter can be old, so inspect its timestamp. [Counter meanings](CONFIDENCE_FILTER_AND_MONITORING.md).

## 5. Stop and restart

Press **Ctrl+C once in each launcher terminal** and allow up to eight seconds for cleanup. Each launcher stops the exact container it created. The Ouster supervisor stops both adapter and detector process groups. The saved image, original bags and `pp-engines` remain.

For repeat runs, skip image preparation and repeat the chosen live/bag launch commands. If a name is occupied, inspect it with `sudo docker ps -a`; stop only the intended instance. The launchers preserve existing containers rather than replacing them.

## If startup does not work

| Symptom | Check |
| --- | --- |
| No recent clouds | Same raw topic, domain and middleware; live Zenoh router reachable |
| `Missing scalar Ouster field` | Actual schema and literal selected field name |
| Detector rejects XYZI | Use the adapter for Ouster fields; inspect point/byte limits |
| No image / missing adapter | Prepare current local source with optional `PP_BUILD_ONLY=1` |
| MCAP `serialized_metadata` warning | In the recorded replay this warning was nonfatal; check actual cloud counters |
| Clouds visible but boxes inaccurate | Consult annotated evaluation; successful transport is separate from accuracy |

[Detailed troubleshooting](LIVE_OUSTER_TROUBLESHOOTING.md) separates current checks from the original physical-host repair history.

## Recorded verification

The deployment/shutdown change passed 91 Python and seven C++/ROS tests at that stage. Actual GPU replay observed 20 raw clouds, 20 adapted clouds and 19 detection arrays, with zero sampled rejection/error counters. One interrupt removed the player in 0.490 s and pipeline in 0.487 s. [Run identity](../config/launcher_fix_validation.json). The later channel study increased the Python suite to 119 tests and made 1,120 direct GPU inferences; that study did not revalidate ROS A/B transport. See [current status](CURRENT_STATUS_AND_RESULTS.md).


## Pause and inspect one scan — verified Jazzy services, 21 November 2026

`play_next` succeeds only while the player is paused. `resume` starts continuous playback. These commands use the existing detector container environment; they do not change saved launcher defaults.

```bash
docker exec pointpillars bash -c '
source /opt/ros/jazzy/setup.bash
ros2 service call /rosbag2_player/pause rosbag2_interfaces/srv/Pause "{}"
ros2 service call /rosbag2_player/is_paused rosbag2_interfaces/srv/IsPaused "{}"
ros2 service call /rosbag2_player/play_next rosbag2_interfaces/srv/PlayNext "{}"
'
```

Repeat only the `play_next` call for further scans; use `/rosbag2_player/resume` with `rosbag2_interfaces/srv/Resume` to continue. Allow queued processing to settle. Source header timestamps can wrap/repeat; use stored bag record time and source hashes for exact evaluation.

For selected point XYZ, use **Panels → Add New Panel → rviz_common / Selection**, choose the Select tool, and expand a selected point's Position. Views/Pitch/Focal Point are camera settings. A rectangular selection may include background returns. See [the exact-person diagnosis](OUSTER_VERIFICATION_AND_PERSON_DIAGNOSIS_20261121.md).
