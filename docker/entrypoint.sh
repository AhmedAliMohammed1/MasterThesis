#!/usr/bin/env bash
set -euo pipefail
# ROS-generated setup scripts expect some variables to be unset.
set +u
source /opt/ros/jazzy/setup.bash
source /workspace/install/setup.bash
set -u
if [[ ${1:-} != run ]]; then exec "$@"; fi
shift
mkdir -p /var/lib/pp_infer
model=/opt/models/pointpillars.onnx
model_hash=$(sha256sum "$model" | cut -d' ' -f1)
# Remap the chosen visible GPU to CUDA device 0 for every process.
export CUDA_VISIBLE_DEVICES="${PP_GPU_INDEX:-${CUDA_VISIBLE_DEVICES:-0}}"
gpu_identity=$(/workspace/install/pp_infer/lib/pp_infer/pp_device_info)
printf '%s\n' "$gpu_identity"
# The installed NVIDIA driver version is host-wide; do not assume NVML GPU 0
# corresponds to CUDA's selected visible device.
driver_identity=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | sort -u)
workspace_mib="${PP_WORKSPACE_MIB:-512}"
[[ "$workspace_mib" =~ ^[1-9][0-9]*$ ]] || { echo "PP_WORKSPACE_MIB must be a positive integer" >&2; exit 2; }
recipe="TensorRT-10.16.1.11-fp32-noTF32-batch1-workspace=$workspace_mib"
cache_key=$(printf '%s\n' "$model_hash" "$gpu_identity" "$driver_identity" "$recipe" | sha256sum | cut -d' ' -f1)
engine="/var/lib/pp_infer/$cache_key.engine"
# Serializes engine creation when containers share the same cache volume.
exec 9>"$engine.lock"
flock 9
if [[ ! -s "$engine" ]]; then
  pending="$engine.pending.$$"
  builder_pid=''
  cleanup_builder() {
    if [[ -n $builder_pid ]]; then
      kill -TERM "$builder_pid" 2>/dev/null || true
      wait "$builder_pid" 2>/dev/null || true
    fi
    rm -f -- "$pending"
  }
  trap cleanup_builder EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trtexec --onnx="$model" --minShapes=points:1x204800x4,num_points:1 \
    --optShapes=points:1x204800x4,num_points:1 --maxShapes=points:1x204800x4,num_points:1 \
    --saveEngine="$pending" --device=0 --memPoolSize="workspace:$workspace_mib" --noTF32 --skipInference &
  builder_pid=$!
  wait "$builder_pid"
  builder_pid=''
  mv "$pending" "$engine"
  trap - EXIT INT TERM
fi
flock -u 9
exec 9>&-
threshold_args=()
if [[ -n ${PP_CONFIDENCE_THRESHOLD:-} ]]; then
  threshold_args=(-p "confidence_threshold:=$PP_CONFIDENCE_THRESHOLD")
fi
exec /workspace/install/pp_infer/lib/pp_infer/pp_infer --ros-args --params-file /opt/pp_infer/node.yaml \
  -p "engine_path:=$engine" -r "__node:=pointpillars" \
  "${threshold_args[@]}" \
  -r "/point_cloud:=${POINT_CLOUD_TOPIC:-/point_cloud}" -r "bbox:=${DETECTIONS_TOPIC:-/bbox}" "$@"
