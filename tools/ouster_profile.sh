#!/usr/bin/env bash
# Shared defaults; preserve explicit overrides in either launcher.
pp_ouster_profile() {
  case "$1" in
    bag)
      export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-99}
      export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
      export OUSTER_POINT_CLOUD_TOPIC=${OUSTER_POINT_CLOUD_TOPIC:-/sensing/lidar/points}
      ;;
    live)
      export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}
      export RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_zenoh_cpp}
      export OUSTER_POINT_CLOUD_TOPIC=${OUSTER_POINT_CLOUD_TOPIC:-/ouster1/points}
      ;;
    *) echo 'Ouster profile must be bag or live.' >&2; return 2 ;;
  esac
  export PP_IMAGE=${PP_IMAGE:-pp-infer:jazzy-trt10}
}
