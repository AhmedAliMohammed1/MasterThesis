#!/usr/bin/env bash
# Download/prepare the tested KITTI bag and camera clip, then play LiDAR in Docker.
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mode=${1:-start}
case "$mode" in
  start|prepare|stop) ;;
  help|--help|-h)
    cat <<'EOF'
Usage: bash tools/rosbag_demo.sh [start|prepare|stop]
  start    Download/verify bag and camera clip; start looping LiDAR playback (default).
  prepare  Prepare assets without starting playback.
  stop     Stop only a playback container created and labeled by this script.
Settings: PP_DEMO_DIR, PP_IMAGE, PP_DEMO_TOOLS_IMAGE, PP_BAG_CONTAINER,
          PP_BAG_RATE (default 0.5), ROS_DOMAIN_ID, POINT_CLOUD_TOPIC.
The inference node is started separately with tools/deploy.sh; RViz with tools/visualize.sh.
The camera MP4 is scene context, not labeled ground truth or synchronized playback.
EOF
    exit 0 ;;
  *) echo "Unknown mode: $mode; use --help." >&2; exit 1 ;;
esac
[[ $# -le 1 ]] || { echo 'Pass only one mode; use environment settings for options.' >&2; exit 1; }
command -v docker >/dev/null || { echo 'Install Docker first; see README.' >&2; exit 1; }
docker_cmd=(docker)
if ! docker info >/dev/null 2>&1; then
  if [[ $(id -u) != 0 ]] && command -v sudo >/dev/null; then
    docker_cmd=(sudo docker)
    "${docker_cmd[@]}" info >/dev/null
  else
    echo 'Docker is unavailable; check the daemon and permissions.' >&2
    exit 1
  fi
fi
container=${PP_BAG_CONTAINER:-pointpillars-bag}
if [[ $mode == stop ]]; then
  owner=$("${docker_cmd[@]}" inspect "$container" --format '{{index .Config.Labels "pp_infer.demo"}}' 2>/dev/null || true)
  [[ $owner == kitti04 ]] || { echo "Refusing to stop '$container': not created by this helper." >&2; exit 1; }
  exec "${docker_cmd[@]}" stop "$container"
fi
image=${PP_IMAGE:-pp-infer:jazzy-trt10}
helper_image=${PP_DEMO_TOOLS_IMAGE:-pp-infer:demo-tools}
if [[ $mode == start ]]; then
  "${docker_cmd[@]}" image inspect "$image" >/dev/null 2>&1 || {
    echo "Build the inference image first with tools/deploy.sh (missing '$image')." >&2; exit 1;
  }
fi
rate=${PP_BAG_RATE:-0.5}
domain=${ROS_DOMAIN_ID:-0}
topic=${POINT_CLOUD_TOPIC:-/point_cloud}
[[ $rate =~ ^[0-9]+([.][0-9]+)?$ && ${rate//[.0]/} != '' ]] || {
  echo 'PP_BAG_RATE must be a positive number.' >&2; exit 1;
}
[[ $domain =~ ^[0-9]{1,3}$ && $((10#$domain)) -le 232 ]] || { echo 'ROS_DOMAIN_ID must be 0..232.' >&2; exit 1; }
[[ $topic == /* && $topic != *[[:space:]]* ]] || { echo 'POINT_CLOUD_TOPIC must be an absolute ROS topic.' >&2; exit 1; }
data_dir=${PP_DEMO_DIR:-$(dirname -- "$project_dir")/rosbags/kitti04}
mkdir -p "$data_dir"
data_dir=$(cd -- "$data_dir" && pwd)
[[ $data_dir != "$project_dir" && $project_dir != "$data_dir/"* ]] || {
  echo 'PP_DEMO_DIR must be a dedicated asset folder, not the checkout or its ancestor.' >&2; exit 1;
}
[[ $data_dir != *,* && $project_dir != *,* ]] || { echo 'Docker bind paths cannot contain commas.' >&2; exit 1; }
command -v flock >/dev/null || { echo 'Install util-linux for flock.' >&2; exit 1; }
exec 9>"$data_dir/.prepare.lock"
flock 9
if ! "${docker_cmd[@]}" image inspect "$helper_image" >/dev/null 2>&1; then
  "${docker_cmd[@]}" build --tag "$helper_image" - < "$project_dir/docker/demo-tools.Dockerfile"
fi
# Keep generated files owned by the person invoking the helper, including under sudo.
asset_uid=${SUDO_UID:-$(id -u)}
asset_gid=${SUDO_GID:-$(id -g)}
"${docker_cmd[@]}" run --rm --init --user "$asset_uid:$asset_gid" \
  --mount "type=bind,src=$data_dir,dst=/data" \
  --mount "type=bind,src=$project_dir/tools,dst=/tools,readonly" \
  "$helper_image" python3 /tools/prepare_kitti_demo.py --data-dir /data
flock -u 9
exec 9>&-
printf '\nCamera video: %s/kitti04_left_camera.mp4\n' "$data_dir"
[[ $mode == start ]] || exit 0
bag_dir="$data_dir/2011_09_30_drive_0016_extract_ros2"
if "${docker_cmd[@]}" container inspect "$container" >/dev/null 2>&1; then
  existing_bag=$("${docker_cmd[@]}" inspect "$container" --format '{{range .Mounts}}{{if eq .Destination "/bag"}}{{.Source}}{{end}}{{end}}')
  running=$("${docker_cmd[@]}" inspect "$container" --format '{{.State.Running}}')
  existing_cmd=$("${docker_cmd[@]}" inspect "$container" --format '{{join .Config.Cmd " "}}')
  existing_env=$("${docker_cmd[@]}" inspect "$container" --format '{{range .Config.Env}}{{println .}}{{end}}')
  if [[ $running == true && $existing_bag == "$bag_dir" &&
        " $existing_cmd " == *" --topics /velodyne_points "* &&
        " $existing_cmd " == *" --rate $rate "* &&
        " $existing_cmd " == *" --loop "* &&
        " $existing_cmd " == *" --remap /velodyne_points:=$topic "* &&
        $'\n'"$existing_env"$'\n' == *$'\n'"ROS_DOMAIN_ID=$domain"$'\n'* ]]; then
    echo "Matching playback already running in '$container'; no duplicate started."
    exit 0
  fi
  echo "Container '$container' already exists with a different/stopped setup; playback was not duplicated."
  echo 'Inspect and stop/remove the intended previous player before retrying.'
  exit 1
fi
"${docker_cmd[@]}" run --rm \
  --mount "type=bind,src=$bag_dir,dst=/bag,readonly" \
  "$image" ros2 bag info /bag
printf 'Starting looping LiDAR playback at rate %s, domain %s, topic %s. Ctrl+C stops it.\n' "$rate" "$domain" "$topic"
exec "${docker_cmd[@]}" run --rm --init --name "$container" \
  --label pp_infer.demo=kitti04 --network host --ipc host \
  -e "ROS_DOMAIN_ID=$domain" \
  --mount "type=bind,src=$bag_dir,dst=/bag,readonly" \
  --mount "type=bind,src=$data_dir/playback_qos.yaml,dst=/qos.yaml,readonly" \
  "$image" ros2 bag play /bag --topics /velodyne_points --loop \
  --rate "$rate" --qos-profile-overrides-path /qos.yaml \
  --remap "/velodyne_points:=$topic"
