# PointPillars inference for ROS 2 Jazzy

This project receives LiDAR point clouds and publishes 3D detection messages using a pretrained PointPillars ONNX model and TensorRT 10.16.1.11. The current deployment uses Ubuntu 24.04 and Docker; the image builds the ROS package with colcon.

The [A-to-Z LaTeX guide](docs/PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex) explains the completed changes and gives plain-language steps and commands for driver installation, Docker/NVIDIA Container Toolkit setup, automatic Git/model/SDK downloads, build/run, inspection, bag playback, synthetic verification, transfer to another computer, native colcon development, troubleshooting, and interrupted-work recovery. Open the `.tex` file in the Codex editor for its PDF preview when the compiler is available. PDF compilation is unverified: the built-in compiler could not initialize; its latest attempt could not download the uncached TeX bundle; earlier attempts after the folder move reported a closed sandbox connection. The source and command checks are saved.

## Build and run with one command

With a working host NVIDIA driver, Docker and NVIDIA Container Toolkit, run from the project folder:

```bash
sudo bash tools/deploy.sh
```

This builds the image and starts `/pointpillars` in the foreground. It automatically clones the latest published GitHub `main`, installs ROS Jazzy/CUDA/TensorRT 10.16.1.11 dependencies and headers, downloads the pinned NGC pretrained ONNX, verifies its checksum, and builds/tests with colcon. First startup generates an FP32 batch-one engine on the selected GPU; later matching launches reuse it in `pp-engines`. No local SDK, installer, model or engine preparation is needed. Stop with Ctrl+C.

`docker build` alone produces an image; it cannot leave a persistent node running after the build. The wrapper performs both build and run. You can also build from just the Dockerfile:

```bash
sudo docker build -t pp-infer:jazzy-trt10 - < Dockerfile
```

Then launch with the direct `docker run` command in [Docker details](docker/README.md). GPU access is required at startup, not during the image build. The wrapper refuses to replace an existing container with the same name; stop/remove the intended old instance first, or choose `PP_CONTAINER_NAME`.

**Push source edits before rebuilding.** GitHub source is used, so uncommitted or unpushed runtime changes are not included. Set `PP_GIT_REF` to a full commit SHA for a fixed release. The image records its source commit in `/opt/pp_infer/source-revision.txt`.

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

After these deployment edits have been committed and pushed, obtain the project on another computer:

```bash
git clone https://github.com/AhmedAliMohammed1/MasterThesis.git "$HOME/pointpillars"
cd "$HOME/pointpillars"
sudo bash tools/deploy.sh
```

The build fetches its own source and dependencies. Plan for roughly 40 GB free for a fresh build, an allowance rather than a measured minimum. Docker images/cache occupy Docker's storage filesystem even if the project is on another drive. The original checkout is now `/media/ae/New Volume/MasterThesis`; quote paths containing spaces. Large models, SDKs, engines and archives remain excluded by `.gitignore`. No registry image has been published.

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

The entrypoint loads ROS before running these utilities. The node needs a LiDAR publisher, compatible ROS bag, or the synthetic check in Step 10 of the guide. It does not produce camera images. The optional RViz viewer below displays its point clouds and boxes on the host desktop.

Input fields must be scalar little-endian FLOAT32 `x`, `y`, `z`, and `intensity`. Organized clouds with valid row padding are supported. The tested engine supports 204800 points; the default byte limit is 64 MiB. The current subscription requests **reliable** delivery, so best-effort-only publishers may not match it.

For direct `docker run`, add `-e POINT_CLOUD_TOPIC=/lidar/points`, `-e DETECTIONS_TOPIC=/detections`, or `-e ROS_DOMAIN_ID=7` before the image name to match your data source. Use `-e PP_GPU_INDEX=1` to select a GPU within the container-visible CUDA set. `-e PP_WORKSPACE_MIB=256` reduces builder workspace, not total GPU memory. For the single-command wrapper, use environment settings:

```bash
sudo env POINT_CLOUD_TOPIC=/lidar/points ROS_DOMAIN_ID=7 \
  PP_GPU_INDEX=0 bash tools/deploy.sh
```

See [Docker details](docker/README.md) and the guide for configuration mounts and playback QoS overrides.

## Download and play the sample bag, with matching camera video

Start inference with `tools/deploy.sh`, then in another terminal run:

```bash
bash tools/rosbag_demo.sh
```

This prepares the same KITTI sequence04 bag used for verification, downloads its original drive's left-color camera frames, creates a camera MP4, and loops the LiDAR topic into `/point_cloud` with reliable QoS at half speed. It builds a small Ubuntu preparation image containing Python and FFmpeg when needed; no host ROS, FFmpeg or Python installation is required for this helper. Docker is required, and the inference image must already exist for playback. Run without sudo; the helper requests Docker access through sudo only if needed and preserves your ownership of generated files.

