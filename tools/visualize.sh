#!/usr/bin/env bash
# Host desktop viewer; inference and bag playback stay in their containers.
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ! -f /opt/ros/jazzy/setup.bash || ! -x /opt/ros/jazzy/bin/rviz2 ]]; then
  printf '%s\n' 'Install host ROS Jazzy (see the guide), then:' \
    'sudo apt install ros-jazzy-rviz2 ros-jazzy-vision-msgs-rviz-plugins' >&2
  exit 1
fi
if [[ -z ${DISPLAY:-} && -z ${WAYLAND_DISPLAY:-} ]]; then
  printf '%s\n' 'Run this viewer in a terminal on a graphical desktop.' >&2
  exit 1
fi
# ROS setup scripts are not safe with Bash nounset enabled.
set +u
source /opt/ros/jazzy/setup.bash
set -u
if ! ros2 pkg prefix vision_msgs_rviz_plugins >/dev/null 2>&1; then
  plugin_root="$project_dir/.recovery/rviz/plugin"
  plugin_prefix="$plugin_root/opt/ros/jazzy"
  if [[ ! -f "$plugin_prefix/lib/libvision_msgs_rviz_plugins.so" ]]; then
    for utility in apt-cache apt-get dpkg-deb; do
      command -v "$utility" >/dev/null || { echo "Missing $utility" >&2; exit 1; }
    done
    # Download through the host's configured signed ROS apt index, without sudo.
    plugin_version=$(apt-cache policy ros-jazzy-vision-msgs-rviz-plugins | \
      awk '/Candidate:/ {print $2; exit}')
    if [[ -z $plugin_version || $plugin_version == '(none)' ]]; then
      echo 'No Jazzy RViz plugin in the apt index; configure the ROS repository and run sudo apt update.' >&2
      exit 1
    fi
    downloads="$project_dir/.recovery/rviz/downloads"
    mkdir -p "$downloads"
    (
      cd "$downloads"
      apt-get download "ros-jazzy-vision-msgs-rviz-plugins=$plugin_version"
    )
    package="$downloads/ros-jazzy-vision-msgs-rviz-plugins_${plugin_version}_$(dpkg --print-architecture).deb"
    temporary=$(mktemp -d "$project_dir/.recovery/rviz/plugin.XXXXXX")
    trap 'rm -rf -- "$temporary"' EXIT
    dpkg-deb --extract "$package" "$temporary"
    test -f "$temporary/opt/ros/jazzy/lib/libvision_msgs_rviz_plugins.so"
    if [[ -e $plugin_root ]]; then
      echo "Incomplete plugin directory: $plugin_root. Inspect it before retrying." >&2
      exit 1
    fi
    mv -- "$temporary" "$plugin_root"
    trap - EXIT
  fi
  export AMENT_PREFIX_PATH="$plugin_prefix${AMENT_PREFIX_PATH:+:$AMENT_PREFIX_PATH}"
  export LD_LIBRARY_PATH="$plugin_prefix/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  missing_libraries=$(ldd "$plugin_prefix/lib/libvision_msgs_rviz_plugins.so" | \
    awk '/not found/ {print $1}')
  if [[ -n $missing_libraries ]]; then
    printf 'Missing plugin dependencies: %s\n' "$missing_libraries" >&2
    echo 'Install dependencies with sudo apt install ros-jazzy-vision-msgs-rviz-plugins.' >&2
    exit 1
  fi
fi
# Avoid shared-memory ownership conflicts between root containers and host users.
# Applies to Fast DDS; preserve an explicit transport choice from the caller.
export FASTDDS_BUILTIN_TRANSPORTS=${FASTDDS_BUILTIN_TRANSPORTS:-UDPv4}
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}
cd "$project_dir"
rviz_config=${RVIZ_CONFIG:-"$project_dir/rviz/pointpillars.rviz"}
printf 'RViz: domain %s, fixed frame velodyne; configuration %s.\n' "$ROS_DOMAIN_ID" "$rviz_config"
exec rviz2 -d "$rviz_config" "$@"
