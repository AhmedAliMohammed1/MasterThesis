# Troubleshoot an Ouster pipeline

Reviewed 8 November 2026. Start with [the current startup guide](STARTUP_AND_REPLAY.md). Work from the source toward the output: **driver → raw cloud → adapter → XYZI → detector → RViz**. A discovered node is not proof of a processed cloud, and a visible box is not proof of accuracy.

## First identify the profile

| Setup | Raw topic | Domain | Middleware |
| --- | --- | ---: | --- |
| Recorded live-host default | `/ouster1/points` | 0 | Zenoh (`rmw_zenoh_cpp`) |
| Downloaded MOSEP bag profile | `/sensing/lidar/points` | 99 | Fast DDS (`rmw_fastrtps_cpp`) |

For the bag, pair `sudo bash tools/start_ouster.sh bag` with `sudo bash tools/start_ouster_bag.sh`. The earlier failure paired a live-profile detector with a bag-profile player and had no reachable Zenoh router. Both names and transport settings differed. Current scripts share explicit bag defaults; custom overrides must match in both terminals.

## No recent clouds or no discovered publishers

In a ROS terminal using the same domain/middleware as the source:

```bash
ros2 node list --no-daemon --spin-time 5
ros2 topic list -t
ros2 topic info /ouster1/points --verbose
```

Use `/sensing/lidar/points` for the bag. Inside the pipeline container:

```bash
sudo docker exec pointpillars /entrypoint.sh ros2 topic list -t
sudo docker exec pointpillars /entrypoint.sh ros2 topic echo /ouster_adapter/stats --once
```

Check that the driver/player is actually publishing, that a Zenoh router is reachable when using Zenoh, and that topic/domain/middleware match. `ros2 daemon stop` only stops the CLI discovery daemon, not application nodes. Restart CLI discovery after changing middleware/domain if cached output is misleading.

`sudo` may discard shell exports; pass settings with `sudo env RMW_IMPLEMENTATION=... ROS_DOMAIN_ID=...`. Host networking does not make different middleware implementations communicate automatically. Custom Zenoh routing settings are not automatically forwarded by these wrappers.

## Clouds arrive but the adapter rejects them

Read the diagnostic error and logged schema. The adapter selects a literal `reflectivity` or `signal` field and supports UINT8, UINT16 or FLOAT32 values. XYZ must be scalar FLOAT32. It validates byte layout, row lengths and limits before conversion.

A common case is the bag's signal channel being named **`intensity`**. The current production selector has no alias for that field. Use reflectivity for the unchanged MOSEP bag. The research A/B runner handles the verified alias separately; do not infer equivalent live adapter support.

The default maximum is 204,800 points and 64 MiB. The adapter does not silently subsample oversized scans. A selected channel with negative/nonfinite values or an invalid divisor is also rejected. [Full conversion contract](LIVE_OUSTER_ADAPTER.md#what-the-converter-accepts-and-preserves).

## The detector reports invalid XYZI

Raw Ouster clouds may have `signal` and `reflectivity` but no scalar FLOAT32 `intensity`. Feed them through the Ouster adapter. The generic detector input adapter does not reinterpret these fields automatically.

For already compatible XYZI, a direct detector-only launcher is appropriate. Under DDS its reliable subscription cannot generally match a best-effort-only publisher. The Ouster adapter receives sensor-data best effort and republishes reliable XYZI. Check actual QoS with `ros2 topic info --verbose`.

Use the aggregate counters to separate the stages:

```bash
sudo env PP_MONITOR_BACKEND=docker bash tools/monitor_detections.sh once
sudo docker logs --tail 100 pointpillars
```

A failed frame has an unavailable detection count; it is not a successful zero-object scan. Counters can be retained after input stops, so check timestamps.

## The engine does not build or CUDA startup fails

```bash
nvidia-smi
sudo docker run --rm --gpus all --entrypoint nvidia-smi pp-infer:jazzy-trt10
```

Both host and container GPU access must work. The CUDA version shown by `nvidia-smi` is driver capability, not the image's installed toolkit version. The current image uses CUDA 12.9 and TensorRT 10.16.1.11.

Builder workspace defaults to 512 MiB. It is not total GPU memory. The recorded live host could not build with 256 MiB because a plugin needed 270,532,608 bytes of scratch space, and a 1024 MiB attempt also encountered allocation failure. The 512 MiB build succeeded there. Other workloads/GPUs need their own verification; successful engine creation alone does not prove successful inference.

If system logs explicitly require a reboot after a fatal GPU fault, preserve work and follow the recovery action. Do not reset a display GPU or kill unidentified processes as a generic fix. `nvidia-smi` can still work while CUDA initialization fails after a driver fault.

## RViz is empty or shows old results

Match the viewer's domain/middleware and set Fixed Frame to the incoming cloud's `header.frame_id`. The MOSEP bag uses `lidar/os_lidar`; the standard KITTI demo uses `velodyne`. Ensure the point/detection displays subscribe to the intended topics and have compatible QoS.

The count display uses MarkerArray, Reliable / Transient Local. It shows the last processed status, which may be old. The launcher opens a new RViz window; use **File → Open Config** to change an existing one. [Monitoring and count meanings](CONFIDENCE_FILTER_AND_MONITORING.md).

## Playback warns about MCAP metadata

The original MOSEP files can produce `Metadata record with name 'rosbag2' did not contain key 'serialized_metadata'`. In the recorded actual replay, this warning did not prevent cloud publication or processing. Check actual reception counters rather than rewriting the original bag or assuming that the warning explains missing data.

## Boxes appear but look wrong

Keep reflectivity/255 as the experimental baseline, but treat object accuracy as unresolved. On the annotated diagnostic subset, reflectivity found four of 60 vehicles from above per run and signal none; both failed all qualifying 3D matches. The matched reflectivity boxes were 0.60–1.14 m too high. Raising the confidence gate cannot correct that geometry. [Evidence and proposed next work](OUSTER_CHANNEL_DECISION.md).

## Physical-host repair history — 28 October 2026

This section retains the useful diagnosis from user-supplied logs on host `alfonso-h017`, Ubuntu 24.04.4 with RTX A4500 Embedded 8 GiB. It is not a claim that this host has now passed live inference or the later accuracy study, whose measured GPU was an RTX 4060 Laptop.

The original host had NVIDIA modules for a different kernel. A dependency simulation and repair using the matching branch-595 open modules/driver, followed by reboot, restored access. Mixed Ubuntu/CUDA package sources had proposed conflicting branch-580 packages. These are host-specific facts; inspect the current GPU, running kernel, available packages and simulated transaction before repairing another machine. The project does not install host drivers.

The Ouster drivers also reported an undefined Fast CDR serialization symbol. Updating the compatible group of `ouster-ros`, `ouster-sensor-msgs`, `fastcdr`, `fastrtps`, Fast RTPS typesupport and RMW packages restored launch, according to the supplied logs. Updating an arbitrary single library is not a reproducible general remedy; stop affected ROS nodes and inspect package compatibility first.

Once middleware matched, the observed 128×1024 cloud had FLOAT32 XYZ, UINT16 signal at offset 28 and UINT8 reflectivity at offset 32, with no intensity field. The detector consequently rejected 565 observed clouds. That was an input-schema failure, not evidence of a TensorRT failure. The subsequently implemented separate Ouster adapter addresses that conversion contract. Successful inference on that original physical live host, sensor fusion and operational acceptance remain unverified by those logs.
