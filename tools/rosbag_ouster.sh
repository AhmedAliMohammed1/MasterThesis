#!/usr/bin/env bash
# Separate non-KITTI Ouster player; does not start or modify inference.
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mode=${1:-start}
case "$mode" in
  start|prepare|info|stop|videos) ;;
  help|--help|-h)
    cat <<'EOF'
Usage: bash tools/rosbag_ouster.sh [start|prepare|info|stop|videos]
  prepare  Download/checksum/extract both Ouster bags; inspect every cloud.
  info     Inspect the selected prepared bag without downloading.
  start    Prepare if necessary, then play only its LiDAR clouds in Docker (default).
  stop     Stop only the Ouster player owned by this helper.
  videos   Export both camera recordings as MP4 previews with bag-record timing.
Settings:
  PP_OUSTER_DIR       default: <project>/.recovery/rosbags/ouster_calibration_v3
  PP_OUSTER_SEQUENCE  bag folder name (see inventory.json); default: first sequence
  PP_OUSTER_FEATURE   default: raw_signal; opt-in controls: signal_div65535,
                      reflectivity_div255, reflectivity_fraction
  PP_OUSTER_CONTAINER default: pointpillars-ouster-bag
  PP_OUSTER_CAMERA    default: 0; set 1 to publish /image and /camera_info too
  PP_OUSTER_RAW_VIEW  default: 0; set 1 to publish original /ouster/raw_points
                      alongside normalized inference; includes camera topics
  PP_DEMO_TOOLS_IMAGE default: pp-infer:demo-tools (FFmpeg video encoder fallback)
  PP_IMAGE            default: pp-infer:jazzy-trt10
  PP_BAG_RATE         default: 0.5
  PP_BAG_LOOP         default: 1 (0 plays once)
  PP_BAG_DURATION     default: -1 (all); positive seconds for a short test
  PP_BAG_DELAY        default: 2 (seconds for subscriber discovery before playback)
  ROS_DOMAIN_ID       default: 0; must match inference and RViz
  POINT_CLOUD_TOPIC   default: /point_cloud
Needs host ROS Jazzy Python packages for preparation; Docker for playback.
raw_signal preserves original XYZI. Explicit feature controls change only the
fourth input feature in a derived cloud-only bag. XYZ/count/order/timestamps stay
unchanged. No confidence tuning or pillar-capacity filtering is installed.
Run tools/deploy.sh separately for inference. See docs/OUSTER_ROSBAG_DEMO.md
for sensor frame, RViz and existing-player instructions.
EOF
    exit 0 ;;
  *) echo 'Unknown mode; use --help.' >&2; exit 1 ;;
esac
[[ $# -le 1 ]] || { echo 'Pass one mode only.' >&2; exit 1; }
image=${PP_IMAGE:-pp-infer:jazzy-trt10}
container=${PP_OUSTER_CONTAINER:-pointpillars-ouster-bag}
owner_key=ouster-calibration-v3
rate=${PP_BAG_RATE:-0.5}
loop=${PP_BAG_LOOP:-1}
duration=${PP_BAG_DURATION:--1}
delay=${PP_BAG_DELAY:-2}
domain=${ROS_DOMAIN_ID:-0}
topic=${POINT_CLOUD_TOPIC:-/point_cloud}
feature=${PP_OUSTER_FEATURE:-raw_signal}
camera=${PP_OUSTER_CAMERA:-0}
raw_view=${PP_OUSTER_RAW_VIEW:-0}
[[ $camera == 0 || $camera == 1 ]] || { echo 'PP_OUSTER_CAMERA must be 0 or 1.' >&2; exit 1; }
[[ $raw_view == 0 || $raw_view == 1 ]] || { echo 'PP_OUSTER_RAW_VIEW must be 0 or 1.' >&2; exit 1; }
[[ $raw_view == 0 ]] || camera=1
case "$feature" in
  raw_signal|signal_div65535|reflectivity_div255|reflectivity_fraction) ;;
  *) echo 'Unknown PP_OUSTER_FEATURE; use --help.' >&2; exit 1 ;;
