# Automatic Docker build and deployment

> **Latest update — 23 October 2026:** confidence filtering and counters were pushed/deployed from `8a87a73`; 73 Python tests, five C++/ROS tests and 60 deployed GPU replay frames passed. The trial detector, KITTI player and RViz were then stopped at the user's request (19:47 UTC); image, engine cache and frozen results are preserved. Accuracy acceptance remains open. [Verified results and restart instructions](../docs/CURRENT_STATUS_AND_RESULTS.md#trial-shutdown-and-restart--23-october-2026).

> **Status reviewed 23 October 2026.** Deployment behavior is unchanged. Later normalized Ouster replay matched 556 occurrences and frontal KITTI replay matched 154 frames; these are integration results. The labeled KITTI accuracy baseline remains poor, and the synchronous depth-700 subscriber is still present. [Current results and evidence](../docs/CURRENT_STATUS_AND_RESULTS.md).

On a Linux x86-64 host with a supported NVIDIA GPU, working driver, Docker and NVIDIA Container Toolkit, run from the project folder:

```bash
sudo bash tools/deploy.sh
```

This one command always invokes `docker build --pull` and then creates a new foreground `docker run --rm` container. Docker reuses eligible cached layers, but the wrapper has no update-only check or immediate image-only launch mode. It does not update an existing running container. Ctrl+C stops it. The wrapper will not replace an existing container with the same name; stop/remove the intended old instance first or select another `PP_CONTAINER_NAME`.

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

## Model and engine lifecycle

Documentation reviewed on **23 October 2026**. The GPU and accuracy evidence below retains its original dates; later sensor results are consolidated in the current-status link above.

| Phase | What happens | File location inside the container |
| --- | --- | --- |
| Image build | Download and checksum-verify the pretrained ONNX; install TensorRT/CUDA packages and the ROS application. Docker may reuse cached layers. | ONNX: `/opt/models/pointpillars.onnx`; TensorRT libraries: `/opt/tensorrt/lib/`; CUDA libraries: `/opt/cuda/lib/`. |
| Container startup | Check the GPU, hash ONNX and reuse a matching nonempty engine or generate one with `trtexec`. | `/var/lib/pp_infer/<cache-key>.engine`, normally in persistent volume `pp-engines`. |
| ROS startup and inference | Pass `engine_path` to `ros2 run`, load the engine once and reuse its execution context and GPU buffers for incoming clouds. | The ROS node reads the `.engine` file, not ONNX. |

At startup, engines are keyed by model hash, GPU model/UUID/capability, driver, CUDA APIs and build recipe. The current recipe builds FP32, batch one, with TF32 disabled. Builds for the same key are serialized; temporary files are promoted only after successful generation. The engine is created locally from the trained network, without retraining. ONNX is model data, not an installer or archive; the engine is a serialized execution plan, not a downloaded model.

The entrypoint prepares the engine **before** executing `ros2 run pp_infer pp_infer --ros-args --params-file /opt/pp_infer/node.yaml -p engine_path:=<saved-engine-path>`, with the node-name and topic remappings. The node initializes plugins, reads the engine bytes, calls `deserializeCudaEngine`, checks its tensor interface and creates the execution context and reusable buffers. It runs the network on the GPU; CPU code handles ROS, input preparation, output checks and NMS.

Normal container startup still needs ONNX for its checksum when reusing a cached engine. Direct `ros2 run` needs an already prepared engine, required libraries and parameters; it does not download ONNX or build an engine. The node's legacy `model_path` is stored but does not load ONNX, and `data_type` does not change the loaded engine's precision. Transfer the image to another supported computer and let startup prepare its matching engine. A nonempty but corrupted cache file is not automatically rebuilt.

