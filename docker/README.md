# Two-command Docker workflow

For a fresh computer, use the [A-to-Z LaTeX guide](../docs/PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex), including driver/toolkit setup, exact SDK/model preparation, and image transfer.

Run these commands from `/home/ae/Desktop/MasterThesis`:

```bash
docker build -t pp-infer:jazzy-trt10 .
docker run --rm --init --name pointpillars --gpus all --network host --ipc host -v pp-engines:/var/lib/pp_infer pp-infer:jazzy-trt10
```

The runtime image includes Ubuntu 24.04, CUDA 12.9.1 shared libraries, ROS 2 Jazzy, TensorRT 10.16.1.11, all three PointPillars plugins, the pretrained ONNX and the colcon-built node. Compilers and CUDA development files stay in the build stage. First startup creates an FP32 batch-one engine on the container's GPU. Later launches reuse a cache keyed by model hash, CUDA-selected GPU UUID/capability, NVIDIA driver version, CUDA driver/runtime API versions and SDK/build recipe. Failed engine builds leave no accepted final engine. No GPU is needed for `docker build`; GPU is required for `docker run`.

Node: `/pointpillars`. Input: `/point_cloud`. Output: `/bbox`. Stop using Ctrl+C. Stop any previous host inference instance before running the container on the same topics. Launch a sensor driver or replay a ROS bag separately; the inference image does not include sensor data.

Build inputs already prepared on this machine: `docker/assets/pointpillars.onnx` and `.recovery/sdk/tensorrt-10.16.1/usr`. These are intentionally ignored by Git/recovery. A Dockerfile alone is not the model/SDK backup. Keep the original download; copy the required build inputs alongside the source on a new build machine. Once built, the image contains them and can run without the source/download directories.

Host prerequisites: Docker, a compatible NVIDIA driver and NVIDIA Container Toolkit configured for Docker. Containers cannot supply the host kernel driver. Network access is needed to download base/ROS packages during the first build. The SDK/model versions are fixed; ROS apt packages/base tag updates mean this is not a byte-for-byte locked build.

Training class labels/order, intensity normalization and coordinates remain unverified. Defaults are provisional numeric labels and scale 1.0; synthetic checks do not establish real detection accuracy. The node's current reliable subscription requires a compatible publisher. The bounded worker and configurable sensor QoS remain unfinished.

Select another input topic within the second command using `-e POINT_CLOUD_TOPIC=/your/lidar/topic`. Set ROS domain using `-e ROS_DOMAIN_ID=...`. To override model parameters, append ROS arguments after the image name, for example `run -p intensity_scale:=255.0`; only use normalization verified against your export specification. `docker/node.yaml` can also be edited before building. For shared systems, match the host ROS domain and middleware.

Development validation:

```bash
docker run --rm --gpus all pp-infer:jazzy-trt10 nvidia-smi
docker run --rm pp-infer:jazzy-trt10 ros2 pkg executables pp_infer
```

## Different machines and GPUs

The runtime code has no RTX 4060 model/architecture assumption. Startup inspects the selected CUDA device, requires SM 7.5 or newer, and builds an engine on that device. GPU compatibility follows [NVIDIA TensorRT 10.x support](https://docs.nvidia.com/deeplearning/tensorrt/10.x.x/getting-started/support-matrix.html). GPU memory must fit this model and engine build. Only the available RTX 4060 has been physically tested here; other supported devices still need target validation.

This image is Linux **amd64/x86-64**. Different Intel/AMD x86-64 hosts with supported NVIDIA GPUs can use the same built image and do not need host ROS, CUDA toolkit or TensorRT installed. A compatible host NVIDIA driver, Docker and NVIDIA Container Toolkit are required. Windows can use an appropriately configured Linux/WSL2 GPU container environment; the host-network recipe above is validated only on Linux. ARM64/SBSA and Jetson require separate matching SDK/platform images. Unsupported old GPUs cannot be made compatible by a Dockerfile.

To choose a GPU within the set visible to the container, add `-e PP_GPU_INDEX=1` to the run command. CUDA_VISIBLE_DEVICES is respected when PP_GPU_INDEX is unset; otherwise the first CUDA-visible device is used. CUDA device 0 after this remapping is shared by the preflight, engine builder and ROS runtime. To reduce the builder's workspace limit on smaller GPUs, add `-e PP_WORKSPACE_MIB=256`; this changes the cache key. It does not cap total GPU memory. Engine generation is serialized for a shared cache key using flock and promoted only after trtexec succeeds.

To run elsewhere, transfer the built image (for example using Docker save/load) or push it to your own registry. The image carries the model/libraries; the source checkout does not automatically carry ignored SDK/model data. No registry publication is performed by this task.

## Verification on this machine

- Full final Dockerfile build and four colcon tests passed; corrected ROS entrypoint included.
- Container GPU check and fresh ONNX engine generation passed.
- A synthetic ROS frame produced detections with the same header, twice across a restart.
- Exactly one engine generation occurred across both starts; the second reused the volume cache.
- Invalid GPU index failed before engine/node startup.
- Isolated validation container was stopped and removed. The image `pp-infer:jazzy-trt10` and `pp-engines` volume are retained.
- Real-data accuracy, other physical GPUs, ARM builds and CUDA memory instrumentation remain unverified.

The builder installs only needed CUDA packages from NVIDIA’s Ubuntu repository, pinned to CUDA 12.9 Update 1 component versions; it does not download the full CUDA development image. Host CUDA/toolchain files are not copied.
