# Download/prepare sample data without installing software on the host.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates python3 ffmpeg \
    && rm -rf /var/lib/apt/lists/*
