# Confidence filtering and detection monitoring

Implemented on 23 October 2026. The publication layer keeps detections whose **score is at least `confidence_threshold`**. Detections below it are absent from `/bbox`: no box, class, position, pose or score for those detections reaches RViz or another subscriber. Kept detections retain their original fields, order, timestamp and frame ID.

The default is **0.5**, an adjustable starting setting, not an accuracy-calibrated recommendation. The threshold must be a finite ROS double in `[0,1]`. Equality passes. Set `0.0` to disable this additional gate; the model's built-in decode cutoff and existing NMS still apply. Scores are compared at their actual numeric values, rather than rounded score labels.

This is a score filter **after the existing CPU NMS**. It does not change weights, engine generation, the model's decode threshold, NMS IoU/top-N, point selection or coordinates. It can reduce low-score clutter, but cannot guarantee removal of false positives. Incorrect high-confidence boxes remain possible; the earlier raw Ouster experiment had incorrect-looking, saturated scores near 1.0. No new accuracy acceptance is claimed.

## Configure it

With the newly built node running, change the threshold for subsequent scans without restarting:

```bash
ros2 param get /pointpillars confidence_threshold
ros2 param set /pointpillars confidence_threshold 0.7
```

The change applies to the next processed scan. It does not republish or re-filter an already published scan. Invalid, nonfinite, out-of-range or incorrectly typed updates are rejected, retaining the committed parameter. Use decimal values such as `0.0` or `1.0`. Existing allocation/model/input parameters remain read-only.

For a node in Docker, using the same domain as that node:

```bash
sudo docker exec pointpillars /entrypoint.sh \
  ros2 param set /pointpillars confidence_threshold 0.7
```

Choose the initial setting through the deployment wrapper:

```bash
sudo env PP_CONFIDENCE_THRESHOLD=0.7 bash tools/deploy.sh
```

For direct `docker run`, pass `-e PP_CONFIDENCE_THRESHOLD=0.7` before the image name. An unset/empty environment variable uses `docker/node.yaml` (default 0.5). An explicit environment value overrides that YAML. Native startup accepts the normal ROS parameter override:

```bash
ros2 run pp_infer pp_infer --ros-args \
  --params-file /absolute/path/to/node.yaml \
  -p confidence_threshold:=0.7 -r __node:=pointpillars
```

The native YAML must also provide a valid engine path and existing required model settings. The historical native launch file still has old engine/topic settings; this feature does not modernize that launch interface.

**Use a newly built executable/image.** An already-running old container does not acquire local source changes. The existing Dockerfile fetches published Git source: the feature must be in the selected published revision before `tools/deploy.sh` includes it. Local native colcon builds use the current working tree. No commit/push, deployment replacement, Docker rebuild or running-container modification was performed while implementing this feature.

## Monitor the latest scan in RViz

The read-only shell helper can open the saved view:

```bash
bash tools/monitor_detections.sh rviz
# Keep the Ouster camera/detail view if that is your selected input:
RVIZ_CONFIG="$PWD/rviz/ouster_detail.rviz" bash tools/monitor_detections.sh rviz
```

Expand **Detection count (latest scan)** in RViz's Displays panel if needed. For an already-open/custom RViz view, add a **MarkerArray** display on `/bbox/count`, with **Reliable** reliability and **Transient Local** durability, using the cloud's fixed frame. Labeled KITTI uses `/kitti/predictions/count`. The standard MarkerArray display requires no additional count-display plugin.

The saved RViz profiles now contain **Detection count (latest scan)**, a standard MarkerArray display, and enable detection score labels. With inference and one player/sensor running, launch the appropriate viewer as before:

```bash
bash tools/visualize.sh
# Or an Ouster profile:
RVIZ_CONFIG="$PWD/rviz/ouster.rviz" bash tools/visualize.sh
```

The label appears at `(8,0,5)` metres in the incoming cloud frame and reports, for example:

```text
Latest scan: 12 boxes / 47 before score filter
score >= 0.7 | removed 35
Total published: 120 | total removed: 350
Processed frames: 10 | dropped input/inference: 0/0
```