esac
if [[ $raw_view == 1 && $feature == raw_signal ]]; then
  echo 'Raw-view comparison requires an explicit normalized feature; raw_signal already publishes original /point_cloud.' >&2
  exit 1
fi
[[ $rate =~ ^[0-9]+([.][0-9]+)?$ && ${rate//[.0]/} != '' ]] || { echo 'PP_BAG_RATE must be positive.' >&2; exit 1; }
[[ $loop == 0 || $loop == 1 ]] || { echo 'PP_BAG_LOOP must be 0 or 1.' >&2; exit 1; }
[[ $duration == -1 || ( $duration =~ ^[0-9]+([.][0-9]+)?$ && ${duration//[.0]/} != '' ) ]] || { echo 'PP_BAG_DURATION must be -1 or positive.' >&2; exit 1; }
[[ $delay =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo 'PP_BAG_DELAY must be nonnegative.' >&2; exit 1; }
[[ $domain =~ ^[0-9]{1,3}$ && $((10#$domain)) -le 232 ]] || { echo 'ROS_DOMAIN_ID must be 0..232.' >&2; exit 1; }
[[ $topic == /* && $topic != *[[:space:]]* ]] || { echo 'POINT_CLOUD_TOPIC must be absolute.' >&2; exit 1; }
get_docker() {
  command -v docker >/dev/null || { echo 'Docker is required for playback.' >&2; exit 1; }
  docker_cmd=(docker)
  if ! docker info >/dev/null 2>&1; then
    command -v sudo >/dev/null || { echo 'Docker permission denied.' >&2; exit 1; }
    docker_cmd=(sudo docker)
    "${docker_cmd[@]}" info >/dev/null
  fi
}
if [[ $mode == stop ]]; then
  get_docker
  owner=$("${docker_cmd[@]}" inspect "$container" --format '{{index .Config.Labels "pp_infer.demo"}}' 2>/dev/null || true)
  [[ $owner == "$owner_key" ]] || { echo "Refusing to stop '$container': not owned by this helper." >&2; exit 1; }
  exec "${docker_cmd[@]}" stop "$container"
fi
data_dir=${PP_OUSTER_DIR:-"$project_dir/.recovery/rosbags/ouster_calibration_v3"}
mkdir -p "$data_dir"
data_dir=$(cd -- "$data_dir" && pwd)
[[ $data_dir != "$project_dir" && $project_dir != "$data_dir/"* && $data_dir != *,* ]] || {
  echo 'Choose a dedicated data folder, not the checkout or its ancestor; no commas.' >&2; exit 1;
}
[[ -f /opt/ros/jazzy/setup.bash ]] || { echo 'Preparation requires host ROS Jazzy.' >&2; exit 1; }
set +u
source /opt/ros/jazzy/setup.bash
set -u
exec 9>"$data_dir/.prepare.lock"
flock 9
if [[ $mode != info ]]; then
  python3 "$project_dir/tools/prepare_ouster_demo.py" --data-dir "$data_dir"
fi
[[ -f "$data_dir/inventory.json" ]] || { echo 'Run prepare first.' >&2; exit 1; }
if [[ $mode == videos ]]; then
  python3 "$project_dir/tools/export_ouster_camera.py" --data-dir "$data_dir" \
    --encoder-image "${PP_DEMO_TOOLS_IMAGE:-pp-infer:demo-tools}"
  exit 0
fi
bag_name=$(python3 - "$data_dir/inventory.json" "${PP_OUSTER_SEQUENCE:-}" <<'PY'
import json,sys
inventory=json.load(open(sys.argv[1]))
bags=inventory['bags']
name=sys.argv[2] or bags[0]['bag']
match=[bag for bag in bags if bag['bag']==name]
if len(match)!=1:
    raise SystemExit('Unknown sequence; choose: '+', '.join(bag['bag'] for bag in bags))
if match[0]['oversized_clouds']:
    raise SystemExit('Clouds exceed engine point capacity; original data preserved, no automatic sampling')
print(name)
PY
)
bag_dir="$data_dir/ouster/$bag_name"
if [[ $feature != raw_signal ]]; then
  python3 "$project_dir/tools/prepare_ouster_variant.py" --data-dir "$data_dir" \
    --sequence "$bag_name" --variant "$feature"
  bag_dir="$data_dir/derived/$feature/$bag_name"
fi
if [[ $camera == 1 && $feature != raw_signal ]]; then
  python3 "$project_dir/tools/prepare_ouster_visual.py" --data-dir "$data_dir" \
    --sequence "$bag_name" --feature "$feature"
  bag_dir="$data_dir/visual/$feature/$bag_name"
fi
if [[ $raw_view == 1 && $feature != raw_signal ]]; then
  python3 "$project_dir/tools/prepare_ouster_raw_view.py" --data-dir "$data_dir" \
    --sequence "$bag_name" --feature "$feature"
  bag_dir="$data_dir/raw_view/$feature/$bag_name"
fi
qos_file="$data_dir/playback_qos.yaml"
if [[ $camera == 1 ]]; then
  qos_file="$data_dir/visual_playback_qos.yaml"
  python3 - "$qos_file" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_text(''.join(topic+':\n  reliability: reliable\n  durability: volatile\n  history: keep_last\n  depth: 5\n' for topic in ('/points','/ouster/raw_points','/image','/camera_info')))
PY
fi
flock -u 9
exec 9>&-
[[ $mode != prepare ]] || { echo "Prepared: $data_dir/inventory.json"; exit 0; }
get_docker
"${docker_cmd[@]}" image inspect "$image" >/dev/null 2>&1 || { echo "Missing image '$image'; build with tools/deploy.sh." >&2; exit 1; }
if [[ $mode == info ]]; then
  exec "${docker_cmd[@]}" run --rm --mount "type=bind,src=$bag_dir,dst=/bag,readonly" "$image" ros2 bag info /bag
fi
# Preserve all existing containers and prevent duplicate input from known project players.
if "${docker_cmd[@]}" container inspect "$container" >/dev/null 2>&1; then
  echo "Container '$container' already exists; use this helper's stop command before retrying." >&2
  exit 1
fi
for player in $("${docker_cmd[@]}" ps --filter label=pp_infer.demo --format '{{.Names}}'); do
  player_env=$("${docker_cmd[@]}" inspect "$player" --format '{{range .Config.Env}}{{println .}}{{end}}')
  player_cmd=$("${docker_cmd[@]}" inspect "$player" --format '{{join .Config.Cmd " "}}')
  if [[ $'\n'"$player_env"$'\n' == *$'\n'"ROS_DOMAIN_ID=$domain"$'\n'* &&
        " $player_cmd " == *":=$topic "* ]]; then
    echo "Player '$player' already feeds $topic in domain $domain. Stop it deliberately or use a different domain/topic." >&2
    exit 1
  fi
done
loop_args=()
[[ $loop == 0 ]] || loop_args=(--loop)
topics=(/points)
[[ $camera == 0 ]] || topics+=(/image /camera_info)
[[ $raw_view == 0 || $feature == raw_signal ]] || topics+=(/ouster/raw_points)
printf 'Ouster: %s, feature %s, playback rate %s, domain %s, output %s. Ctrl+C stops playback.\n' "$bag_name" "$feature" "$rate" "$domain" "$topic"
exec "${docker_cmd[@]}" run --rm --init --name "$container" \
  --label "pp_infer.demo=$owner_key" --network host --ipc host \
  -e "ROS_DOMAIN_ID=$domain" -e FASTDDS_BUILTIN_TRANSPORTS=UDPv4 \
  --mount "type=bind,src=$bag_dir,dst=/bag,readonly" \
  --mount "type=bind,src=$qos_file,dst=/qos.yaml,readonly" \
  "$image" ros2 bag play /bag --topics "${topics[@]}" "${loop_args[@]}" \
  --rate "$rate" --delay "$delay" --playback-duration "$duration" \
  --qos-profile-overrides-path /qos.yaml --remap "/points:=$topic"
