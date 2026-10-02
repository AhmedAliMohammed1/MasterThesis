# Source this file from Bash; it exposes the extracted SDK without system installs.
pp_workspace_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
pp_sdk_root="$pp_workspace_root/.recovery/sdk/tensorrt-10.16.1/usr"
if [[ ! -f "$pp_sdk_root/include/x86_64-linux-gnu/NvInfer.h" ]]; then
  echo "Project-local TensorRT SDK is missing: $pp_sdk_root" >&2
  return 1
fi
export TENSORRT_ROOT="$pp_sdk_root"
export LD_LIBRARY_PATH="$pp_sdk_root/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONPATH="$pp_sdk_root/lib/python3.12/dist-packages${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$pp_sdk_root/bin:$PATH"
unset pp_workspace_root pp_sdk_root