The numerator is the number actually published in the detection array. The denominator is the count **after NMS but before the new score gate**, not the raw network candidate count. Adjust the viewing direction or move closer if the text is outside the current view. The cloud, detections and label share the original frame; no world transform is invented.

This is the last processed scan, not a tracked count of unique objects. The retained label is not a heartbeat and remains until the next frame/status update. Check its header stamp or topic rate to distinguish a paused stream from fresh data. On a rejected frame the label becomes a warning with **detection count unavailable**, rather than claiming that zero objects were detected. No detection array is emitted for that rejected frame, preserving the existing frame-drop policy; consumers may still show their previous successful scan.

## Monitor the statistics topic

Use [tools/monitor_detections.sh](../tools/monitor_detections.sh) from the project folder:

```bash
bash tools/monitor_detections.sh              # Continuously stream all counters.
bash tools/monitor_detections.sh once         # One retained snapshot; bounded wait.
bash tools/monitor_detections.sh threshold    # Read the currently configured threshold.
bash tools/monitor_detections.sh --help
```

The default `auto` backend sources host ROS Jazzy when installed, otherwise reads through the existing Docker container. To explicitly read inside the inference container:

```bash
PP_MONITOR_BACKEND=docker bash tools/monitor_detections.sh once
```

Use Docker permissions appropriate to your installation, such as `sudo env PP_MONITOR_BACKEND=docker bash tools/monitor_detections.sh once`. The Docker backend inherits the container's ROS domain unless you explicitly supply `ROS_DOMAIN_ID`; the host backend defaults to domain 0. The helper does not build/start inference or playback, change settings, or reset counters. If the snapshot/parameter request receives no response within 10 seconds, it exits with an explanation rather than claiming zero detections. `watch` runs until Ctrl+C. A retained snapshot can be old; inspect the header timestamp. The `threshold` mode queries the live parameter, while the statistics/marker threshold belongs to the last processed frame.

For a different topic/domain or native node name:

```bash
ROS_DOMAIN_ID=42 DETECTIONS_TOPIC=/kitti/predictions \
  bash tools/monitor_detections.sh once
PP_NODE_NAME=/minimal_publisher bash tools/monitor_detections.sh threshold
```

You can manually edit the defaults in the script: `backend`, `topic`, `node`, `container`, and `wait_seconds`. Environment settings `PP_MONITOR_BACKEND`, `DETECTIONS_TOPIC`, `PP_NODE_NAME`, `PP_CONTAINER_NAME` and `PP_MONITOR_TIMEOUT` override them. Use a positive `PP_MONITOR_TIMEOUT`, for example 20 seconds for slow discovery. For custom detection topics, supply a matching `RVIZ_CONFIG`; the helper selects the standard KITTI validation profile automatically for `/kitti/predictions`.

The existing standard `vision_msgs/msg/Detection3DArray` schema is unchanged. Its `detections` array length is the published box count. Richer counters are published separately as `diagnostic_msgs/msg/DiagnosticArray`:

| Default topic | Type | Contents |
| --- | --- | --- |
| `/bbox` | `vision_msgs/msg/Detection3DArray` | Only accepted boxes, with full usual information |
| `/bbox/stats` | `diagnostic_msgs/msg/DiagnosticArray` | Latest frame counts, threshold, cumulative detection events and dropped-frame counts |
| `/bbox/count` | `visualization_msgs/msg/MarkerArray` | RViz text label for the latest scan/status |

Monitor from a host ROS terminal with matching transport/domain:

```bash
ros2 topic echo /bbox/stats
ros2 topic echo /bbox/stats --qos-durability transient_local --once
ros2 topic hz /bbox
```

Or inspect from the running inference container:

```bash
sudo docker exec pointpillars /entrypoint.sh ros2 topic echo /bbox/stats --once
```

For a valid frame, `status[0].values` contains:

