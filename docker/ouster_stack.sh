#!/usr/bin/env bash
# Invoked by the image's ROS-sourcing entrypoint. Own both process groups so
# adapter/inference failures, Docker stop and Ctrl+C also stop their descendants.
set -euo pipefail
[[ $# -eq 0 || $# -eq 2 ]] || { echo 'Expected zero arguments or adapter/entrypoint paths.' >&2; exit 2; }
adapter=${1:-/workspace/install/pp_infer/lib/pp_infer/ouster_adapter}
entrypoint=${2:-/entrypoint.sh}
children=()
cleanup() {
  trap - EXIT
  trap '' INT TERM
  local pid running
  for pid in "${children[@]}"; do kill -TERM -- "-$pid" 2>/dev/null || true; done
  # Let ROS shut down; then bound shutdown even if a builder/child is stuck.
  for ((attempt=0; attempt<50; ++attempt)); do
    running=0
    for pid in "${children[@]}"; do
      if kill -0 -- "-$pid" 2>/dev/null; then running=1; fi
    done
    [[ $running == 1 ]] || break
    sleep 0.1
  done
  for pid in "${children[@]}"; do kill -KILL -- "-$pid" 2>/dev/null || true; done
  for pid in "${children[@]}"; do wait "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
[[ -x $adapter && -x $entrypoint ]] || { echo 'Missing adapter or inference entrypoint.' >&2; exit 1; }
setsid "$adapter" --ros-args \
  -p "input_topic:=${OUSTER_POINT_CLOUD_TOPIC:-/ouster1/points}" \
  -p "output_topic:=${POINT_CLOUD_TOPIC:-/point_cloud}" \
  -p "intensity_source:=${PP_OUSTER_INTENSITY_SOURCE:-reflectivity}" \
  -p "intensity_divisor:=${PP_OUSTER_INTENSITY_DIVISOR:-255.0}" &
children+=("$!")
setsid "$entrypoint" run &
children+=("$!")
status=0
wait -n "${children[@]}" || status=$?
echo "An Ouster pipeline process exited (status $status); stopping the pipeline." >&2
[[ $status -ne 0 ]] || status=1
exit "$status"
