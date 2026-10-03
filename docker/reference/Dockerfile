# Independent diagnostic environment; never replaces the deployment image.
FROM ubuntu:22.04
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl g++ python3 && \
    curl -fL https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb -o /tmp/keyring.deb && \
    dpkg -i /tmp/keyring.deb && rm /tmp/keyring.deb && apt-get update && \
    apt-get install -y --no-install-recommends \
      libnvinfer8=8.6.1.6-1+cuda12.0 libnvinfer-plugin8=8.6.1.6-1+cuda12.0 \
      libnvonnxparsers8=8.6.1.6-1+cuda12.0 libnvinfer-bin=8.6.1.6-1+cuda12.0 \
      libnvinfer-headers-dev=8.6.1.6-1+cuda12.0 libnvinfer-headers-plugin-dev=8.6.1.6-1+cuda12.0 \
      libcudnn8=8.9.0.131-1+cuda12.1 libcublas-12-0=12.0.2.224-1 cuda-cudart-dev-12-0=12.0.146-1 && \
    rm -rf /var/lib/apt/lists/* && \
    ln -s libnvinfer.so.8 /usr/lib/x86_64-linux-gnu/libnvinfer.so && \
    ln -s libnvinfer_plugin.so.8 /usr/lib/x86_64-linux-gnu/libnvinfer_plugin.so
ENV LD_LIBRARY_PATH=/usr/local/cuda-12.0/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64
ENV NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=compute,utility
WORKDIR /reference
# Compile upstream NMS unchanged; source revision and file hashes are fixed.
RUN mkdir upstream && \
    curl -fL https://raw.githubusercontent.com/NVIDIA-TAO/tao_toolkit_recipes/a540badc47812a17a94e924b537d49ad3969b5a8/tao_pointpillars/tensorrt_sample/src/postprocess.cpp -o upstream/postprocess.cpp && \
    curl -fL https://raw.githubusercontent.com/NVIDIA-TAO/tao_toolkit_recipes/a540badc47812a17a94e924b537d49ad3969b5a8/tao_pointpillars/tensorrt_sample/include/postprocess.h -o upstream/postprocess.h && \
    curl -fL https://raw.githubusercontent.com/NVIDIA-TAO/tao_toolkit_recipes/a540badc47812a17a94e924b537d49ad3969b5a8/tao_pointpillars/tensorrt_sample/LICENSE -o upstream/LICENSE && \
    printf '%s\n' \
      '7b67603d679510bcc02fd8fc63f84292dde5edb3017cdfd53625cd83c093d066  upstream/postprocess.cpp' \
      'd9e80c9e9aedc2d1e9d7f1818e5c137232980f3443329dfac5b08decc8f60481  upstream/postprocess.h' \
      'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30  upstream/LICENSE' | sha256sum --check
RUN apt-get update && apt-get install -y --no-install-recommends cuda-nvcc-12-0=12.0.140-1 && rm -rf /var/lib/apt/lists/*
COPY runner.cpp nms_driver.cpp ./
RUN g++ -std=c++17 -O2 -I/usr/include/x86_64-linux-gnu -I/usr/local/cuda-12.0/include \
      runner.cpp -L/usr/local/cuda-12.0/lib64 -lnvinfer -lnvinfer_plugin -lcudart -o /usr/local/bin/pp-reference && \
    g++ -std=c++17 -O2 -Iupstream -I/usr/local/cuda-12.0/include \
      nms_driver.cpp upstream/postprocess.cpp -o /usr/local/bin/pp-reference-nms && \
    dpkg-query -W > /reference/packages.txt
CMD ["pp-reference", "--info"]
