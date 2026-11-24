# Ouster adapter: convert the cloud before inference

Reviewed 8 November 2026. The adapter is a separate ROS 2 node between an Ouster publisher and PointPillars. It validates the cloud layout and writes a new FLOAT32 XYZI cloud using an explicitly selected channel. The original publisher and recording remain unchanged.

**Use reflectivity/255 as the experimental baseline for this model.** Independent annotated testing supports a vehicle advantage from above over signal/65,535, but both encodings have zero qualifying 3D matches. Neither is accepted as accurate. [Full comparison and proposal](OUSTER_CHANNEL_DECISION.md).

## What flows through the pipeline

```mermaid
flowchart LR
  A[Ouster driver or original bag] --> B[Adapter: validate schema]
  B --> C[Copy XYZ and header; convert chosen channel]
  C --> D[New FLOAT32 XYZI on /point_cloud]
  D --> E[PointPillars detector]
  E --> F[/bbox and monitoring]
  B --> G[/ouster_adapter/stats]
```

An already compatible XYZI publisher can feed the detector directly using `start.sh`. The Ouster launcher always runs conversion; it does not automatically select passthrough, choose a feature, calibrate a sensor or fuse two sensors.

## Start the complete pipeline with one command

With the driver already running and an image containing the adapter:

```bash
sudo bash tools/start_ouster.sh
```

The live defaults are Zenoh, ROS domain 0 and raw `/ouster1/points`. A reachable Zenoh router is required. Prepare/update the local image first if needed:

```bash
sudo env PP_BUILD_ONLY=1 bash tools/deploy.sh
```

Build-only mode is optional and avoids starting a second detector. The combined launcher starts adapter and detector in one foreground container. One Ctrl+C stops both; image and engine cache persist. It preserves an existing named container.

For the primary raw01/ouster1 recordings, select the matching bag profile:

```bash
# Separate terminals:
sudo bash tools/start_ouster.sh bag
sudo bash tools/start_ouster_bag.sh
```

Both use Fast DDS/domain 99/raw `/ouster1/points`. The player defaults to `raw01`; pass `ouster1` for the second primary recording. [Complete startup and RViz guide](STARTUP_AND_REPLAY.md).

## Conversion choices

| Choice | Command for a compatible live schema | New intensity |
| --- | --- | --- |
| Reflectivity | `sudo bash tools/start_ouster.sh` | `reflectivity / 255.0` |
| Signal | `sudo bash tools/start_ouster.sh signal` | `signal / 65535.0` |
| Custom divisor | `sudo env PP_OUSTER_INTENSITY_DIVISOR=100.0 bash tools/start_ouster.sh` | Selected value divided by 100; no clipping |

The selected field must actually exist. In the unchanged MOSEP and studied Dur360 recordings, the signal channel is named **`intensity`**. The current adapter selects the literal field `signal`; it has no production alias parameter. Therefore selecting `signal` on those originals rejects the cloud. The direct comparison tools verified and handled that alias separately. A verified field alias identifies the recorded channel; changing a datatype label without converting its bytes is not a valid numerical conversion.

Divisors are declared encodings, not proof of the model's training convention or sensor calibration. Reflectivity values from a UINT16 field can exceed 255; division does not automatically constrain output to [0,1]. The adapter does not blend signal and reflectivity or normalize by a per-scan maximum. Keep the detector's `intensity_scale=1.0` to avoid scaling twice.

### Parameters and overrides

| Parameter / launcher variable | Default | Meaning |
| --- | --- | --- |
| `input_topic` / `OUSTER_POINT_CLOUD_TOPIC` | `/ouster1/points` (live and bag) | Raw source |
| `output_topic` / `POINT_CLOUD_TOPIC` | `/point_cloud` | New XYZI cloud |
| `intensity_source` / `PP_OUSTER_INTENSITY_SOURCE` | `reflectivity` | Literal selected field |
| `intensity_divisor` / `PP_OUSTER_INTENSITY_DIVISOR` | `255.0`; signal launcher chooses `65535.0` | Positive numerical divisor |
| `intensity_clip_max` / `PP_OUSTER_INTENSITY_CLIP_MAX` | `0.0` (disabled) | Optional cap after division; `1.0` with divisor `100.0` gives clipped reflectivity/100 |
| `max_points` | 204800 | Maximum total points in the input message |
| `max_cloud_bytes` | 67108864 | Cloud-size bound |

Adapter parameters are read-only after startup. Restart to change the feature recipe. Input/output names must differ even after remapping. Topic discovery reports candidates but never switches input automatically.

For another driver setup:

```bash
sudo env OUSTER_POINT_CLOUD_TOPIC=/ouster2/points \
  ROS_DOMAIN_ID=7 RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
  bash tools/start_ouster.sh
```

Use separate adapter node names/topics for multiple sensors. No coordinate transformation, time synchronization or fusion is implemented.

## What the converter accepts and preserves

XYZ must be scalar FLOAT32, little-endian. The selected channel may be UINT8, UINT16 or FLOAT32. Validation checks counts, duplicates, selected-field overlap and bounds, row stride, exact data length, point/byte capacities and a finite positive divisor. Organized rows and padding are supported.

