# syntax=docker/dockerfile:1
# BuildKit resolves this Git reference on each build; local source is not copied.
FROM ubuntu:24.04 AS source
ARG GIT_REPO=https://github.com/AhmedAliMohammed1/MasterThesis.git
ARG GIT_REF=main
ADD --keep-git-dir=true ${GIT_REPO}#${GIT_REF} /source/

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

FROM base AS sdk
# Signed apt metadata validates downloads. Header-only packages avoid huge static
# development archives; this project links the shared runtime libraries.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libnvinfer10=10.16.1.11-1+cuda12.9 \
      libnvinfer-plugin10=10.16.1.11-1+cuda12.9 \
      libnvonnxparsers10=10.16.1.11-1+cuda12.9 \
      libnvinfer-bin=10.16.1.11-1+cuda12.9 \
      libnvinfer-lean10=10.16.1.11-1+cuda12.9 \
      libnvinfer-vc-plugin10=10.16.1.11-1+cuda12.9 \
      libnvinfer-dispatch10=10.16.1.11-1+cuda12.9 \
      libnvinfer-headers-dev=10.16.1.11-1+cuda12.9 \
      libnvinfer-headers-plugin-dev=10.16.1.11-1+cuda12.9 && \
    ln -s libnvinfer.so.10 /usr/lib/x86_64-linux-gnu/libnvinfer.so && \
    ln -s libnvinfer_plugin.so.10 /usr/lib/x86_64-linux-gnu/libnvinfer_plugin.so && \
    rm -rf /var/lib/apt/lists/*
ENV TENSORRT_ROOT=/usr CUDAToolkit_ROOT=/usr/local/cuda-12.9
ENV LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:/usr/local/cuda-12.9/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64

FROM base AS model
ARG MODEL_URL=https://api.ngc.nvidia.com/v2/models/nvidia/tao/pointpillarnet/versions/deployable_v1.1/files/pointpillars_deployable.onnx
ARG MODEL_SHA256=2dcabddc3a365e9608a112d7bbbb7db769a6dddeeaa59aa03611a83113326da1
RUN mkdir -p /opt/models && \
    curl -fL --retry 3 --connect-timeout 30 "$MODEL_URL" -o /opt/models/pointpillars.onnx && \
    printf '%s  %s\n' "$MODEL_SHA256" /opt/models/pointpillars.onnx | sha256sum --check

FROM sdk AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential cmake git python3-colcon-common-extensions && rm -rf /var/lib/apt/lists/*
COPY --from=source /source/ /workspace/src/pp_infer/
WORKDIR /workspace
RUN git -C src/pp_infer rev-parse HEAD > source-revision.txt && \
    rm -rf src/pp_infer/.git && \
    source /opt/ros/jazzy/setup.bash && colcon build --packages-select pp_infer \
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
COPY --from=sdk /usr/lib/x86_64-linux-gnu/libnvinfer*.so* /opt/tensorrt/lib/
COPY --from=sdk /usr/lib/x86_64-linux-gnu/libnvonnxparser.so* /opt/tensorrt/lib/
COPY --from=sdk /usr/bin/trtexec /usr/local/bin/trtexec
COPY --from=base /usr/local/cuda-12.9/targets/x86_64-linux/lib/libcudart.so* /opt/cuda/lib/
COPY --from=base /usr/local/cuda-12.9/targets/x86_64-linux/lib/libnvrtc*.so* /opt/cuda/lib/
COPY --from=base /usr/local/cuda-12.9/targets/x86_64-linux/lib/libnvJitLink.so* /opt/cuda/lib/
COPY --from=base /usr/local/cuda-12.9/targets/x86_64-linux/lib/libcublas*.so* /opt/cuda/lib/
ENV LD_LIBRARY_PATH=/opt/tensorrt/lib:/opt/cuda/lib:/usr/local/nvidia/lib:/usr/local/nvidia/lib64
COPY --from=build /workspace/install/ /workspace/install/
COPY --from=build /workspace/source-revision.txt /opt/pp_infer/source-revision.txt
COPY --from=model /opt/models/pointpillars.onnx /opt/models/pointpillars.onnx
COPY --from=source /source/docker/node.yaml /opt/pp_infer/node.yaml
COPY --from=source /source/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENV NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=compute,utility
WORKDIR /workspace
ENTRYPOINT ["/entrypoint.sh"]
CMD ["run"]
