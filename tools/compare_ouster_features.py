#!/usr/bin/env python3
"""Frozen same-scan feature comparison using lossless raw TensorRT observations."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import statistics
import numpy as np
from ouster_features import VARIANTS, channel, packed_variant

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError('Frozen evidence changed: ' + str(path))
        return
    pending = path.with_suffix(path.suffix + '.pending')
    pending.write_bytes(content)
    pending.replace(path)


def json_save(path, obj):
    save(path, (json.dumps(obj, indent=2, allow_nan=False) + '\n').encode())


def run_command(args, logfile):
    with logfile.open('w') as log:
        subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True)


def prepare(data, output, frames_per_bag, repeats):
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import PointCloud2
    inventory = json.loads((ROOT / 'config/ouster_demo_inventory.json').read_text())
    attributes = json.loads((ROOT / 'config/model_contract.json').read_text())['input']['voxel_plugin_attributes']
    recipe = {'variants': VARIANTS, 'selection': 'Evenly spaced scan indices including first/last in each bag',
              'frames_per_bag': frames_per_bag, 'repeats': repeats, 'frames': [],
              'intensity_scale': 1.0, 'nms_iou_threshold': 0.01, 'pre_nms_top_n': 4096,
              'adaptation_limit': 'Only fourth input feature changes. XYZ/order/count unchanged; zero returns retained.',
              'accuracy_validated': False,
              'sources': ['https://github.com/ouster-lidar/ouster-ros/blob/master/include/ouster_ros/os_point.h',
                          'https://static.ouster.dev/sensor-docs/image_route1/image_route2/sensor_data/sensor-data.html',
                          'https://docs.nvidia.com/tao/tao-toolkit/6.26.03/text/cv_finetuning/pytorch/point_cloud/pointpillars.html'],
              'sensor_calibration_status': 'Firmware/profile/factory calibration metadata absent from these bags',
              'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), ROOT/'tools/ouster_features.py', ROOT/'src/postprocess.cpp', ROOT/'docker/reference/runner.cpp']}}
    frame_index = 0
    jobs = []
    for bag in inventory['bags']:
        for dbpath in sorted((data / 'ouster' / bag['bag']).glob('*.db3')):
            expected = next(x['sha256'] for x in inventory['extracted_files'] if Path(x['path']).name == dbpath.name)
            if sha(dbpath) != expected:
                raise ValueError('Source database changed')
            with sqlite3.connect(dbpath.resolve().as_uri() + '?mode=ro', uri=True) as db:
                topic = db.execute("SELECT id FROM topics WHERE name='/points'").fetchone()[0]
                messages = db.execute('SELECT id,timestamp FROM messages WHERE topic_id=? ORDER BY timestamp', (topic,)).fetchall()
                indices = np.linspace(0, len(messages)-1, frames_per_bag, dtype=int).tolist()
                for index in indices:
                    mid, stamp = messages[index]
                    payload = db.execute('SELECT data FROM messages WHERE id=?', (mid,)).fetchone()[0]
                    msg = deserialize_message(payload, PointCloud2)
                    save(output/'clouds'/f'{frame_index:06d}.cdr', payload)
                    raw = packed_variant(msg, 'raw_signal')
                    xyz_hash = hashlib.sha256(raw[:,:3].tobytes()).hexdigest()
                    lo = np.asarray(attributes['point_cloud_range'][:3], dtype=np.float32)
                    hi = np.asarray(attributes['point_cloud_range'][3:], dtype=np.float32)
                    inside = np.all((raw[:,:3] >= lo) & (raw[:,:3] < hi), axis=1)
                    xy = np.floor((raw[inside,:2] - lo[:2]) / np.asarray(attributes['voxel_size'][:2], dtype=np.float32)).astype(np.int32)
                    _, voxel_counts = np.unique(xy, axis=0, return_counts=True)
                    record = {'frame_id': f'{frame_index:06d}', 'bag': bag['bag'], 'scan_index': index,
                              'timestamp_ns': stamp, 'frame': msg.header.frame_id, 'source_cdr_sha256': hashlib.sha256(payload).hexdigest(),
                              'xyz_sha256': xyz_hash, 'points': len(raw),
                              'zero_range_points': int((channel(msg,'range')==0).sum()),
                              'zero_xyz_points': int(np.all(raw[:,:3]==0,axis=1).sum()),
                              'occupied_pillars': len(voxel_counts),
                              'pillars_above_32_points': int((voxel_counts>32).sum()),
                              'points_above_per_pillar_capacity': int(np.maximum(voxel_counts-32,0).sum()),
                              'inputs': {}}
                    for variant_index, variant in enumerate(VARIANTS):
                        packed = packed_variant(msg, variant)
                        if hashlib.sha256(packed[:,:3].tobytes()).hexdigest() != xyz_hash:
                            raise ValueError('Variant changed XYZ')
                        identifier = f'{variant_index*100000+frame_index:06d}'
                        path = output/'inputs'/(identifier+'.bin')
                        save(path, packed.tobytes())
                        record['inputs'][variant] = {'id': identifier, 'sha256': sha(path),
                                                    'feature_min': float(packed[:,3].min()), 'feature_max': float(packed[:,3].max())}
                        jobs.append(identifier+'\t/out/inputs/'+identifier+'.bin\n')
                    recipe['frames'].append(record)
                    frame_index += 1
    save(output/'jobs.tsv', ''.join(jobs).encode())
    image = subprocess.check_output(['docker','image','inspect','pp-infer:reference-trt10','--format','{{.Id}}'], text=True).strip()
    deployment = subprocess.check_output(['docker','inspect','pointpillars','--format','{{.Image}}'], text=True).strip()
    engine_sha = subprocess.check_output(['docker','exec','pointpillars','sha256sum','/var/lib/pp_infer/4b6ea34734d959f49e9a9be3326b9bdffa13d5ec7293022b16e322ac77a94b4a.engine'],text=True).split()[0]
    if engine_sha != inventory['verification']['engine_sha256'] or deployment != inventory['verification']['image_id']:
        raise ValueError('Deployment changed from Ouster baseline')
    recipe.update({'diagnostic_image_id':image,'deployment_image_id':deployment,'engine_sha256':engine_sha,
                   'engine_path':'/engines/4b6ea34734d959f49e9a9be3326b9bdffa13d5ec7293022b16e322ac77a94b4a.engine'})
    json_save(output/'recipe.json', recipe)
    return recipe


def raw_summary(rows):
    finite = np.isfinite(rows)
    invalid_geometry = (~finite[:,:7].all(axis=1)) | (rows[:,3:6] <= 0).any(axis=1)
    invalid_class = (~finite[:,7]) | (rows[:,7] < 0) | (rows[:,7] >= 3) | (rows[:,7] != np.floor(rows[:,7]))
    invalid_score = ~finite[:,8]
    valid = ~(invalid_geometry | invalid_class | invalid_score)
    columns = ['x','y','z','length','width','height','yaw','class','score']
    scores = rows[finite[:,8],8].astype(np.float64)
    geometry = rows[valid,:7].astype(np.float64)
    result = {'raw_count':len(rows), 'invalid_rows':int((~valid).sum()),
              'nonfinite_by_component':{c:int((~finite[:,i]).sum()) for i,c in enumerate(columns)},
              'nonpositive_dimensions':{c:int((rows[:,i]<=0).sum()) for i,c in zip((3,4,5),('length','width','height'))},
              'invalid_class_rows':int(invalid_class.sum()),
              'score_quantiles':np.quantile(scores,[0,.5,.9,1]).tolist() if len(scores) else [],
              'scores_at_least_0_99':int((scores>=.99).sum()),
              'score_outside_0_1':int(((scores<0)|(scores>1)).sum()),
              'raw_valid_geometry_quantiles':{c:np.quantile(geometry[:,i],[0,.5,.9,1]).tolist() if len(geometry) else [] for i,c in enumerate(columns[:7])}}
    return result


def summarize(output, recipe):
    current = output/'current-nms'
    current.mkdir(exist_ok=True)
    valid_raw = output/'valid-raw'
    valid_raw.mkdir(exist_ok=True)
    observations = []
    for frame in recipe['frames']:
        for variant, value in frame['inputs'].items():
            for repeat in range(recipe['repeats']):
                path = output/'raw'/f"{value['id']}-{repeat}.bin"
                if path.stat().st_size % 36:
                    raise ValueError('Malformed raw output size')
                rows = np.fromfile(path,dtype='<f4').reshape(-1,9)
                observation = {'frame_id':frame['frame_id'],'variant':variant,'repeat':repeat,'raw_file':str(path.relative_to(output)),
                               'raw_sha256':sha(path),**raw_summary(rows)}
                observation['frame_rejected_by_output_contract'] = observation['invalid_rows'] > 0
                if not observation['frame_rejected_by_output_contract']:
                    save(valid_raw/path.name, path.read_bytes())
                observations.append(observation)
    executable = output/'nms-current'
    run_command(['g++','-std=c++17','-O2','-DPP_CURRENT_NMS','-I'+str(ROOT/'include'),
                 str(ROOT/'docker/reference/nms_driver.cpp'),str(ROOT/'src/postprocess.cpp'),'-o',str(executable)],output/'compile-nms.log')
    run_command([str(executable),str(valid_raw),str(current)],output/'nms.log')
    for observation in observations:
        path = current/Path(observation['raw_file']).name
        if observation['frame_rejected_by_output_contract']:
            observation['final_count'] = None
            continue
        rows = np.fromfile(path,dtype='<f4').reshape(-1,9)
        observation['final_count'] = len(rows)
        observation['final_sha256'] = sha(path)
        observation['final_score_median'] = float(np.median(rows[:,8])) if len(rows) else None
        observation['final_geometry_quantiles'] = {c:np.quantile(rows[:,i].astype(np.float64),[0,.5,.9,1]).tolist() if len(rows) else [] for i,c in enumerate(('x','y','z','length','width','height','yaw'))}
    summaries = {}
    for variant in VARIANTS:
        selected = [o for o in observations if o['variant']==variant]
        accepted = [o for o in selected if not o['frame_rejected_by_output_contract']]
        finals = [o['final_count'] for o in accepted]
        summary = {'observations':len(selected),'rejected_frames':len(selected)-len(accepted),
                   'invalid_raw_rows':sum(o['invalid_rows'] for o in selected),
                   'raw_count_median':statistics.median(o['raw_count'] for o in selected),
                   'final_count_min':min(finals,default=None),'final_count_median':statistics.median(finals) if finals else None,
                   'final_count_max':max(finals,default=None),
                   'final_score_median_of_observation_medians':statistics.median(o['final_score_median'] for o in accepted if o['final_score_median'] is not None) if any(o['final_score_median'] is not None for o in accepted) else None}
        summaries[variant] = summary
    report = {'recipe_sha256':sha(output/'recipe.json'),'summary':summaries,'observations':observations,
              'limit':'Unlabeled same-scan numerical/input experiment. Lower counts or nonsaturated scores do not establish accuracy. Training/calibration parity unknown.',
              'production_default_changed':False}
    json_save(output/'report.json',report)
    print(json.dumps(summaries,indent=2),flush=True)


def main():
    import fcntl
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=ROOT/'.recovery/rosbags/ouster_calibration_v3')
    parser.add_argument('--output',type=Path,default=ROOT/'.recovery/accuracy/ouster-feature-v1')
    parser.add_argument('--frames-per-bag',type=int,default=8)
    parser.add_argument('--repeats',type=int,default=3)
    args = parser.parse_args()
    if not 2 <= args.frames_per_bag <= 32 or not 1 <= args.repeats <= 10:
        raise ValueError('Invalid experiment size')
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    with (output/'.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        recipe = prepare(args.data_dir.resolve(),output,args.frames_per_bag,args.repeats)
        raw = output/'raw'
        index = output/'raw-index.json'
        if raw.exists() and list(raw.glob('*.bin')):
            if not index.exists():
                raise ValueError('Unindexed interrupted outputs; preserve them and use a fresh --output folder')
            for name, checksum in json.loads(index.read_text()).items():
                if sha(output/name) != checksum:
                    raise ValueError('Raw evidence changed')
        else:
            command = ['docker','run','--rm','--gpus','all','--mount','type=bind,src='+str(output)+',dst=/out',
                       '--mount','type=volume,src=pp-engines,dst=/engines,readonly',recipe['diagnostic_image_id'],
                       'pp-reference',recipe['engine_path'],'/out/jobs.tsv','/out/raw',str(args.repeats)]
            run_command(command,output/'inference.log')
            json_save(index,{str(p.relative_to(output)):sha(p) for p in raw.glob('*.bin')})
        summarize(output,recipe)


if __name__ == '__main__':
    main()