For the complete explanation and both diagrams, see the [explanation README](../README_PROJECT_EXPLANATIONS.md#7-downloads-and-engine-generation-in-docker-today). The [latest discussion continuation](../docs/CHAT_DISCUSSION_RECORD.md#explanation-and-presentation-continuation-saved-5-october-2026) records the questions and presentation changes; the [updated presentation source](../docs/PROJECT_MIGRATION_PRESENTATION.tex) gives the short version.

Node `/pointpillars` receives `/point_cloud` (`sensor_msgs/msg/PointCloud2`) and publishes `/bbox` (`vision_msgs/msg/Detection3DArray`). Start a sensor or bag publisher separately; the container does not generate real data. Input needs little-endian scalar FLOAT32 XYZI and a compatible reliable publisher.

Wrapper settings: `PP_IMAGE`, `PP_CONTAINER_NAME`, `PP_ENGINE_VOLUME`, `PP_GIT_REPO`, `PP_GIT_REF`, `PP_GPU_INDEX`, `PP_WORKSPACE_MIB`, `ROS_DOMAIN_ID`, `POINT_CLOUD_TOPIC`, `DETECTIONS_TOPIC`. Extra wrapper arguments are forwarded to `docker build`, including build arguments and secrets. For example:

```bash
sudo env POINT_CLOUD_TOPIC=/lidar/points ROS_DOMAIN_ID=7 \
  PP_GPU_INDEX=0 PP_WORKSPACE_MIB=256 bash tools/deploy.sh
```

The new `PP_CONFIDENCE_THRESHOLD` setting overrides the node YAML's default score gate of 0.5. For example, `sudo env PP_CONFIDENCE_THRESHOLD=0.7 bash tools/deploy.sh`. An unset/empty value leaves the YAML setting in effect. The threshold can also change live through `ros2 param set /pointpillars confidence_threshold 0.7` (use `/entrypoint.sh` through `docker exec` when running inside the container).

New images publish only boxes at or above the threshold. The standard detection array remains on `/bbox`; `/bbox/stats` adds per-frame/cumulative counts as DiagnosticArray, and `/bbox/count` publishes the RViz text marker. Monitoring topics follow detection-topic remapping. The Docker stages now declare diagnostic/visualization message packages and the build includes a fifth, GPU-free ROS output integration test. See [the feature guide](../docs/CONFIDENCE_FILTER_AND_MONITORING.md). Local changes still need publication in the selected Git revision before this remote-source Docker build includes them; no existing image/container is updated automatically.

GPU indexes refer to the visible CUDA set. Workspace limits do not cap total GPU memory. The image is Linux amd64 and follows [TensorRT 10.x hardware support](https://docs.nvidia.com/deeplearning/tensorrt/10.x.x/getting-started/support-matrix.html), with capability 7.5 as a floor. ARM/Jetson requires a separate image. Only the available RTX 4060 has been physically tested.

Exact model class order is verified; numerical input/output reference parity and accuracy acceptance remain unfinished. Defaults remain generic labels and scale 1.0. Synthetic tests do not establish real-data accuracy. Bounded-worker integration, configurable QoS, full CUDA memory/failure validation and operational acceptance remain unfinished.

See the [A-to-Z LaTeX guide](../docs/PROJECT_IMPLEMENTATION_AND_DEPLOYMENT_GUIDE.tex), [README](../README.md) and [progress record](../recovery/PROGRESS.md) for setup, verification and limits.

## Optional desktop visualization

The inference image stays headless. Keep the node and a LiDAR/bag publisher running, then use `bash tools/visualize.sh` from this checkout on a ROS Jazzy desktop. The saved view displays `/point_cloud` and `/bbox` with the official vision_msgs plugin; no inference rebuild is needed. Host RViz must be installed. See the [viewer setup and limits](../README.md#visualize-points-and-boxes-in-rviz) for packages, fixed frame, domain and transport settings. GPU inference can stay on a separate compatible machine if ROS network discovery is configured.

## Sample bag and camera clip helper

After building the inference image, `bash tools/rosbag_demo.sh` downloads/verifies the tested KITTI bag, prepares a camera reference MP4 from its original drive and loops reliable LiDAR playback. `prepare` downloads assets only; `stop` stops only helper-owned playback. A separate `pp-infer:demo-tools` image supplies Python/FFmpeg without host installation. Matching active playback is reused; different existing containers are preserved. See the [sample instructions](../README.md#download-and-play-the-sample-bag-with-matching-camera-video) for storage, recovery, settings and the independent video's timing/accuracy limits.


## Labeled accuracy status (3 October 2026)

The published runtime image was exercised on 32 matched KITTI diagnostic frames. The 16-frame test split produced no moderate 3D matches; moderate BEV AP_R40 was 5.75% Car, 0% Pedestrian and0.0258% Cyclist, with Vehicle explicitly evaluated as Car compatibility. This is a poor diagnostic baseline, not accuracy acceptance. Green ground truth can now be compared with predictions through the host player/viewer on isolated domain 42. See [results and reproduction](../docs/KITTI_ACCURACY_RESULTS.md) and [accuracy inventory](../config/kitti_accuracy_inventory.json). These host validation tools do not replace the image's normal startup, and local edits require publication before a Git-source Docker build includes them.


## Independent reference update: 3 October 2026

A separate TensorRT 8.6 engine for the exact ONNX reproduced the poor KITTI baseline and approximately 1.53 m upward car error. Three repeats per runtime (192 raw inferences) still produced zero moderate 3D matches in both runtimes. NVIDIA's unchanged NMS and our NMS selected identical boxes on all 192 same-candidate observations. Strict numerical parity remains unmet: both runtimes vary, and 12 frames exceed the export's 10,000-voxel limit. Two tuning-only capacity controls improved repeat matching to roughly 99.6–100%; no production adaptation was installed. Two actual CUDA 12.9 allocation probes reported zero errors, which does not clear the internal tensor-bounds concern or complete GPU memory validation. Read [independent comparison](../docs/MODEL_REFERENCE_COMPARISON.md) for commands, results, source evidence and limits. Pretrained weights alone are not established as the cause; bounded voxelization and the original input/training contract are next.

The 23 October trial was stopped after verifying the published feature; the tagged image and `pp-engines` cache remain. [Exact trial results and restart](../docs/CURRENT_STATUS_AND_RESULTS.md#trial-shutdown-and-restart--23-october-2026).