Downloads use a pinned Hugging Face revision/checksum for the bag and a pinned object ETag for the original KITTI archive. Camera frames are fetched using ZIP byte ranges, avoiding a complete raw-data download. Completed frames are reused, partial bag downloads resume, and video promotion occurs after encoding/probing succeeds. Reruns verify and reuse prepared assets. The default folder is `../rosbags/kitti04` relative to the checkout; a generated `.gitignore` excludes its assets. Allow roughly3 GB there, plus Docker storage for the preparation image.

The camera video is `kitti04_left_camera.mp4` in that folder. Open it with your video player. It shows the underlying scene from drive `2011_09_30_drive_0016`; it is **not annotated ground truth** and does not automatically synchronize with RViz or bag playback. The camera has285 frames; the bag has283 LiDAR frames. Original camera timestamps are saved, and its first frame precedes the first LiDAR scan by about0.210 seconds. The clip plays at recorded speed; the default bag playback is half speed. This helper does not publish camera images or overlay boxes on the video.

Other modes and settings:

```bash
bash tools/rosbag_demo.sh prepare  # Assets/video only; no playback or inference image needed.
bash tools/rosbag_demo.sh stop     # Stops only a player created by this helper.
PP_DEMO_DIR="$HOME/rosbags/kitti04" PP_BAG_RATE=1 bash tools/rosbag_demo.sh
```

Match `ROS_DOMAIN_ID` and `POINT_CLOUD_TOPIC` to inference. A matching running player is reused; a different or stopped container with the same name is preserved and reported as a conflict. The helper's stop mode refuses to stop manually started/unlabeled containers; inspect and stop those explicitly. See `bash tools/rosbag_demo.sh --help` for image/container settings. Open the separate RViz viewer below while playback runs.

Sources: [bag converter and sequence mapping](https://github.com/Jakubach/kitti_to_ros), [ready ROS bags](https://huggingface.co/datasets/kubchud/kitti_to_ros), [KITTI sensor/data description](https://www.cvlibs.net/datasets/kitti/raw_data.php). Preserve dataset attribution and applicable licensing terms with copied data.

## Visualize points and boxes in RViz

Keep inference and bag playback (or your LiDAR driver) running. On an Ubuntu desktop with **host ROS Jazzy and RViz** installed, run from this folder:

```bash
bash tools/visualize.sh
```

The saved [RViz view](rviz/pointpillars.rviz) shows `/point_cloud` and `/bbox` together, using the official [vision_msgs RViz plugin](https://github.com/ros-perception/vision_msgs/blob/ros2/vision_msgs_rviz_plugins/README.md). It uses reliable QoS and fixed frame `velodyne` for the tested KITTI bag. For another sensor frame/domain:

```bash
ROS_DOMAIN_ID=7 bash tools/visualize.sh -f your_lidar_frame
```

Run the viewer as your desktop user, without sudo. A Docker-only inference host does not need ROS or a display; this optional viewer does. Follow the guide's native ROS installation section if needed, then install:

```bash
sudo apt install ros-jazzy-rviz2 ros-jazzy-vision-msgs-rviz-plugins
```

If RViz is already installed but its vision display plugin is missing, the launcher downloads the official package from the host's configured ROS apt index and extracts it under ignored `.recovery/rviz`; it does not register a system package. Missing dependencies require the apt installation above. The launcher defaults Fast DDS to UDPv4 to avoid shared-memory ownership conflicts between root containers and desktop users; an explicit `FASTDDS_BUILTIN_TRANSPORTS` setting overrides this. Network/firewall/domain restrictions can still affect discovery.

Use the mouse wheel to zoom and drag to rotate. Expand **Detections** to check its status or enable **Show Score**. Box colors identify numeric model IDs: orange `0`, blue `1`, yellow `2`; their semantic class names remain unverified. Intensity colors apply to points. All published boxes remain visible; this viewer adds no confidence filter. A sensor-frame-only bag can show a global TF warning because it supplies no transform tree. With both displays receiving data in the same `velodyne` frame, points and boxes can still render; do not substitute a different fixed frame without a valid transform.

Real-bag integration passed 25 matched frames inside Docker and another 25 through the host viewer transport. The live RViz window rendered points and boxes. These checks establish message compatibility and visualization, **not detection accuracy**; labels, intensity normalization and box-coordinate conventions still need a known reference. The inference container remains headless and publishes `Detection3DArray` directly; no marker conversion is needed.

## Current implementation and limits

The CPU geometry core and local ROS adapters are verified. Runtime migration uses TensorRT named tensors, validated input/output contracts, owned CUDA resources, and reusable buffers. Docker build, engine creation, synthetic ROS/GPU message flow, restart cache reuse, and invalid GPU selection checks passed on the available GPU. Real KITTI bag message checks and live RViz rendering also passed.

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
