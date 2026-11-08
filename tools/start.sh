#!/usr/bin/env bash
# Start the saved inference image without building or downloading updates.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "$project_root/tools/docker_foreground.sh"

case "${1:-}" in
  -h|--help)
    cat <<'EOF'
Usage: sudo bash tools/start.sh

Run tools/deploy.sh once to build the image, then use this launcher for later runs.
Starts inference in the foreground; Ctrl+C stops and removes the container.
The local image and persistent engine cache are retained. No image is pulled.

Settings (same defaults as deploy.sh):
  PP_IMAGE                 pp-infer:jazzy-trt10
  PP_CONTAINER_NAME        pointpillars
  PP_ENGINE_VOLUME         pp-engines
  ROS_DOMAIN_ID            0
  RMW_IMPLEMENTATION       rmw_fastrtps_cpp
  POINT_CLOUD_TOPIC        /point_cloud
  DETECTIONS_TOPIC         /bbox
  PP_CONFIDENCE_THRESHOLD  0.4
  PP_GPU_INDEX             0
  PP_WORKSPACE_MIB         512

Example:
  sudo env RMW_IMPLEMENTATION=rmw_zenoh_cpp POINT_CLOUD_TOPIC=/ouster1/points bash tools/start.sh
EOF
    exit 0 ;;
esac
[[ $# -eq 0 ]] || { echo 'Unexpected arguments; use --help. Configure startup through environment variables.' >&2; exit 2; }

image="${PP_IMAGE:-pp-infer:jazzy-trt10}"
container="${PP_CONTAINER_NAME:-pointpillars}"
volume="${PP_ENGINE_VOLUME:-pp-engines}"
command -v docker >/dev/null || { echo 'Install Docker and NVIDIA Container Toolkit first.' >&2; exit 1; }
docker info >/dev/null
if docker container inspect "$container" >/dev/null 2>&1; then
  echo "Container '$container' already exists. Stop/remove the intended old instance or set PP_CONTAINER_NAME." >&2
  exit 1
fi
if ! docker image inspect "$image" >/dev/null 2>&1; then
  echo "Local image '$image' is missing. Run sudo bash tools/deploy.sh first (with the same PP_IMAGE if customized)." >&2
  exit 1
fi
pp_run_container --pull=never --rm --init --name "$container" \
  --gpus all --network host --ipc host \
  -e "ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}" \
  -e "RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}" \
  -e "POINT_CLOUD_TOPIC=${POINT_CLOUD_TOPIC:-/point_cloud}" \
  -e "DETECTIONS_TOPIC=${DETECTIONS_TOPIC:-/bbox}" \
  -e "PP_CONFIDENCE_THRESHOLD=${PP_CONFIDENCE_THRESHOLD:-0.4}" \
  -e "PP_GPU_INDEX=${PP_GPU_INDEX:-0}" \
  -e "PP_WORKSPACE_MIB=${PP_WORKSPACE_MIB:-512}" \
  -v "$volume:/var/lib/pp_infer" "$image"
