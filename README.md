# PointPillars inference for ROS 2 Jazzy

This project receives LiDAR point clouds and publishes 3D detection messages using a pretrained PointPillars ONNX model and TensorRT 10.16.1.11. The current deployment uses Ubuntu 24.04 and Docker; the image builds the ROS package with colcon.

The [A-to-Z LaTeX guide](docs/PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex) explains the completed changes and gives plain-language steps and commands for driver installation, Docker/NVIDIA Container Toolkit setup, model and SDK preparation, build/run, inspection, bag playback, synthetic verification, transfer to another computer, native colcon development, troubleshooting, and interrupted-work recovery. Open the `.tex` file in the Codex editor for its PDF preview when the compiler is available. Current PDF compilation is unverified: the built-in compiler could not download its TeX bundle; the source and command checks are saved.

## Start on this machine

Run from `/home/ae/Desktop/MasterThesis`, where the model and extracted SDK are already prepared:

```bash
sudo docker build -t pp-infer:jazzy-trt10 .
sudo docker run --rm --init --name pointpillars \
  --gpus all --network host --ipc host \
  -v pp-engines:/var/lib/pp_infer \
  pp-infer:jazzy-trt10
```

The build runs four colcon test modes. First startup builds an FP32 batch-one engine on the selected GPU. Later starts reuse a matching engine in the volume. GPU access is required for running, not building. Stop with Ctrl+C. Stop an earlier instance on the same topics before launching another.

| Item | Name |
| --- | --- |
| ROS package / executable | `pp_infer` / `pp_infer` |
| Container node | `/pointpillars` |
| Input | `/point_cloud` — `sensor_msgs/msg/PointCloud2` |
| Output | `/bbox` — `vision_msgs/msg/Detection3DArray` |

The native command is `ros2 run pp_infer pp_infer` with an engine and parameter file; there is no `ros2 node run` command. Without a name override, native startup retains `/minimal_publisher`. Use the explicit startup procedure in the guide; the historical launch file has old absolute paths and unverified model settings.

## Prepare another computer

Use Ubuntu 24.04 on Linux x86-64 with a supported NVIDIA GPU, enough GPU memory, a compatible driver, Docker, and NVIDIA Container Toolkit configured for Docker. The guide starts from installing the driver and provides each command. Host ROS, TensorRT, and CUDA development packages are unnecessary when using the image.

TensorRT 10.x lists compute capability 7.5 or newer as its hardware floor. Only the RTX 4060 Laptop has been physically tested here; other targets need validation. ARM64/Jetson requires a separate image, and this Linux host-network recipe has not been validated on Windows/WSL2. See [NVIDIA's support matrix](https://docs.nvidia.com/deeplearning/tensorrt/10.x.x/getting-started/support-matrix.html).

For a source build, obtain this updated working tree and prepare these ignored build inputs using Steps 5–6 of the guide:

- `docker/assets/pointpillars.onnx` — the supplied deployable ONNX, verified by hash.
- `.recovery/sdk/tensorrt-10.16.1/usr` — extracted TensorRT headers, shared libraries, and `trtexec`.

A Dockerfile or source-only copy does not include those ignored files. The current changes have not been published as a new Git commit or registry image; cloning the original upstream repository will not reproduce them. Plan for roughly 40 GB free during a source build; this is an allowance, not a measured minimum.

Alternatively, transfer the built image with `docker save` and `docker load`, then run it on the receiving computer. The guide gives both commands. The image contains the model and libraries and builds its own target engine; do not assume engines transfer between different GPUs. Keep SDK/model licensing terms with redistributed artifacts.

## Check the running application

Use another terminal:

```bash
sudo docker ps
sudo docker image ls pp-infer
sudo docker logs --tail 80 pointpillars
sudo docker exec pointpillars /entrypoint.sh ros2 node list
sudo docker exec pointpillars /entrypoint.sh ros2 node info /pointpillars
sudo docker exec pointpillars /entrypoint.sh ros2 topic list -t
sudo docker exec pointpillars /entrypoint.sh ros2 topic echo /bbox --once
```

The entrypoint loads ROS before running these utilities. The node needs a LiDAR publisher, compatible ROS bag, or the synthetic check in Step 10 of the guide. It does not produce camera images or provide a GUI viewer.

Input fields must be scalar little-endian FLOAT32 `x`, `y`, `z`, and `intensity`. Organized clouds with valid row padding are supported. The tested engine supports 204800 points; the default byte limit is 64 MiB. The current subscription requests **reliable** delivery, so best-effort-only publishers may not match it.

Add `-e POINT_CLOUD_TOPIC=/lidar/points`, `-e DETECTIONS_TOPIC=/detections`, or `-e ROS_DOMAIN_ID=7` before the image name to match your data source. Use `-e PP_GPU_INDEX=1` to select a GPU within the container-visible CUDA set. `-e PP_WORKSPACE_MIB=256` reduces builder workspace, not total GPU memory. See [Docker details](docker/README.md) and the guide for configuration mounts and playback QoS overrides.

## Current implementation and limits

The CPU geometry core and local ROS adapters are verified. Runtime migration uses TensorRT named tensors, validated input/output contracts, owned CUDA resources, and reusable buffers. Docker build, engine creation, synthetic ROS/GPU message flow, restart cache reuse, and invalid GPU selection checks passed on the available GPU.

Training class order, intensity normalization, and coordinate semantics are unresolved. Defaults in `docker/node.yaml` are provisional `class_0`/`class_1`/`class_2` and intensity scale 1.0. Synthetic checks do not establish real-data accuracy. CUDA memory instrumentation was inconclusive; further runtime failure checks, the bounded worker, configurable sensor QoS, timing metrics, benchmark targets, and CI/operational acceptance remain unfinished.

See [architecture](IMPLEMENTATION_ARCHITECTURE.md), [progress](recovery/PROGRESS.md), [task ledger](recovery/tasks.json), and [native SDK/build record](docs/local_runtime.md). The [old Foxy/TensorRT 8 README](docs/LEGACY_FOXY_README.md) is historical and is not the current installation procedure.

## Continue after an interruption

```bash
python3 tools/recovery.py status
python3 tools/recovery.py checkpoint \
  --task W09 --state in-progress \
  --next 'Continue the interrupted substep and record actual verification.' \
  --evidence 'Current work remains unfinished.'
```

Read [RESUME.md](recovery/RESUME.md) before continuing. Checkpoints preserve eligible source and detect drift; they do not reset files, restore automatically, run tests, or extend model credits. SDKs, engines, models, bags, and logs require independent backups.

## CPU-only development checks

```bash
colcon build --packages-select pp_infer \
  --build-base .recovery/colcon-doc/core/build \
  --install-base .recovery/colcon-doc/core/install \
  --cmake-args -DPP_BUILD_RUNTIME=OFF -DPP_BUILD_ROS_ADAPTER=OFF \
  -DCMAKE_BUILD_TYPE=Debug
colcon test --packages-select pp_infer \
  --build-base .recovery/colcon-doc/core/build \
  --install-base .recovery/colcon-doc/core/install \
  --ctest-args --output-on-failure
colcon test-result --test-result-base .recovery/colcon-doc/core/build --verbose
```

All current build instructions use colcon. The CPU-only configuration has no install target, so its skipped-install warning is expected. The guide also includes ROS adapter and sanitizer configurations in separate directories, native runtime commands, and the GPU smoke check. CMake remains a build dependency behind colcon; `--cmake-args` passes package configuration options.
