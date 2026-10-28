# Live Ouster deployment troubleshooting — 28 October 2026

This records user-supplied terminal evidence from physical host alfonso-h017,
Ubuntu 24.04.4, RTX A4500 Embedded GPU (8 GiB). These are host-session results,
not GPU checks performed in the CPU-only cloud development environment.

## Verified progress and remaining work

The host driver and Docker GPU access were repaired. TensorRT 10.16.1 built
and deserialized the FP32 engine with a 512 MiB workspace. The node started.
Matching the detector middleware to the host's Zenoh middleware made both
Ouster drivers and PointPillars discoverable together. Monitoring messages
confirmed incoming clouds, but all observed frames were rejected as invalid.
Successful live inference, detection quality and two-sensor fusion remain unverified.

## Host NVIDIA driver

Initially `modprobe nvidia` reported no module for running kernel 7.0.0-38.
Installed 595 driver modules existed only for kernel 6.17.0-35. GPU PCI
detection worked and Secure Boot was disabled. Automatic driver installation
attempted a conflicting 580 package set from mixed Ubuntu/CUDA repositories.
The working repair retained branch 595:

```bash
sudo apt-get -s install linux-modules-nvidia-595-open-$(uname -r) nvidia-driver-595-open
# Inspect the simulation before applying on another host.
sudo apt-get install linux-modules-nvidia-595-open-$(uname -r) nvidia-driver-595-open
# Save work before restarting; this interrupts other services.
sudo reboot
```

This installed driver 595.99.02 and modules for kernels 7.0.0-38 and 7.0.0-42.
Do not prescribe these exact branches/kernel packages to every host without
checking its GPU, available packages and dependency simulation first.
Validate host and container access with `nvidia-smi` and:

```bash
sudo docker run --rm --gpus all --entrypoint nvidia-smi pp-infer:jazzy-trt10
```

The CUDA version printed by nvidia-smi is driver capability, not the installed
container toolkit version. This host ran the image's CUDA 12.9 runtime.

## Engine creation and GPU faults

A 1024 MiB build attempt reported a failed allocation and an empty engine.
A 256 MiB attempt failed because VoxelGeneratorPlugin required 270532608 bytes
of scratch space, exceeding 268435456 available bytes. A 512 MiB attempt
completed engine creation; this is now the default in both launch paths.
Workspace is a builder memory-pool limit, not a cap on total GPU memory.
Changing it changes the engine cache key. A successful --skipInference build
does not demonstrate successful inference.

The host also recorded Xid 32 and a UVM global fatal error requiring OS reboot
(Xid 154 recovery action: Node Reboot Required). In that state nvidia-smi still
worked while CUDA startup failed. Save work and reboot when logs explicitly
require it; do not kill unidentified processes or reset a display GPU blindly.
The underlying cause of that GPU fault was not established.

## Ouster ROS library failure

Both sensors configured successfully, but drivers exited with an undefined
Fast CDR serialize symbol in the Ouster message typesupport library. Installed
Ouster builds were from September while Fast CDR/Fast RTPS were January builds.
The supplied GPU-repair apt transactions contained no ROS package changes.
After simulation, the user updated these seven packages together and reported
the Ouster launch working:

```bash
sudo apt-get -s install --only-upgrade \
  ros-jazzy-ouster-ros ros-jazzy-ouster-sensor-msgs \
  ros-jazzy-fastcdr ros-jazzy-fastrtps \
  ros-jazzy-rosidl-typesupport-fastrtps-cpp \
  ros-jazzy-rmw-fastrtps-cpp ros-jazzy-rmw-fastrtps-shared-cpp
# If the preview is appropriate, repeat without -s after stopping host ROS nodes.
```

## Match the ROS middleware

Host networking alone was insufficient: the host used rmw_zenoh_cpp with an
existing rmw_zenohd router, while the original image used default Fast DDS.
Domain ID was 0 on both sides. Installing Zenoh in the detector image and
starting it with RMW_IMPLEMENTATION=rmw_zenoh_cpp restored discovery and cloud
delivery. Leave the existing LiDAR drivers/router unchanged.

The Dockerfile now includes ros-jazzy-rmw-zenoh-cpp. The deployment wrapper
passes RMW_IMPLEMENTATION, defaulting to rmw_fastrtps_cpp when unset. Because
sudo may discard exported variables, pass the choice explicitly:

```bash
cd ~/MasterThesis
sudo env RMW_IMPLEMENTATION=rmw_zenoh_cpp ROS_DOMAIN_ID=0 \
  POINT_CLOUD_TOPIC=/ouster1/points PP_WORKSPACE_MIB=512 bash tools/deploy.sh
```

This expects the host's existing Zenoh router to be reachable through host
networking using the default Zenoh configuration. Custom router configurations
need matching settings; they are not automatically forwarded by the wrapper.
The Docker build fetches published Git source, so publish changes before
rebuilding. A previously committed local Zenoh test image does not update this
Dockerfile automatically. Rebuilding from this Dockerfile makes installation
reproducible. Stop only the intended old pointpillars container before relaunch.
The pp-engines named volume preserves engines across container recreation.

CLI discovery caches were misleading. `ros2 daemon stop` stops the CLI daemon,
not the nodes. Validate with fresh discovery:

```bash
ros2 node list --no-daemon --spin-time 5
sudo docker exec pointpillars /entrypoint.sh ros2 node info /pointpillars --no-daemon
ros2 topic info /ouster1/points --verbose
ros2 topic echo /bbox/stats --once
```

Ouster advertised BEST_EFFORT, while the detector advertised RELIABLE with depth
700. DDS reliability compatibility would prevent this pairing. Nevertheless,
the observed Zenoh setup delivered frames and emitted invalid-cloud counters.
Do not mistake endpoint visibility for successful processing or assume all RMWs
enforce the same matching behavior. Configurable detector sensor QoS remains work.

## Outstanding input conversion (LiDAR driver unchanged)

The actual cloud is little-endian, 128 by 1024 points, point_step 48. Fields:

| Field | Offset | PointField type |
| --- | --- | --- |
| x, y, z | 0, 4, 8 | FLOAT32 |
| t | 16 | UINT32 |
| ring | 20 | UINT16 |
| range | 24 | UINT32 |
| signal | 28 | UINT16 |
| near_ir | 30 | UINT16 |
| reflectivity | 32 | UINT8 |
| flags | 33 | UINT8 |

There is no intensity field. The current adapter requires scalar FLOAT32 XYZI,
so it reports "Missing or unsupported scalar FLOAT32 XYZI field/offset".
Monitoring showed 565 invalid clouds, zero processed frames and zero inference
errors. Middleware connectivity is established; model execution is not.

Next implement a separate converter or detector adapter accepting these fields,
preserving header/XYZ and converting a selected channel numerically to FLOAT32
intensity. Merely renaming a field or changing its datatype metadata is invalid.
Keep the LiDAR driver unchanged. Reflectivity is a reasonable initial candidate
because it is range-compensated; raw signal has different semantics. Neither
channel nor scaling has been validated against this model's training contract.
Make channel/scaling explicit and compare recorded data before claiming accuracy.
No converter, sensor calibration, coordinate transformation or fusion of both
Ouster sensors is implemented by this troubleshooting update.
