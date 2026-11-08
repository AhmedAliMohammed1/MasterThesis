#!/usr/bin/env bash
# Build changed runtime inputs with cached dependencies, then start inference.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "$project_root/tools/docker_foreground.sh"
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  cat <<'HELP'
Usage: sudo bash tools/deploy.sh [docker build options]

Checks the host GPU/Docker first. Builds from this checkout by default; no push
is needed. Reuses a matching saved image, otherwise uses Docker layer cache.
Source edits do not invalidate independent SDK/model dependency stages.
Starts the detector after building unless PP_BUILD_ONLY=1.

  PP_BUILD_ONLY=1       Build/check image, do not start a container
  PP_FORCE_BUILD=1      Run a cached build even when runtime inputs match
  PP_PULL_BASE=1        Refresh base images (can reinstall dependencies)
  PP_SOURCE_MODE=remote Use published Git source instead of the checkout
  PP_GIT_REPO / PP_GIT_REF  Remote source selection (also selects remote mode)

Repeat runs: tools/start.sh, or tools/start_ouster.sh bag for the fresh bag.
No host NVIDIA drivers are installed or upgraded by these scripts.
HELP
  exit 0
fi
image=${PP_IMAGE:-pp-infer:jazzy-trt10}
container=${PP_CONTAINER_NAME:-pointpillars}
volume=${PP_ENGINE_VOLUME:-pp-engines}
pull=${PP_PULL_BASE:-0}
force=${PP_FORCE_BUILD:-0}
build_only=${PP_BUILD_ONLY:-0}
for value in "$pull" "$force" "$build_only"; do
  [[ $value == 0 || $value == 1 ]] || { echo 'Build switches must be 0 or 1; use --help.' >&2; exit 2; }
done
mode=${PP_SOURCE_MODE:-local}
if [[ -z ${PP_SOURCE_MODE:-} && ( -n ${PP_GIT_REF:-} || -n ${PP_GIT_REPO:-} ) ]]; then mode=remote; fi
[[ $mode == local || $mode == remote ]] || { echo 'PP_SOURCE_MODE must be local or remote.' >&2; exit 2; }
command -v nvidia-smi >/dev/null || { echo 'NVIDIA driver is missing. Install/repair the host driver before deployment.' >&2; exit 1; }
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader || {
  echo 'Host NVIDIA driver check failed. Repair it before building.' >&2; exit 1;
}
command -v docker >/dev/null || { echo 'Install Docker and NVIDIA Container Toolkit first.' >&2; exit 1; }
docker info >/dev/null
if [[ $build_only == 0 ]] && docker container inspect "$container" >/dev/null 2>&1; then
  echo "Container '$container' already exists. Stop/remove the intended instance or set PP_CONTAINER_NAME." >&2
  exit 1
fi
cd "$project_root"
# Hash only image inputs; docs, downloaded bags and model assets are excluded.
fingerprint=$(
  {
    printf 'build-options\0'
    if [[ $# -gt 0 ]]; then printf '%s\0' "$@"; fi
    sha256sum -- Dockerfile .dockerignore CMakeLists.txt package.xml LICENSE docker/node.yaml docker/entrypoint.sh
    find src include tests/core tests/runtime tests/ros -type f \
      ! -name '*.pyc' ! -name '.env*' ! -name '*.pem' ! -name '*.key' -print0 | \
      LC_ALL=C sort -z | xargs -0 -r sha256sum --
    find launch -maxdepth 1 -type f -name '*.py' -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum --
  } | sha256sum | cut -d' ' -f1
)
cached=$(docker image inspect "$image" --format '{{index .Config.Labels "pp_infer.build-input-sha256"}}' 2>/dev/null || true)
if [[ $mode == local && $cached == "$fingerprint" && $pull == 0 && $force == 0 && $# == 0 ]]; then
  echo "Runtime build inputs unchanged; reusing $image. No downloads or installation."
else
  revision=$(git rev-parse HEAD 2>/dev/null || printf 'unversioned')
  revision="$revision+inputs-$fingerprint"
  echo "Building $image from $mode source; cached dependency/model layers are reused when available."
  docker build "--pull=$([[ $pull == 1 ]] && echo true || echo false)" --tag "$image" \
    --label "pp_infer.build-input-sha256=$([[ $mode == local ]] && echo "$fingerprint" || echo remote)" \
    --build-arg "SOURCE_MODE=$mode" --build-arg "SOURCE_REVISION=$revision" \
    --build-arg "GIT_REPO=${PP_GIT_REPO:-https://github.com/AhmedAliMohammed1/MasterThesis.git}" \
    --build-arg "GIT_REF=${PP_GIT_REF:-main}" "$@" "$project_root"
fi
[[ $build_only == 0 ]] || { echo "Image ready: $image"; exit 0; }
pp_run_container --pull=never --rm --init --name "$container" \
  --gpus all --network host --ipc host \
  -e "ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}" \
  -e "RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}" \
  -e "POINT_CLOUD_TOPIC=${POINT_CLOUD_TOPIC:-/point_cloud}" \
  -e "DETECTIONS_TOPIC=${DETECTIONS_TOPIC:-/bbox}" \
  -e "PP_CONFIDENCE_THRESHOLD=${PP_CONFIDENCE_THRESHOLD:-0.4}" \
  -e "PP_GPU_INDEX=${PP_GPU_INDEX:-0}" \
  -e "PP_WORKSPACE_MIB=${PP_WORKSPACE_MIB:-512}" \
  -v "$volume:/var/lib/pp_infer" "$image"
