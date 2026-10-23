#!/usr/bin/env bash
# Read published counters/current threshold, or open the existing RViz count view.
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mode=${1:-watch}
case "$mode" in
  help|--help|-h)
    cat <<'EOF'
Usage: bash tools/monitor_detections.sh [watch|once|threshold|rviz]
  watch      Stream detection statistics (default); Ctrl+C stops monitoring.
  once       Print the latest retained statistics; wait at most 10 seconds.
  threshold  Read the node's current confidence_threshold; does not change it.
  rviz       Open points, accepted boxes and the latest-scan count label.

Statistics show post-NMS boxes, removed boxes, published boxes, the threshold,
cumulative detection events and dropped-frame counts. Retained data may be old;
inspect the header timestamp. Totals count events, not unique tracked objects.

Settings (edit defaults below or supply environment variables):
  PP_MONITOR_BACKEND   auto (host ROS if installed), host, or docker
  DETECTIONS_TOPIC    /bbox; statistics are read from <topic>/stats
  PP_NODE_NAME        /pointpillars (use /minimal_publisher for unnamed native runs)
  PP_CONTAINER_NAME   pointpillars; used only by the docker backend
  PP_MONITOR_TIMEOUT  10 seconds for once/threshold
  ROS_DOMAIN_ID       match inference; docker inherits its container's domain
                      unless ROS_DOMAIN_ID is explicitly supplied here
  RVIZ_CONFIG         optional saved viewer configuration for rviz mode

Examples:
  bash tools/monitor_detections.sh once
  PP_MONITOR_BACKEND=docker bash tools/monitor_detections.sh watch
  ROS_DOMAIN_ID=42 DETECTIONS_TOPIC=/kitti/predictions bash tools/monitor_detections.sh
  RVIZ_CONFIG="$PWD/rviz/ouster.rviz" bash tools/monitor_detections.sh rviz

Inference must already use the updated executable/image. This helper does not
build/deploy inference, start playback, change thresholds, or reset counters.
EOF
    exit 0 ;;
  watch|once|threshold|rviz) ;;
  *) echo 'Unknown mode; use --help.' >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { echo 'Pass one mode; use --help.' >&2; exit 2; }

# Manual defaults: adjust these values, or override them through the environment.
backend=${PP_MONITOR_BACKEND:-auto}
topic=${DETECTIONS_TOPIC:-/bbox}
node=${PP_NODE_NAME:-/pointpillars}
container=${PP_CONTAINER_NAME:-pointpillars}
wait_seconds=${PP_MONITOR_TIMEOUT:-10}
[[ $topic =~ ^/([a-zA-Z_][a-zA-Z0-9_]*)(/[a-zA-Z_][a-zA-Z0-9_]*)*$ ]] || {
  echo 'DETECTIONS_TOPIC must be an absolute ROS topic, for example /bbox.' >&2; exit 2;
}
[[ $wait_seconds =~ ^[0-9]+([.][0-9]+)?$ && ${wait_seconds//[.0]/} != '' ]] || {
  echo 'PP_MONITOR_TIMEOUT must be positive seconds.' >&2; exit 2;
}
if [[ $mode == rviz ]]; then
  if [[ -z ${RVIZ_CONFIG:-} && $topic == /kitti/predictions ]]; then
    export RVIZ_CONFIG="$project_dir/rviz/kitti_validation.rviz"
  elif [[ -z ${RVIZ_CONFIG:-} && $topic != /bbox ]]; then
    echo 'Set RVIZ_CONFIG to a profile using your custom detection/count topics.' >&2; exit 2
  fi
  exec bash "$project_dir/tools/visualize.sh"
fi
case "$backend" in
  auto) if [[ -f /opt/ros/jazzy/setup.bash ]]; then backend=host; else backend=docker; fi ;;
  host|docker) ;;
  *) echo 'PP_MONITOR_BACKEND must be auto, host or docker.' >&2; exit 2 ;;
esac
if [[ $backend == host ]]; then
  [[ -f /opt/ros/jazzy/setup.bash ]] || { echo 'Host ROS Jazzy is missing; select PP_MONITOR_BACKEND=docker.' >&2; exit 1; }
  set +u
  source /opt/ros/jazzy/setup.bash
  set -u
  export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}
  export FASTDDS_BUILTIN_TRANSPORTS=${FASTDDS_BUILTIN_TRANSPORTS:-UDPv4}
  runner=(ros2)
else
  command -v docker >/dev/null || { echo 'Docker is missing; use a configured host ROS installation.' >&2; exit 1; }
  if ! running=$(docker inspect "$container" --format '{{.State.Running}}'); then
    echo 'Cannot inspect the container. Check its name and Docker permissions (use sudo if needed).' >&2; exit 1
  fi
  [[ $running == true ]] || { echo "Container '$container' is not running; start inference separately." >&2; exit 1; }
  runner=(docker exec)
  if [[ $mode == watch && -t 0 && -t 1 ]]; then runner+=(-it); fi
  if [[ -n ${ROS_DOMAIN_ID:-} ]]; then runner+=(-e "ROS_DOMAIN_ID=$ROS_DOMAIN_ID"); fi
  runner+=("$container" /entrypoint.sh)
  # Bound the ROS process inside the container, not just the Docker client.
  if [[ $mode != watch ]]; then runner+=(timeout --foreground "${wait_seconds}s"); fi
  runner+=(ros2)
fi

if [[ $mode == threshold ]]; then
  args=(param get "$node" confidence_threshold)
else
  args=(topic echo "$topic/stats" diagnostic_msgs/msg/DiagnosticArray --qos-durability transient_local)
  if [[ $mode == once ]]; then args+=(--once); fi
  echo "Reading $topic/stats via $backend. The updated inference node must already be running." >&2
fi
if [[ $mode == watch ]]; then exec "${runner[@]}" "${args[@]}"; fi
command -v timeout >/dev/null || { echo 'The timeout utility is required for bounded reads.' >&2; exit 1; }
bounded_runner=("${runner[@]}")
if [[ $backend == host ]]; then bounded_runner=(timeout --foreground "${wait_seconds}s" "${runner[@]}"); fi
if "${bounded_runner[@]}" "${args[@]}"; then
  exit 0
else
  code=$?
  if [[ $code == 124 ]]; then
    echo 'No response before the timeout. Check the updated node/image, topic, ROS domain and transport. No counters are assumed to be zero.' >&2
  fi
  exit "$code"
fi
