# Optional native project-local TensorRT setup

Docker now downloads its own SDK/model and needs none of this host setup. For native work after moving the checkout, use fresh build/install directories: old generated CMake caches and ROS setup files can contain the previous absolute path. Choose new `--build-base`/`--install-base` directories consistently for build, test and overlay sourcing. The commands below assume fresh default directories.

The downloaded SDK is extracted, not registered with apt/dpkg. System installation was unavailable without a sudo password. Original package: `/home/ae/Downloads/nv-tensorrt-local-repo-ubuntu2404-10.16.1-cuda-12.9_1.0-1_amd64.deb`.

TensorRT 10.16.1.11 runtime/development/plugin/parser components are under `.recovery/sdk/tensorrt-10.16.1/usr`. Exact artifact hashes are in `config/runtime_inventory.json`.

```bash
cd '/media/ae/New Volume/MasterThesis'
source /opt/ros/jazzy/setup.bash
source tools/env_tensorrt.sh
colcon build --packages-select pp_infer --cmake-args \
  -DPP_BUILD_RUNTIME=ON -DPP_BUILD_ROS_ADAPTER=ON -DBUILD_TESTING=ON \
  -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=/usr/bin/python3
source install/setup.bash
colcon test --packages-select pp_infer --ctest-args --output-on-failure
colcon test-result --verbose
./build/pp_infer/runtime_smoke .recovery/engines/pointpillars-fp32.smoke.engine
```

The smoke command requires host GPU device access. It exercises repeated synthetic inference; it is not an accuracy benchmark. The existing ROS launch file has historical hardcoded paths and unverified class/intensity settings; do not use it as a validated deployment configuration. W06/W07 will supply the bounded worker and launch configuration.

Recovery snapshots exclude `.recovery` SDK/engine/build/log artifacts. Keep the original DEB and ONNX independently. To reconstruct the local SDK, extract the outer DEB with `dpkg-deb --extract`, then the SDK component DEBs with the same command into one local root; no package maintainer scripts are run. The full system installation remains optional and requires sudo.

## Colcon build and ros2 run

```bash
cd '/media/ae/New Volume/MasterThesis'
source /opt/ros/jazzy/setup.bash
source tools/env_tensorrt.sh
colcon build --packages-select pp_infer --cmake-args -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=/usr/bin/python3
source install/setup.bash
ros2 run pp_infer pp_infer --ros-args --params-file .recovery/run/node.yaml
```

After moving this checkout, regenerate the native parameter file using the guide's Native engine and configuration procedure: an existing engine_path can still point to the old Desktop directory. Stop any existing instance before launching another on the same topics. The startup YAML uses provisional class labels and intensity scaling; replace them with validated model settings for real data. `colcon test --packages-select pp_infer` and `colcon test-result --verbose` passed four tests. Source ROS, the SDK environment and the workspace overlay in each new terminal.