The output has 16 bytes per point: FLOAT32 `x`, `y`, `z`, `intensity`. It preserves the header, dimensions, point order and XYZ bits. Other channels remain in the source and are omitted from the new message. The selected channel is read numerically, divided in double precision and cast to FLOAT32. Negative/nonfinite/overflowing results reject the cloud. Nonfinite XYZ is preserved with `is_dense=false`; the detector subsequently removes nonfinite points.

This adapter does not remove finite all-zero invalid returns, crop to the model ROI, subsample oversized clouds or impose the internal 10,000-pillar/32-points-per-pillar limits. A 262,144-point Dur360 cloud exceeds the adapter's default total-point bound; the research preparation used an explicitly recorded compatibility crop/filter. That preparation is not automatically deployed here.

The raw subscription uses sensor-data best-effort QoS. Output requests reliable depth 5, matching the detector's reliable input. This bridges delivery policies; it does not guarantee every scan survives overload. The detector remains synchronous with depth 700.

## Inspect reception and conversion

```bash
sudo docker exec pointpillars /entrypoint.sh ros2 topic list -t
sudo docker exec pointpillars /entrypoint.sh ros2 topic info /ouster1/points --verbose
sudo docker exec pointpillars /entrypoint.sh ros2 topic echo /ouster_adapter/stats --once
sudo env PP_MONITOR_BACKEND=docker bash tools/monitor_detections.sh once
```

Use the actual raw topic for bag mode. The adapter publishes diagnostics every two seconds: selected topics/feature/divisor, publisher count, `received`, `converted`, `rejected`, accepted schema and discovered PointCloud2 candidates. An input schema is logged when it changes. No recent clouds produces a warning; the last conversion error produces error status until another valid cloud clears it. A paused bag can legitimately produce a no-recent-cloud warning.

If raw input arrives but conversions fail, inspect the field error. If conversions increase but detector processing does not, inspect the detector log and its domain/topic/limits. [Troubleshooting](LIVE_OUSTER_TROUBLESHOOTING.md).

## Build and run without a GPU

Only conversion needs ROS/PCL development dependencies; it needs no CUDA, TensorRT, model or engine:

```bash
source /opt/ros/jazzy/setup.bash
colcon --log-base .recovery/ouster-adapter-log build --packages-select pp_infer \
  --build-base .recovery/ouster-adapter-build \
  --install-base .recovery/ouster-adapter-install \
  --cmake-args -DPP_BUILD_RUNTIME=OFF -DPP_BUILD_ROS_ADAPTER=ON \
    -DBUILD_TESTING=ON -DPython3_EXECUTABLE=/usr/bin/python3
source .recovery/ouster-adapter-install/setup.bash
export RMW_IMPLEMENTATION=rmw_zenoh_cpp ROS_DOMAIN_ID=0
ros2 launch pp_infer ouster_adapter_launch.py \
  input_topic:=/ouster1/points output_topic:=/point_cloud \
  intensity_source:=reflectivity intensity_divisor:=255.0
```

This launch file starts only the adapter. Start a detector separately with matching middleware/domain and `/point_cloud`, or use the combined container launcher instead. [Native full-runtime setup](local_runtime.md).

## Evidence and its limits

Conversion tests cover layouts, numeric conversion, headers/XYZ, malformed inputs and ROS delivery. Offline verification exercised 556 original legacy scans in four declared cases, totaling 2,224 conversion observations; reconstructed live schemas were explicitly distinguished from original data. [Conversion inventory](../config/ouster_adapter_bag_validation.json).

A fresh unchanged MOSEP bag was also replayed through adapter, actual GPU detector and RViz with reflectivity/255. [Visual integration record](FRESH_OUSTER_VISUAL_TEST.md). The later 1,120-inference channel study uses unchanged production inference/NMS directly, with independently annotated scans, but bypasses this ROS adapter. [Accuracy and stability decision](OUSTER_CHANNEL_DECISION.md). These complementary checks do not establish a newly tested live-sensor A/B deployment.

## Clipped-reflectivity visual preview — 21 November 2026

The optional cap implements `min(reflectivity / 100, 1)` when divisor100 and cap1
are explicitly selected. Source geometry and headers remain unchanged; the live
point-selection policy is unchanged. This is a local experiment, not a verified
NVIDIA recommendation or accepted accuracy configuration. See
[NVIDIA model research](NVIDIA_EXACT_MODEL_CONFIDENCE_RESEARCH.md) and
[publisher settings](NVIDIA_POINTPILLARS_SETTINGS_RESEARCH.md).

```bash
sudo env PP_IMAGE=pp-infer:reflectivity-preview-overlay \
  PP_OUSTER_INTENSITY_DIVISOR=100 PP_OUSTER_INTENSITY_CLIP_MAX=1 \
  PP_CONFIDENCE_THRESHOLD=0.3 bash tools/start_ouster.sh bag
```

This requires an image built with the new adapter parameter. Ordinary baseline
defaults remain reflectivity/255, clipping disabled and launcher score gate0.4.
