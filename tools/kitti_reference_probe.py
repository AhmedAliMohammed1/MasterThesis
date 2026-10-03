#!/usr/bin/env python3
"""One-frame trtexec candidate consistency probe; does not certify full runtime parity."""
import argparse
import json
import math
from pathlib import Path
import re
import statistics
import struct
import subprocess

from kitti_evaluation import sha
from prepare_kitti_validation import atomic_write,encoded


def probe(dataset,predictions,output,container,frame):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',container) or not re.fullmatch(r'\d{6}',frame):
        raise ValueError('Invalid container/frame identity')
    info=json.loads(subprocess.check_output(['docker','inspect',container]))[0]
    commands=subprocess.check_output(['docker','top',container,'-eo','pid,args'],text=True)
    paths=set(re.findall(r'engine_path:=([^\s]+\.engine)',commands))
    if len(paths)!=1:raise ValueError('Expected one loaded validation engine')
    engine=paths.pop();engine_name=Path(engine).name
    if not re.fullmatch(r'[0-9a-f]{64}\.engine',engine_name) or Path(engine).parent.as_posix()!='/var/lib/pp_infer':
        raise ValueError('Unexpected engine cache path')
    mount=next(m for m in info['Mounts'] if m['Destination']=='/var/lib/pp_infer')
    engine_mount=('type=volume,src='+mount['Name'] if mount['Type']=='volume' else 'type=bind,src='+mount['Source'])+',dst=/engines,readonly'
    manifest=json.loads((dataset/'manifest.json').read_text())
    selected=next(f for f in manifest['frames'] if f['frame_id']==frame)
    cloud_path=dataset/selected['assets']['velodyne']['path']
    if sha(cloud_path)!=selected['assets']['velodyne']['sha256']:raise ValueError('Cloud digest mismatch')
    cloud=cloud_path.read_bytes();output.mkdir(parents=True,exist_ok=True)
    atomic_write(output/'points.bin',cloud+bytes(204800*16-len(cloud)))
    atomic_write(output/'num_points.bin',struct.pack('<i',len(cloud)//16))
    command=['docker','run','--rm','--gpus','all','--mount','type=bind,src='+str(output)+',dst=/reference',
             '--mount',engine_mount,info['Image'],'trtexec','--loadEngine=/engines/'+engine_name,
             '--shapes=points:1x204800x4,num_points:1',
             '--loadInputs=points:/reference/points.bin,num_points:/reference/num_points.bin',
             '--device=0','--warmUp=0','--duration=0','--iterations=1','--exportOutput=/reference/raw-output.json']
    with (output/'trtexec.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    tensors={t['name']:t['values'] for t in json.loads((output/'raw-output.json').read_text())}
    count=int(tensors['num_boxes'][0]);rows=[tensors['output_boxes'][i*9:i*9+9] for i in range(count)]
    ros=json.loads((predictions/f'predictions/{frame}.json').read_text())['detections'];errors=[]
    for p in ros:
        candidates=[]
        for row in rows:
            if int(row[7])!=p['class_id']:continue
            expected=p['center_lidar']+p['dimensions_lwh']+[p['yaw_lidar'],p['score']]
            actual=row[:7]+[row[8]]
            difference=[abs(x-y) for x,y in zip(expected,actual)]
            difference[6]=abs((expected[6]-actual[6]+math.pi)%(2*math.pi)-math.pi)
            candidates.append(max(difference))
        errors.append(min(candidates) if candidates else None)
    result={'frame_id':frame,'image_id':info['Image'],'engine_sha256':subprocess.check_output(['docker','exec',container,'sha256sum',engine],text=True).split()[0],
            'cloud_sha256':sha(cloud_path),'padded_points_sha256':sha(output/'points.bin'),'raw_output_sha256':sha(output/'raw-output.json'),
            'command':command,'raw_count':count,'ros_final_count':len(ros),'raw_z_median':statistics.median(r[2] for r in rows) if rows else None,
            'ros_z_median':statistics.median(p['center_lidar'][2] for p in ros) if ros else None,
            'same_class_nearest_row_max_component_error':errors,'within_1e_minus_3':sum(e is not None and e<1e-3 for e in errors),
            'limit':'one-frame candidate consistency only; independent full pre/post-NMS parity pending. trtexec floats rounded and repeated model execution varies; no unique-row matching enforced.'}
    atomic_write(output/'probe.json',encoded(result));print(json.dumps({k:v for k,v in result.items() if k!='same_class_nearest_row_max_component_error'},indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--predictions',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--container',default='pointpillars-validation');p.add_argument('--frame',default='005876')
    a=p.parse_args();probe(a.dataset.resolve(),a.predictions.resolve(),a.output.resolve(),a.container,a.frame)
