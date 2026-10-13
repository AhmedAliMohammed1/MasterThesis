#!/usr/bin/env bash
# Full-cloud official KITTI city recording with forward-facing camera.
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mode=${1:-start}
case "$mode" in
 start|prepare|info|stop) ;;
 help|--help|-h)
  cat <<'EOF'
Usage: bash tools/rosbag_kitti_front.sh [start|prepare|info|stop]
Official synced drive 2011_09_26_drive_0005: forward-facing left color camera,
full 360-degree Velodyne HDL-64E scans, source calibration. No point crop/sampling.
 prepare  Download/verify archives, create ROS 2 bag and front-camera video.
 info     Inspect prepared bag without downloading.
 start    Prepare if necessary and play clouds, image and camera_info (default).
 stop     Stop only this helper's player.
Settings: PP_KITTI_FRONT_DIR, PP_KITTI_FRONT_CONTAINER, PP_IMAGE,
          PP_DEMO_TOOLS_IMAGE, PP_BAG_RATE (0.5), PP_BAG_LOOP (1),
          PP_BAG_DURATION (-1), PP_BAG_DELAY (2), ROS_DOMAIN_ID (0),
          POINT_CLOUD_TOPIC (/point_cloud).
Inference is started separately; use rviz/kitti_front.rviz for visualization.
EOF
  exit 0 ;;
 *) echo 'Unknown mode; use --help.' >&2; exit 1 ;;
esac
[[ $# -le 1 ]] || { echo 'Pass one mode.' >&2; exit 1; }
container=${PP_KITTI_FRONT_CONTAINER:-pointpillars-kitti-front-bag}
image=${PP_IMAGE:-pp-infer:jazzy-trt10}
rate=${PP_BAG_RATE:-0.5};loop=${PP_BAG_LOOP:-1};duration=${PP_BAG_DURATION:--1};delay=${PP_BAG_DELAY:-2}
domain=${ROS_DOMAIN_ID:-0};topic=${POINT_CLOUD_TOPIC:-/point_cloud}
[[ $rate =~ ^[0-9]+([.][0-9]+)?$ && ${rate//[.0]/} != '' ]] || { echo 'PP_BAG_RATE must be positive.' >&2; exit 1; }
[[ $loop == 0 || $loop == 1 ]] || { echo 'PP_BAG_LOOP must be 0 or 1.' >&2; exit 1; }
[[ $duration == -1 || ( $duration =~ ^[0-9]+([.][0-9]+)?$ && ${duration//[.0]/} != '' ) ]] || { echo 'PP_BAG_DURATION must be -1 or positive.' >&2; exit 1; }
[[ $delay =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo 'PP_BAG_DELAY must be nonnegative.' >&2; exit 1; }
[[ $domain =~ ^[0-9]{1,3}$ && $((10#$domain)) -le 232 ]] || { echo 'ROS_DOMAIN_ID must be 0..232.' >&2; exit 1; }
[[ $topic == /* && $topic != *[[:space:]]* ]] || { echo 'POINT_CLOUD_TOPIC must be absolute.' >&2; exit 1; }
get_docker() {
 docker_cmd=(docker)
 if ! docker info >/dev/null 2>&1; then docker_cmd=(sudo docker);"${docker_cmd[@]}" info >/dev/null;fi
}
if [[ $mode == stop ]]; then
 get_docker
 owner=$("${docker_cmd[@]}" inspect "$container" --format '{{index .Config.Labels "pp_infer.demo"}}' 2>/dev/null || true)
 [[ $owner == kitti-front-0005 ]] || { echo "Refusing to stop '$container': unowned." >&2;exit 1; }
 exec "${docker_cmd[@]}" stop "$container"
fi
root=${PP_KITTI_FRONT_DIR:-"$project_dir/.recovery/rosbags/kitti_front_0005"}
mkdir -p "$root";root=$(cd -- "$root" && pwd)
[[ $root != "$project_dir" && $project_dir != "$root/"* && $root != *,* ]] || { echo 'Choose a dedicated asset folder.' >&2;exit 1; }
[[ -f /opt/ros/jazzy/setup.bash ]] || { echo 'Preparation requires host ROS Jazzy.' >&2;exit 1; }
set +u
source /opt/ros/jazzy/setup.bash
set -u
if [[ $mode != info ]]; then
 python3 "$project_dir/tools/prepare_kitti_front.py" --data-dir "$root" --encoder-image "${PP_DEMO_TOOLS_IMAGE:-pp-infer:demo-tools}"
fi
[[ -f "$root/manifest.json" ]] || { echo 'Run prepare first.' >&2;exit 1; }
[[ $mode != prepare ]] || exit 0
get_docker
"${docker_cmd[@]}" image inspect "$image" >/dev/null
if [[ $mode == info ]]; then
 exec "${docker_cmd[@]}" run --rm --mount "type=bind,src=$root/rosbag,dst=/bag,readonly" "$image" ros2 bag info /bag
fi
if "${docker_cmd[@]}" inspect "$container" >/dev/null 2>&1; then echo "Container '$container' exists; stop it first." >&2;exit 1;fi
for player in $("${docker_cmd[@]}" ps --filter label=pp_infer.demo --format '{{.Names}}');do
 envs=$("${docker_cmd[@]}" inspect "$player" --format '{{range .Config.Env}}{{println .}}{{end}}')
 cmd=$("${docker_cmd[@]}" inspect "$player" --format '{{join .Config.Cmd " "}}')
 if [[ $'\n'"$envs"$'\n' == *$'\n'"ROS_DOMAIN_ID=$domain"$'\n'* && " $cmd " == *":=$topic "* ]];then
  echo "Player '$player' already feeds $topic in domain $domain; stop it deliberately or choose another domain." >&2;exit 1
 fi
done
python3 - "$root/playback_qos.yaml" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_text(''.join(t+':\n  reliability: reliable\n  durability: volatile\n  history: keep_last\n  depth: 5\n' for t in ('/point_cloud','/image','/camera_info')))
PY
loop_args=();[[ $loop == 0 ]] || loop_args=(--loop)
exec "${docker_cmd[@]}" run --rm --init --name "$container" --label pp_infer.demo=kitti-front-0005 --network host --ipc host \
 -e "ROS_DOMAIN_ID=$domain" -e FASTDDS_BUILTIN_TRANSPORTS=UDPv4 \
 --mount "type=bind,src=$root/rosbag,dst=/bag,readonly" --mount "type=bind,src=$root/playback_qos.yaml,dst=/qos.yaml,readonly" \
 "$image" ros2 bag play /bag --topics /point_cloud /image /camera_info "${loop_args[@]}" --rate "$rate" --delay "$delay" \
 --playback-duration "$duration" --qos-profile-overrides-path /qos.yaml --remap "/point_cloud:=$topic"
