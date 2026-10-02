# syntax=docker/dockerfile:1
FROM ubuntu:24.04 AS base
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive ROS_DISTRO=jazzy
RUN test "$(dpkg --print-architecture)" = amd64 && apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg && \
    curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu noble main" > /etc/apt/sources.list.d/ros2.list && \
    curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb -o /tmp/cuda-keyring.deb && \
    dpkg -i /tmp/cuda-keyring.deb && rm /tmp/cuda-keyring.deb && \
    apt-get update && apt-get install -y --no-install-recommends \
      cuda-cudart-dev-12-9=12.9.79-1 cuda-nvcc-12-9=12.9.86-1 \
      cuda-nvrtc-12-9=12.9.86-1 libcublas-12-9=12.9.1.4-1 libnvjitlink-12-9=12.9.86-1 \
      ros-jazzy-ros-base ros-jazzy-vision-msgs ros-jazzy-pcl-conversions libpcl-dev && \
    rm -rf /var/lib/apt/lists/*
# SDK data extracted from the verified local DEB; no host driver is included.
COPY .recovery/sdk/tensorrt-10.16.1/usr/include/ /opt/tensorrt/include/
COPY .recovery/sdk/tensorrt-10.16.1/usr/lib/x86_64-linux-gnu/ /opt/tensorrt/lib/
COPY .recovery/sdk/tensorrt-10.16.1/usr/bin/trtexec /usr/local/bin/trtexec
ENV TENSORRT_ROOT=/opt/tensorrt CUDAToolkit_ROOT=/usr/local/cuda-12.9
ENV LD_LIBRARY_PATH=/opt/tensorrt/lib:/usr/local/cuda-12.9/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64

FROM base AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential cmake python3-colcon-common-extensions && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace/src/pp_infer
COPY CMakeLists.txt package.xml ./
COPY include/ include/
COPY src/ src/
COPY tests/ tests/
COPY launch/ launch/
WORKDIR /workspace
RUN source /opt/ros/jazzy/setup.bash && colcon build --packages-select pp_infer \
      --cmake-args -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=/usr/bin/python3 && \
    source install/setup.bash && colcon test --packages-select pp_infer && colcon test-result --verbose

FROM ubuntu:24.04 AS runtime
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive ROS_DISTRO=jazzy
COPY --from=base /usr/share/keyrings/ros-archive-keyring.gpg /usr/share/keyrings/ros-archive-keyring.gpg
COPY --from=base /etc/apt/sources.list.d/ros2.list /etc/apt/sources.list.d/ros2.list
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates util-linux ros-jazzy-ros-base ros-jazzy-vision-msgs libpcl-common1.14 && \
    rm -rf /var/lib/apt/lists/*
COPY .recovery/sdk/tensorrt-10.16.1/usr/lib/x86_64-linux-gnu/ /opt/tensorrt/lib/
COPY .recovery/sdk/tensorrt-10.16.1/usr/bin/trtexec /usr/local/bin/trtexec
# Shared CUDA libraries only; omit the compiler, static libs and headers.
COPY --from=base /usr/local/cuda-12.9/targets/x86_64-linux/lib/libcudart.so* /opt/cuda/lib/
COPY --from=base /usr/local/cuda-12.9/targets/x86_64-linux/lib/libnvrtc*.so* /opt/cuda/lib/
COPY --from=base /usr/local/cuda-12.9/targets/x86_64-linux/lib/libnvJitLink.so* /opt/cuda/lib/
COPY --from=base /usr/local/cuda-12.9/targets/x86_64-linux/lib/libcublas*.so* /opt/cuda/lib/
ENV LD_LIBRARY_PATH=/opt/tensorrt/lib:/opt/cuda/lib:/usr/local/nvidia/lib:/usr/local/nvidia/lib64
COPY --from=build /workspace/install/ /workspace/install/
COPY docker/assets/pointpillars.onnx /opt/models/pointpillars.onnx
COPY docker/node.yaml /opt/pp_infer/node.yaml
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENV NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=compute,utility
WORKDIR /workspace
ENTRYPOINT ["/entrypoint.sh"]
CMD ["run"]
