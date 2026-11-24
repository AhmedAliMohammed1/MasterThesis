# Docker deployment and engine storage

Reviewed 8 November 2026. Use [startup and replay](../docs/STARTUP_AND_REPLAY.md) for the shortest Ouster workflow. This page explains image construction, persistence and overrides.

## Choose the command

| Command, from the project root | What it starts |
| --- | --- |
| `sudo bash tools/deploy.sh` | Check GPU/Docker, reuse or build the local image, then detector only |
| `sudo env PP_BUILD_ONLY=1 bash tools/deploy.sh` | Prepare/reuse the image and exit; optional build-only mode |
| `sudo bash tools/start.sh` | Detector from an existing image |
| `sudo bash tools/start_ouster.sh` | Live Ouster adapter and detector; driver/router already running |
| `sudo bash tools/start_ouster.sh bag` | Adapter and detector configured for primary raw01/ouster1 replay |
| `sudo bash tools/start_ouster_bag.sh` | Bag player only; recording must already exist |

All foreground launchers stop their own container on one Ctrl+C. Allow up to eight seconds for cleanup. Images and the engine volume persist. Existing container names are preserved; inspect and stop the intended old instance or choose another `PP_CONTAINER_NAME`.

The host must provide a working NVIDIA driver, Docker and NVIDIA Container Toolkit. The scripts check access; they do not install drivers. Host ROS is needed only for native development or desktop RViz.

## What an image build does

The Dockerfile installs ROS Jazzy, CUDA 12.9 components and matching TensorRT 10.16.1.11 runtime/plugin/parser/tool/header packages. It downloads NVIDIA NGC PointPillarNet `deployable_v1.1` ONNX, verifies SHA-256 `2dcabddc3a365e9608a112d7bbbb7db769a6dddeeaa59aa03611a83113326da1`, then builds/tests the C++ package with colcon.

`deploy.sh` uses **local source** by default, including uncommitted runtime edits. Its runtime-input hash excludes documentation, bags, models and SDK artifacts. A matching saved image skips `docker build`; source/configuration changes run a cached build. Dependency and model stages are separate from source compilation. First builds, missing/pruned caches or changed dependency recipes can require downloads and installation.

| Switch | Effect |
| --- | --- |
| `PP_BUILD_ONLY=1` | Exit after image preparation |
| `PP_FORCE_BUILD=1` | Invoke a build even when the input hash matches; keep layer cache |
| `PP_PULL_BASE=1` | Refresh base images explicitly |
| `PP_SOURCE_MODE=remote` | Use published Git source |
| `PP_GIT_REF`, `PP_GIT_REPO` | Select remote source; imply remote mode unless explicitly overridden |

Direct Dockerfile builds retain their **remote-source default**, including builds with only the Dockerfile as context:

```bash
sudo docker build -t pp-infer:jazzy-trt10 - < Dockerfile
```

A local edit is included automatically by `deploy.sh`; a remote build only includes changes published at its selected reference. To pin remote source:

```bash
sudo env PP_BUILD_ONLY=1 PP_GIT_REF='YOUR_FULL_COMMIT_SHA' bash tools/deploy.sh
```

Extra deployment arguments are passed to `docker build`. Use BuildKit secrets for private access; never embed credentials in URLs or arguments. CUDA/TensorRT are pinned, but Ubuntu tags and ROS apt versions may evolve. Retain the built image and source/runtime identity for a repeated experiment. A documentation-only commit can legitimately reuse an image recording an earlier Git revision with the same runtime hash.

## Model and engine lifecycle

| Stage | Artifact and location inside the container |
| --- | --- |
| Image build | Network/weights at `/opt/models/pointpillars.onnx` |
| First target-GPU startup | FP32 engine built with `trtexec` into `/var/lib/pp_infer/<key>.engine` |
| Later matching startup | Existing nonempty engine reused; ONNX still hashed |
| Node initialization | Engine deserialized once; context and GPU buffers reused |

