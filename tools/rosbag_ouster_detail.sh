#!/usr/bin/env bash
# Original sensor visualization plus the previously tested normalized inference input.
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export PP_OUSTER_FEATURE=${PP_OUSTER_FEATURE:-reflectivity_div255}
export PP_OUSTER_CAMERA=1
export PP_OUSTER_RAW_VIEW=1
exec bash "$project_dir/tools/rosbag_ouster.sh" "$@"
