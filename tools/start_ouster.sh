#!/usr/bin/env bash
# Start the saved detector image with the live Ouster adapter in one container.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "$project_root/tools/docker_foreground.sh"
source "$project_root/tools/ouster_profile.sh"
case "${1:-}" in
  -h|--help)
    cat <<'EOF'
Usage: sudo bash tools/start_ouster.sh [bag] [reflectivity|signal]

Starts the Ouster adapter and detector together using the saved image. The Ouster
driver must already be running. Ctrl+C stops both; the engine cache is retained.
No build, image pull, package installation, or driver configuration is performed.
For the downloaded bag: start_ouster.sh bag, then start_ouster_bag.sh.
Bag mode shares the player's Fast DDS, domain 99 and /sensing/lidar/points.

Defaults:
  OUSTER_POINT_CLOUD_TOPIC     /ouster1/points (raw sensor input)
  POINT_CLOUD_TOPIC            /point_cloud (adapted detector input)
  PP_OUSTER_INTENSITY_SOURCE   reflectivity (overridden by positional choice)
  PP_OUSTER_INTENSITY_DIVISOR  255.0 for reflectivity, 65535.0 for signal
  RMW_IMPLEMENTATION          rmw_zenoh_cpp (match your Ouster drivers)
  ROS_DOMAIN_ID               0
  PP_IMAGE                   pp-infer:jazzy-trt10 (must include ouster_adapter)
  PP_CONTAINER_NAME           pointpillars
  PP_ENGINE_VOLUME            pp-engines
  DETECTIONS_TOPIC            /bbox
  PP_CONFIDENCE_THRESHOLD     0.4
  PP_GPU_INDEX                0
  PP_WORKSPACE_MIB            512

Examples:
  sudo bash tools/start_ouster.sh
  sudo bash tools/start_ouster.sh signal
  sudo env OUSTER_POINT_CLOUD_TOPIC=/ouster2/points bash tools/start_ouster.sh
  sudo env RMW_IMPLEMENTATION=rmw_fastrtps_cpp bash tools/start_ouster.sh

This launcher explicitly converts the selected channel. It does not automatically
pass through an existing intensity field, fuse sensors, or choose the best feature.
The intensity divisor must be a positive decimal number; conversion is experimental.
EOF
    exit 0 ;;
esac
profile=live
if [[ ${1:-} == bag ]]; then profile=bag; shift; fi
pp_ouster_profile "$profile"
[[ $# -le 1 ]] || { echo 'Use --help; expected at most one source choice.' >&2; exit 2; }
source_channel=${1:-${PP_OUSTER_INTENSITY_SOURCE:-reflectivity}}
case "$source_channel" in
  reflectivity) default_divisor=255.0 ;;
  signal) default_divisor=65535.0 ;;
  *) echo 'Choose reflectivity or signal; use --help.' >&2; exit 2 ;;
esac
divisor=${PP_OUSTER_INTENSITY_DIVISOR:-$default_divisor}
[[ $divisor =~ ^[0-9]+([.][0-9]+)?$ && ${divisor//[.0]/} != '' ]] || {
  echo 'PP_OUSTER_INTENSITY_DIVISOR must be a positive decimal number.' >&2; exit 2;
}
[[ $divisor == *.* ]] || divisor+=.0
raw_topic=${OUSTER_POINT_CLOUD_TOPIC:-/ouster1/points}
adapted_topic=${POINT_CLOUD_TOPIC:-/point_cloud}
for topic in "$raw_topic" "$adapted_topic" "${DETECTIONS_TOPIC:-/bbox}"; do
  [[ $topic =~ ^/([a-zA-Z_][a-zA-Z0-9_]*)(/[a-zA-Z_][a-zA-Z0-9_]*)*$ ]] || {
    echo "Invalid absolute ROS topic: $topic" >&2; exit 2;
  }
done
[[ $raw_topic != "$adapted_topic" ]] || { echo 'Raw and adapted topics must differ.' >&2; exit 2; }
domain=${ROS_DOMAIN_ID:-0}
[[ $domain =~ ^[0-9]{1,3}$ && $((10#$domain)) -le 232 ]] || {
  echo 'ROS_DOMAIN_ID must be 0..232.' >&2; exit 2;
}
image=${PP_IMAGE:-pp-infer:jazzy-trt10}
container=${PP_CONTAINER_NAME:-pointpillars}
volume=${PP_ENGINE_VOLUME:-pp-engines}
supervisor="$project_root/docker/ouster_stack.sh"
[[ -f $supervisor && $supervisor != *,* ]] || {
  echo 'The checkout must contain docker/ouster_stack.sh and its path must not contain commas.' >&2; exit 2;
}
command -v docker >/dev/null || { echo 'Install Docker and NVIDIA Container Toolkit first.' >&2; exit 1; }
docker info >/dev/null
if docker container inspect "$container" >/dev/null 2>&1; then
  echo "Container '$container' already exists. Stop/remove the intended instance or set PP_CONTAINER_NAME." >&2
  exit 1
fi
if ! docker image inspect "$image" >/dev/null 2>&1; then
  echo "Local image '$image' is missing. Build the updated image first with tools/deploy.sh." >&2
  exit 1
fi
if ! docker run --pull=never --rm --network none --entrypoint /usr/bin/test "$image" \
    -x /workspace/install/pp_infer/lib/pp_infer/ouster_adapter; then
  echo "Image '$image' lacks the Ouster adapter, or its preflight container failed." >&2
  echo 'Rebuild the current checkout with tools/deploy.sh (PP_BUILD_ONLY=1 builds without starting).' >&2
  exit 1
fi
printf 'Ouster pipeline: %s -> [%s / %s] -> %s -> %s\n' \
  "$raw_topic" "$source_channel" "$divisor" "$adapted_topic" "${DETECTIONS_TOPIC:-/bbox}"
echo 'Starting adapter and detector. Ctrl+C stops both. The Ouster driver must already be running.'
printf 'Profile: %s; domain: %s; middleware: %s\n' "$profile" "$domain" "$RMW_IMPLEMENTATION"
if [[ $profile == live ]]; then
  echo 'For the downloaded ROS bag use: sudo bash tools/start_ouster.sh bag'
fi
pp_run_container --pull=never --rm --init --stop-timeout 10 --name "$container" \
  --gpus all --network host --ipc host \
  --mount "type=bind,source=$supervisor,target=/ouster-stack.sh,readonly" \
  -e "ROS_DOMAIN_ID=$domain" \
  -e "RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_zenoh_cpp}" \
  -e "OUSTER_POINT_CLOUD_TOPIC=$raw_topic" \
  -e "POINT_CLOUD_TOPIC=$adapted_topic" \
  -e "PP_OUSTER_INTENSITY_SOURCE=$source_channel" \
  -e "PP_OUSTER_INTENSITY_DIVISOR=$divisor" \
  -e "DETECTIONS_TOPIC=${DETECTIONS_TOPIC:-/bbox}" \
  -e "PP_CONFIDENCE_THRESHOLD=${PP_CONFIDENCE_THRESHOLD:-0.4}" \
  -e "PP_GPU_INDEX=${PP_GPU_INDEX:-0}" \
  -e "PP_WORKSPACE_MIB=${PP_WORKSPACE_MIB:-512}" \
  -v "$volume:/var/lib/pp_infer" "$image" bash /ouster-stack.sh