The default `pp-engines` Docker volume makes engine storage persistent across disposable containers. The cache key includes model hash, selected GPU identity, driver/CUDA information and build settings. Generation is serialized with a lock, uses a temporary file, and promotes it only after success. Ctrl+C during generation removes the partial file. A nonempty corrupted engine is not automatically detected and rebuilt by the shell cache check.

The builder uses FP32, batch one, TF32 disabled and 512 MiB workspace. Workspace is a builder pool limit, not total GPU memory. A changed GPU or recipe can require another engine. Copying an engine to another machine is not a portable deployment strategy; transfer the image and let its startup build a matching engine.

The entrypoint loads ROS and executes the installed C++ detector directly. It passes the cached `engine_path`, topic remappings and optional confidence override. Native `ros2 run` invokes the same binary but does not prepare an engine. Legacy `model_path` and `data_type` do not load ONNX or rebuild an existing engine.

## Runtime settings

| Setting | Detector launcher default |
| --- | --- |
| `PP_IMAGE` | `pp-infer:jazzy-trt10` |
| `PP_CONTAINER_NAME` | `pointpillars` |
| `PP_ENGINE_VOLUME` | `pp-engines` |
| `ROS_DOMAIN_ID` | `0` |
| `RMW_IMPLEMENTATION` | `rmw_fastrtps_cpp` |
| `POINT_CLOUD_TOPIC` | `/point_cloud` |
| `DETECTIONS_TOPIC` | `/bbox` |
| `PP_CONFIDENCE_THRESHOLD` | `0.4` |
| `PP_GPU_INDEX` | `0` within visible CUDA devices |
| `PP_WORKSPACE_MIB` | `512` |

Repeat custom settings at each launch; the wrappers do not save them:

```bash
sudo env POINT_CLOUD_TOPIC=/lidar/xyzi ROS_DOMAIN_ID=7 \
  PP_CONFIDENCE_THRESHOLD=0.7 bash tools/start.sh
```

Ouster launchers add a profile and channel settings; see [the adapter guide](../docs/LIVE_OUSTER_ADAPTER.md). The live profile defaults to Zenoh/domain 0/raw `/ouster1/points`; bag mode defaults to Fast DDS/domain 99/raw `/sensing/lidar/points`.

A direct launch is possible:

```bash
sudo docker run --rm --init --name pointpillars \
  --gpus all --network host --ipc host \
  -v pp-engines:/var/lib/pp_infer pp-infer:jazzy-trt10
```

Without a confidence environment override, direct entrypoint startup uses the YAML default **0.5**, while wrappers supply **0.4**. Prefer the wrappers for the tested single-interrupt shutdown behavior.

## Check identity and output

```bash
sudo docker exec pointpillars cat /opt/pp_infer/source-revision.txt
sudo docker logs --tail 80 pointpillars
sudo docker exec pointpillars /entrypoint.sh ros2 node info /pointpillars
sudo env PP_MONITOR_BACKEND=docker bash tools/monitor_detections.sh once
```

Input must be little-endian scalar FLOAT32 XYZI within the engine's 204,800-point capacity and the default 64 MiB cloud limit. The detector requests reliable depth 700. `/bbox` carries accepted boxes; derived `/bbox/stats` and `/bbox/count` carry aggregate diagnostics and RViz text. A headless detector does not open RViz or create real sensor data.

The current recipe targets Linux amd64. The main measured GPU is the RTX 4060 Laptop; a separate live-host troubleshooting record describes an RTX A4500 Embedded. ARM/Jetson and Windows/WSL2 need separate work. Operational latency, memory safety and 3D accuracy remain unaccepted. [Current evidence](../docs/CURRENT_STATUS_AND_RESULTS.md) and [channel decision](../docs/OUSTER_CHANNEL_DECISION.md) explain the limits.
