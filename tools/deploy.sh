#!/usr/bin/env bash
# Build current published Git source, then start the GPU node in the foreground.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
image="${PP_IMAGE:-pp-infer:jazzy-trt10}"
container="${PP_CONTAINER_NAME:-pointpillars}"
volume="${PP_ENGINE_VOLUME:-pp-engines}"
command -v docker >/dev/null || { echo "Install Docker and NVIDIA Container Toolkit first." >&2; exit 1; }
docker info >/dev/null
if docker container inspect "$container" >/dev/null 2>&1; then
  echo "Container '$container' already exists. Stop/remove the intended old instance or set PP_CONTAINER_NAME." >&2
  exit 1
fi
docker build --pull --tag "$image" \
  --build-arg "GIT_REPO=${PP_GIT_REPO:-https://github.com/AhmedAliMohammed1/MasterThesis.git}" \
  --build-arg "GIT_REF=${PP_GIT_REF:-main}" "$@" "$project_root"
# A failed build returns before touching containers or engine volumes.
exec docker run --rm --init --name "$container" \
  --gpus all --network host --ipc host \
  -e "ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}" \
  -e "POINT_CLOUD_TOPIC=${POINT_CLOUD_TOPIC:-/point_cloud}" \
  -e "DETECTIONS_TOPIC=${DETECTIONS_TOPIC:-/bbox}" \
  -e "PP_GPU_INDEX=${PP_GPU_INDEX:-0}" \
  -e "PP_WORKSPACE_MIB=${PP_WORKSPACE_MIB:-1024}" \
  -v "$volume:/var/lib/pp_infer" "$image"
