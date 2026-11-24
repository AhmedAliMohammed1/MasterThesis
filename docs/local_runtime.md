# Native development without the inference container

Reviewed 8 November 2026. Docker is the normal deployment route; [startup and replay](STARTUP_AND_REPLAY.md) needs no host CUDA/TensorRT development setup. Use native builds when debugging C++, running selected tests or developing the adapter separately.

## Before building

The runtime needs host ROS Jazzy development dependencies, PCL, CUDA and matching TensorRT 10 headers/libraries. The recorded optional SDK is extracted under `.recovery/sdk/tensorrt-10.16.1/usr`, with identity in [the runtime inventory](../config/runtime_inventory.json). It is not tracked by Git and is not registered with apt. `tools/env_tensorrt.sh` exposes that specific extracted SDK; it does not download or install it.

If the SDK is missing, use the container workflow or prepare the documented matching SDK from independently retained artifacts. Do not reuse a generated build tree after moving the checkout: CMake caches and ROS setup files can contain old absolute paths. The commands below use separate development directories.

## Build and test the full runtime

From the project root:

```bash
source /opt/ros/jazzy/setup.bash
source tools/env_tensorrt.sh
colcon --log-base .recovery/native-log build --packages-select pp_infer \
  --build-base .recovery/native-build --install-base .recovery/native-install \
  --cmake-args -DPP_BUILD_RUNTIME=ON -DPP_BUILD_ROS_ADAPTER=ON \
    -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release \
    -DPython3_EXECUTABLE=/usr/bin/python3
source .recovery/native-install/setup.bash
colcon --log-base .recovery/native-log test --packages-select pp_infer \
  --build-base .recovery/native-build --install-base .recovery/native-install \
  --ctest-args --output-on-failure
colcon test-result --test-result-base .recovery/native-build --verbose
```

Use a valid matching engine for a GPU smoke check:

```bash
.recovery/native-build/pp_infer/runtime_smoke /absolute/path/to/matching.engine
```

This requires working GPU device access and checks synthetic inference, not accuracy. It does not download a model or build an engine.

## Run the node with explicit configuration

Prepare a parameter YAML containing a real `engine_path` and the intended processing settings. A direct command is:

```bash
ros2 run pp_infer pp_infer --ros-args \
  --params-file /absolute/path/to/node.yaml \
  -r __node:=pointpillars -p confidence_threshold:=0.4
```

Source ROS, the SDK environment and the new overlay in every terminal. Native default naming is `/minimal_publisher` unless remapped as above. The historical detector launch file contains old absolute paths and is not the validated deployment interface. The container's engine generation does not occur in `ros2 run`.

Input must be compatible FLOAT32 XYZI. For raw Ouster data, run the separate adapter with matching topic, domain and middleware. Keep detector `intensity_scale` at 1.0 when the adapter has already divided the selected channel. [Adapter build and launch](LIVE_OUSTER_ADAPTER.md#build-and-run-without-a-gpu).

## Tests that do not need GPU inference

For plain C++ geometry/output-contract tests without ROS:

```bash
cmake -S . -B .recovery/core-build \
  -DPP_BUILD_RUNTIME=OFF -DPP_BUILD_ROS_ADAPTER=OFF -DBUILD_TESTING=ON
cmake --build .recovery/core-build
ctest --test-dir .recovery/core-build --output-on-failure
```

For ROS conversion/publication tests without CUDA/TensorRT, follow the adapter-only colcon build in the adapter guide. ROS/PCL development dependencies are still required. Python tests use:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

Some download tests open localhost sockets; a restricted execution sandbox can block these even when the code is correct. Report environment failures separately from test failures.

## Research status

The latest recorded suite has 119 Python tests; the deployment image separately passed seven C++/ROS tests. The annotated channel study used unchanged production inference/NMS in a direct runner and supports reflectivity/255 as a development baseline. Both channels still have zero qualifying 3D matches. Capacity controls remain experimental, and no bounded worker or production point-selection policy has been installed. [Results, limitations and proposal](OUSTER_CHANNEL_DECISION.md).

Keep ignored SDKs, engines and raw observations backed up independently. The [thesis/documentation index](README.md) points to the current research narrative; dated recovery entries retain their historical scope.