| Key | Meaning |
| --- | --- |
| `frame_status` | `ok`; failure states are `invalid_cloud` or `inference_error` |
| `confidence_threshold` | Exact threshold used for this frame |
| `post_nms_count` | Boxes returned by existing inference/NMS, before the publication gate |
| `filtered_count` | Boxes removed by this gate |
| `published_count` | Boxes actually emitted; equals `len(detections)` |
| `processed_frames_total` | Successfully published frames, including valid empty/all-filtered frames |
| `published_detections_total` | Sum of published boxes since node startup |
| `filtered_detections_total` | Sum of removed boxes since node startup |
| `invalid_cloud_frames_total` | Input frames rejected before inference |
| `inference_error_frames_total` | Frames rejected during inference/output validation |

For successful frames, `post_nms_count = filtered_count + published_count`. A valid all-filtered/empty frame publishes an empty detection array, with a zero count and normal status. On a dropped frame, the three per-frame counts are the string `unavailable`, diagnostics level is WARN, and successful-frame/detection totals do not increase. Aggregate counts are the only information retained about filtered detections; individual rejected box information is not published on another topic.

Cumulative totals reset when the node restarts. The same physical object detected in ten scans contributes ten detection events; there is no tracker or unique-object ID added here. Statistics and markers use reliable, depth-one, transient-local publication so a late monitoring subscriber can receive the last status. Detection delivery retains its existing reliable QoS/history.

Monitoring follows the **resolved detection topic**. If detections are remapped to `/kitti/predictions`, monitoring becomes `/kitti/predictions/stats` and `/kitti/predictions/count`. Standard KITTI profiles use that count topic. Custom detection remappings require the matching topic in a custom RViz configuration. Native node naming defaults to `/minimal_publisher` unless remapped; use the actual node name for parameter commands.

## Preserve accuracy comparisons

Existing saved reports, predictions, model/engine artifacts and inventory hashes remain untouched. Their numbers describe the earlier unfiltered publication policy.

For **new** KITTI baseline collection, `tools/kitti_accuracy.sh` explicitly requests threshold `0.0` on new images, verifies the live parameter, and records it in the new runtime identity. The exporter matches per-frame statistics by the cloud header and refuses a nonzero/changed gate or inconsistent counts, including a change made midway through collection. Older images without this parameter retain their old identity shape. A changed exporter/image/runtime identity requires a **new `PP_KITTI_OUTPUT` directory**; do not overwrite the frozen baseline. `report` continues to score existing frozen outputs without new collection.

To investigate accuracy at other thresholds, design a separate tuning/evaluation run and record the threshold; the baseline helper deliberately refuses that filtered policy. A lower box count alone is not evidence of fewer false positives or higher precision.

## Implementation and checks

`src/detection_output.cpp` and `include/pp_infer/detection_output.hpp` own the dynamic parameter, detection publication and monitoring. `make_detections` in `src/pointcloud_adapter.cpp` validates candidates before gating and constructs only accepted messages. The GPU node calls this shared output path for successful/empty frames and reports input/inference failures. ROS diagnostic/visualization message dependencies are declared in CMake, package metadata and Docker stages.

The TensorRT-enabled executable built successfully against the existing local SDK. All **five C++/ROS tests** and **67 Python tests** passed; the latest stricter baseline check also passed the focused three-test rerun. The GPU-free ROS integration test exercises the same output class used by production: score boundaries, preserved full fields/headers/order, malformed outputs, live and rejected atomic parameter updates, real remapped detection/statistics/marker delivery, cumulative/zero/error counts and late subscribers. Python controls protect the baseline exporter against changed filtering. Shell/embedded-Python syntax and all seven RViz configurations were checked.

New GPU replay and actual desktop rendering of the count display remain unverified: `nvidia-smi` could not communicate with the host driver in this session. No existing container/image was replaced. Exact logs and scope are recorded in [the progress entry](../recovery/PROGRESS.md).

The shell helper subsequently passed six isolated routing/error/timeout tests and actual host ROS `once`/`threshold` reads from a temporary controlled fixture on domain 116. The TensorRT-enabled package was rebuilt and all five C++/ROS tests passed again, including cumulative totals and dropped-frame values in the actual MarkerArray text. These message-level checks do not establish desktop rendering or GPU accuracy. All fixture processes were stopped after the checks.
