#!/usr/bin/env bash
# Labeled KITTI preparation, measured inference, live RViz and pinned devkit report.
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_dir"
mode=${1:-live}
dataset=${PP_KITTI_DATASET:-"$project_dir/../datasets/kitti_object_diagnostic_v1"}
output=${PP_KITTI_OUTPUT:-"$project_dir/.recovery/accuracy/kitti-baseline-v1"}
container=${PP_KITTI_CONTAINER:-pointpillars-validation}
image=${PP_IMAGE:-pp-infer:jazzy-trt10}
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-42}
export FASTDDS_BUILTIN_TRANSPORTS=${FASTDDS_BUILTIN_TRANSPORTS:-UDPv4}
if [[ $mode == prepare ]]; then
  exec python3 tools/prepare_kitti_validation.py --output "$dataset"
fi
if [[ $mode == report ]]; then
  exec python3 tools/kitti_evaluation.py --dataset "$dataset" --predictions "$output" --output "$output/evaluation"
fi
if [[ $mode == view ]]; then
  mkdir -p "$output"
  python3 - "$output" "$$" <<'PYOWNER'
import json,sys
from pathlib import Path
pid=int(sys.argv[2]);start=Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[19]
(Path(sys.argv[1])/'viewer-owner.json').write_text(json.dumps({'pid':pid,'start_ticks':start,'kind':'rviz2'})+'\n')
PYOWNER
  export RVIZ_CONFIG="$project_dir/rviz/kitti_validation.rviz"
  exec bash tools/visualize.sh
fi
if [[ $mode == stop ]]; then
  python3 - "$container" "$output" <<'PY'
import json,subprocess,sys,os,signal
from pathlib import Path
name,out=sys.argv[1:]; owner=Path(out)/'container-owner.json'
if not owner.exists():raise SystemExit('No helper ownership record; inspect the container and stop it explicitly if intended.')
info=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
if info['Id']!=json.loads(owner.read_text())['container_id']:raise SystemExit('Container identity changed; refusing to stop it.')
for filename in ('player-owner.json','viewer-owner.json'):
 path=Path(out)/filename
 if not path.exists():continue
 saved=json.loads(path.read_text());proc=Path('/proc')/str(saved['pid'])
 try:
  start=(proc/'stat').read_text().split(') ',1)[1].split()[19]
  command=(proc/'cmdline').read_bytes().split(b'\0')
 except FileNotFoundError:continue
 if start!=saved['start_ticks'] or not any(saved['kind'].encode() in arg for arg in command):
  raise SystemExit('Recorded process identity changed; refusing to signal it.')
 os.kill(saved['pid'],signal.SIGINT)
subprocess.run(['docker','stop',name],check=True)
PY
  exit
fi
if [[ $mode != live && $mode != collect ]]; then
  echo 'Usage: bash tools/kitti_accuracy.sh {prepare|collect|live|view|report|stop}' >&2
  exit 2
fi
[[ -f "$dataset/manifest.json" ]] || { echo 'Prepare labeled data first: bash tools/kitti_accuracy.sh prepare' >&2; exit 1; }
[[ -f /opt/ros/jazzy/setup.bash ]] || { echo 'Host ROS Jazzy with rclpy/vision_msgs/visualization_msgs is required for this player.' >&2; exit 1; }
mkdir -p "$output"
if ! docker container inspect "$container" >/dev/null 2>&1; then
  container_id=$(docker run -d --rm --init --name "$container" --gpus all --network host --ipc host \
    --label pp_infer.kitti_validation=1 \
    -e "ROS_DOMAIN_ID=$ROS_DOMAIN_ID" -e "FASTDDS_BUILTIN_TRANSPORTS=$FASTDDS_BUILTIN_TRANSPORTS" \
    -e POINT_CLOUD_TOPIC=/kitti/point_cloud -e DETECTIONS_TOPIC=/kitti/predictions \
    -v "${PP_ENGINE_VOLUME:-pp-engines}:/var/lib/pp_infer" "$image")
  python3 - "$output" "$container_id" <<'PY'
