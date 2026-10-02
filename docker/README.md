# Automatic Docker build and deployment

On a Linux x86-64 host with a supported NVIDIA GPU, working driver, Docker and NVIDIA Container Toolkit, run from the project folder:

```bash
sudo bash tools/deploy.sh
```

This one command builds the image and starts the node in the foreground. Ctrl+C stops it. The wrapper will not replace an existing container with the same name; stop/remove the intended old instance first or select another `PP_CONTAINER_NAME`.

`docker build` creates an image. It cannot keep a ROS node running after its build container exits. The wrapper runs `docker build` followed by `docker run`; target-GPU engine creation happens at container startup. Host drivers and Docker GPU integration must already work.

The Dockerfile automatically:

1. Clones the latest published GitHub `main` source using BuildKit's Git `ADD`.
2. Installs ROS 2 Jazzy, CUDA 12.9 components, C++/colcon tools and PCL dependencies.
3. Downloads and installs the exact TensorRT 10.16.1.11 CUDA 12.9 runtime/plugin/parser/tool/header packages from NVIDIA's signed apt repository. All TensorRT dependencies are pinned to the same CUDA variant; large static development packages are omitted.
4. Downloads NVIDIA NGC PointPillarNet `deployable_v1.1` ONNX and verifies SHA-256 `2dcabddc3a365e9608a112d7bbbb7db769a6dddeeaa59aa03611a83113326da1`.
5. Builds and tests `pp_infer` with colcon, records the Git commit in `/opt/pp_infer/source-revision.txt`, and packages a runtime image.

No local `.recovery/sdk`, downloaded DEB, ONNX, engine, or build tree is sent to Docker. `.dockerignore` allows only the Dockerfile and ignore file. You can build from the Dockerfile alone:

```bash
sudo docker build -t pp-infer:jazzy-trt10 - < Dockerfile
```

To launch the built image directly:

```bash
sudo docker run --rm --init --name pointpillars \
  --gpus all --network host --ipc host \
  -v pp-engines:/var/lib/pp_infer pp-infer:jazzy-trt10
```

Push source edits before rebuilding: local uncommitted or unpushed runtime changes are not included. BuildKit resolves the Git reference and caches by source identity, so unchanged dependencies need not be downloaded again. To pin a release, pass `--build-arg GIT_REF=<full-commit-sha>` to the build, or set `PP_GIT_REF` for the wrapper.

```bash
sudo env PP_GIT_REF='YOUR_FULL_COMMIT_SHA' bash tools/deploy.sh
```

For another repository, set `PP_GIT_REPO` in the wrapper or `GIT_REPO` as a build argument. A private repository needs BuildKit Git authentication secrets; do not embed access tokens in URLs, Dockerfile arguments or source. Network access is required for a fresh build. CUDA/SDK versions are pinned; Ubuntu tags and ROS apt versions can still change. Pin the Git commit and retain the built image for repeatable deployments.

At startup, the selected CUDA GPU is checked and an FP32 batch-one engine is generated. Engines are cached in `pp-engines`, keyed by model hash, GPU UUID/capability, driver, CUDA APIs and build recipe. Builds for the same key are serialized; temporary files are promoted only after successful engine generation. Transfer the image to another supported computer and let it generate its own engine.

Node `/pointpillars` receives `/point_cloud` (`sensor_msgs/msg/PointCloud2`) and publishes `/bbox` (`vision_msgs/msg/Detection3DArray`). Start a sensor or bag publisher separately; the container does not generate real data. Input needs little-endian scalar FLOAT32 XYZI and a compatible reliable publisher.

Wrapper settings: `PP_IMAGE`, `PP_CONTAINER_NAME`, `PP_ENGINE_VOLUME`, `PP_GIT_REPO`, `PP_GIT_REF`, `PP_GPU_INDEX`, `PP_WORKSPACE_MIB`, `ROS_DOMAIN_ID`, `POINT_CLOUD_TOPIC`, `DETECTIONS_TOPIC`. Extra wrapper arguments are forwarded to `docker build`, including build arguments and secrets. For example:

```bash
sudo env POINT_CLOUD_TOPIC=/lidar/points ROS_DOMAIN_ID=7 \
  PP_GPU_INDEX=0 PP_WORKSPACE_MIB=256 bash tools/deploy.sh
```

GPU indexes refer to the visible CUDA set. Workspace limits do not cap total GPU memory. The image is Linux amd64 and follows [TensorRT 10.x hardware support](https://docs.nvidia.com/deeplearning/tensorrt/10.x.x/getting-started/support-matrix.html), with capability 7.5 as a floor. ARM/Jetson requires a separate image. Only the available RTX 4060 has been physically tested.

Class order, intensity scaling and coordinate semantics still need reference validation. Defaults remain generic labels and scale 1.0. Synthetic tests do not establish real-data accuracy. Bounded-worker integration, configurable QoS, CUDA memory instrumentation and operational acceptance remain unfinished.

See the [A-to-Z LaTeX guide](../docs/PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex), [README](../README.md) and [progress record](../recovery/PROGRESS.md) for setup, verification and limits.

## Optional desktop visualization

The inference image stays headless. Keep the node and a LiDAR/bag publisher running, then use `bash tools/visualize.sh` from this checkout on a ROS Jazzy desktop. The saved view displays `/point_cloud` and `/bbox` with the official vision_msgs plugin; no inference rebuild is needed. Host RViz must be installed. See the [viewer setup and limits](../README.md#visualize-points-and-boxes-in-rviz) for packages, fixed frame, domain and transport settings. GPU inference can stay on a separate compatible machine if ROS network discovery is configured.

## Sample bag and camera clip helper

After building the inference image, `bash tools/rosbag_demo.sh` downloads/verifies the tested KITTI bag, prepares a camera reference MP4 from its original drive and loops reliable LiDAR playback. `prepare` downloads assets only; `stop` stops only helper-owned playback. A separate `pp-infer:demo-tools` image supplies Python/FFmpeg without host installation. Matching active playback is reused; different existing containers are preserved. See the [sample instructions](../README.md#download-and-play-the-sample-bag-with-matching-camera-video) for storage, recovery, settings and the independent video's timing/accuracy limits.
