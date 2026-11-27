#!/usr/bin/env bash
# Replay primary experiment MCAPs or historical MOSEP bags without rewriting them.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "$project_root/tools/docker_foreground.sh"
source "$project_root/tools/ouster_profile.sh"
pp_ouster_profile bag
case "${1:-}" in
  -h|--help)
    cat <<'EOF'
Usage: sudo bash tools/start_ouster_bag.sh [raw01|ouster1|dry|rain30|rain100]

Play a primary experiment MCAP unchanged, using a read-only Docker mount.
raw01 (default) and ouster1 are the primary recordings; MOSEP choices are historical.
Starts only playback; start the adapter/detector and RViz separately.
Ctrl+C stops playback and removes its container. No download or build occurs.

Defaults:
  PP_IMAGE              pp-infer:jazzy-trt10 (same as start_ouster.sh bag)
  PP_OUSTER_CONTAINER   pointpillars-ouster-bag
  PP_ROSBAGS_DIR        <checkout>/../rosbags (primary recording root)
  PP_OUSTER_FRESH_DIR   <checkout>/.recovery/rosbags/ouster_mosep_fresh_20261107/original
                       (historical MOSEP choices only)
  ROS_DOMAIN_ID         99
  RMW_IMPLEMENTATION    rmw_fastrtps_cpp
  OUSTER_POINT_CLOUD_TOPIC /ouster1/points (adapter input)
  PP_BAG_RATE           0.5
  PP_BAG_LOOP           1 (set 0 to play once)
  PP_BAG_DELAY          3 seconds (0 starts without a delay)

Examples:
  sudo bash tools/start_ouster_bag.sh
  sudo bash tools/start_ouster_bag.sh ouster1
  sudo env PP_BAG_LOOP=0 PP_BAG_RATE=1 bash tools/start_ouster_bag.sh

Match the adapter's ROS domain, middleware and raw input topic. An existing
container is preserved; stop the intended old player before starting another.
EOF
    exit 0 ;;
esac
[[ $# -le 1 ]] || { echo 'Expected one recording choice at most; use --help.' >&2; exit 2; }
selection=${1:-raw01}
source_topic=/ouster1/points
storage_args=()
case "$selection" in
  raw01|ouster1)
    data_root=${PP_ROSBAGS_DIR:-"$(dirname -- "$project_root")/rosbags"}
    case "$selection" in
      raw01) filename=ouster1_raw_01_0-001.mcap ;;
      ouster1) filename=ouster1_raw_02_0-001.mcap ;;
    esac
    bag="$data_root/$selection"
    [[ -f "$bag/$filename" ]] || { echo "Missing primary MCAP: $bag/$filename" >&2; exit 1; }
    storage_args=(--storage mcap)
    ;;
  dry|rain30|rain100)
    case "$selection" in
      dry) sequence=digitrans_40kmh_dry ;;
      rain30) sequence=digitrans_40kmh_30mmh ;;
      rain100) sequence=digitrans_40kmh_100mmh ;;
    esac
    data_root=${PP_OUSTER_FRESH_DIR:-"$project_root/.recovery/rosbags/ouster_mosep_fresh_20261107/original"}
    bag="$data_root/$sequence"
    [[ -f "$bag/metadata.yaml" ]] || { echo "Missing original bag: $bag/metadata.yaml" >&2; exit 1; }
    shopt -s nullglob
    files=("$bag"/*.mcap)
    [[ ${#files[@]} -gt 0 ]] || { echo "No MCAP source file in $bag" >&2; exit 1; }
    source_topic=/sensing/lidar/points
    ;;
  *) echo 'Choose raw01, ouster1, dry, rain30 or rain100; use --help.' >&2; exit 2 ;;
esac
bag=$(cd -- "$bag" && pwd)
[[ $bag != *,* ]] || { echo 'The bag path must not contain commas (Docker mount syntax).' >&2; exit 2; }
rate=${PP_BAG_RATE:-0.5}
delay=${PP_BAG_DELAY:-3}
loop=${PP_BAG_LOOP:-1}
domain=${ROS_DOMAIN_ID:-99}
topic=${OUSTER_POINT_CLOUD_TOPIC:-/ouster1/points}
[[ $rate =~ ^[0-9]+([.][0-9]+)?$ && ${rate//[.0]/} != '' ]] || {
  echo 'PP_BAG_RATE must be a positive decimal number.' >&2; exit 2;
}
[[ $delay =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo 'PP_BAG_DELAY must be nonnegative.' >&2; exit 2; }
[[ $loop == 0 || $loop == 1 ]] || { echo 'PP_BAG_LOOP must be 0 or 1.' >&2; exit 2; }
[[ $domain =~ ^[0-9]{1,3}$ && $((10#$domain)) -le 232 ]] || { echo 'ROS_DOMAIN_ID must be 0..232.' >&2; exit 2; }
[[ $topic =~ ^/([a-zA-Z_][a-zA-Z0-9_]*)(/[a-zA-Z_][a-zA-Z0-9_]*)*$ ]] || {
  echo 'OUSTER_POINT_CLOUD_TOPIC must be an absolute ROS topic.' >&2; exit 2;
}
image=$PP_IMAGE
container=${PP_OUSTER_CONTAINER:-pointpillars-ouster-bag}
command -v docker >/dev/null || { echo 'Docker is required.' >&2; exit 1; }
docker info >/dev/null
if docker container inspect "$container" >/dev/null 2>&1; then
  echo "Container '$container' already exists. Playback was not restarted. Stop the intended player first." >&2
  exit 1
fi
if ! docker image inspect "$image" >/dev/null 2>&1; then
  echo "Missing local image '$image'. Set PP_IMAGE to your saved ROS inference image." >&2
  exit 1
fi
# ROS accepts only positive values for --delay; omit it for zero.
delay_args=()
[[ -z ${delay//[.0]/} ]] || delay_args=(--delay "$delay")
loop_args=()
[[ $loop == 0 ]] || loop_args=(--loop)
remap_args=()
[[ $topic == "$source_topic" ]] || remap_args=(--remap "$source_topic:=$topic")
bag_uri=/bag
if [[ $selection == raw01 || $selection == ouster1 ]]; then
  bag="$bag/$filename"
  bag_uri=/bag.mcap
fi
printf 'Original Ouster bag: %s\nOutput: %s; domain: %s; rate: %s; loop: %s. Ctrl+C stops playback.\n' \
  "$bag" "$topic" "$domain" "$rate" "$loop"
pp_run_container --pull=never --rm --init --name "$container" \
  --label "pp_infer.demo=ouster-$selection" --network host --ipc host \
  -e "ROS_DOMAIN_ID=$domain" \
  -e "RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}" \
  -e "FASTDDS_BUILTIN_TRANSPORTS=${FASTDDS_BUILTIN_TRANSPORTS:-UDPv4}" \
  --mount "type=bind,source=$bag,target=$bag_uri,readonly" \
  "$image" ros2 bag play "$bag_uri" "${storage_args[@]}" --topics "$source_topic" \
  --rate "$rate" "${loop_args[@]}" "${delay_args[@]}" --disable-keyboard-controls \
  "${remap_args[@]}"