import json,sys
from pathlib import Path
(Path(sys.argv[1])/'container-owner.json').write_text(json.dumps({'container_id':sys.argv[2]})+'\n')
PY
fi
python3 - "$container" "$image" "$output" "$ROS_DOMAIN_ID" <<'PY'
import json,subprocess,sys
from pathlib import Path
name,image,out,domain=sys.argv[1:]
info=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
expected=json.loads(subprocess.check_output(['docker','image','inspect',image]))[0]['Id']
env=dict(s.split('=',1) for s in info['Config']['Env'])
for key,value in {'ROS_DOMAIN_ID':domain,'POINT_CLOUD_TOPIC':'/kitti/point_cloud','DETECTIONS_TOPIC':'/kitti/predictions','FASTDDS_BUILTIN_TRANSPORTS':'UDPv4'}.items():
 if env.get(key)!=value:raise SystemExit('Existing container settings differ: '+key)
if info['Image']!=expected or not info['State']['Running']:raise SystemExit('Existing container image/state differs; preserve and inspect it.')
model_hash=subprocess.check_output(['docker','exec',name,'sha256sum','/opt/models/pointpillars.onnx'],text=True).split()[0]
if model_hash!='2dcabddc3a365e9608a112d7bbbb7db769a6dddeeaa59aa03611a83113326da1':raise SystemExit('Image model hash differs from the validation contract.')
import re
config=subprocess.check_output(['docker','exec',name,'cat','/opt/pp_infer/node.yaml'],text=True)
for key,value in {'intensity_scale':'1.0','nms_iou_thresh':'0.01','pre_nms_top_n':'4096','data_type':'fp32'}.items():
 if not re.search(r'^\s*'+key+r':\s*'+re.escape(value)+r'\s*$',config,re.M):raise SystemExit('Image node parameter differs: '+key)
record={'image_id':info['Image'],'container':name,'domain':int(domain),
 'model_sha256':'2dcabddc3a365e9608a112d7bbbb7db769a6dddeeaa59aa03611a83113326da1',
 'parameters':{'intensity_scale':1.0,'nms_iou_thresh':0.01,'pre_nms_top_n':4096,'data_type':'fp32'},
 'source_revision':subprocess.check_output(['docker','exec',name,'cat','/opt/pp_infer/source-revision.txt'],text=True).strip(),
 'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=name,uuid,driver_version','--format=csv,noheader'],text=True).strip()}
path=Path(out)/'runtime.json'
if path.exists() and json.loads(path.read_text())!=record:raise SystemExit('Frozen runtime identity differs; use a new PP_KITTI_OUTPUT directory.')
if not path.exists():path.write_text(json.dumps(record,indent=2)+'\n')
PY
set +u
source /opt/ros/jazzy/setup.bash
set -u
exec 9>"$output/.collector.lock"
flock -n 9 || { echo 'An inference collector already holds this output folder.' >&2; exit 1; }
if ros2 node list --no-daemon 2>/dev/null | grep -qx '/kitti_validation_player'; then
  echo 'A KITTI player is already active in this domain; stop it before starting another.' >&2
  exit 1
fi
python3 - "$output" "$$" <<'PYOWNER'
import json,sys
from pathlib import Path
pid=int(sys.argv[2]);start=Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[19]
(Path(sys.argv[1])/'player-owner.json').write_text(json.dumps({'pid':pid,'start_ticks':start,'kind':'kitti_inference.py'})+'\n')
PYOWNER
if [[ $mode == live ]]; then
  exec python3 tools/kitti_inference.py --dataset "$dataset" --output "$output" --loop --timeout 600 --period "${PP_KITTI_PERIOD:-3}"
fi
exec python3 tools/kitti_inference.py --dataset "$dataset" --output "$output" --timeout 600 --period 0
