#!/usr/bin/env python3
"""Independent TRT8/TRT10 diagnostic comparison; not original training parity."""
import argparse
from collections import defaultdict, deque
import fcntl
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time

from kitti_evaluation import sha, evaluate
from prepare_kitti_validation import atomic_write, encoded, freeze_json

ROOT=Path(__file__).resolve().parents[1]
MODEL_SHA='2dcabddc3a365e9608a112d7bbbb7db769a6dddeeaa59aa03611a83113326da1'
IMAGES={'trt8':'pp-infer:reference-trt861','trt10':'pp-infer:reference-trt10'}


def command(cmd,log=None):
    if log:
        log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
    else:subprocess.run(cmd,check=True)


def read_rows(path):
    data=path.read_bytes()
    if len(data)%36 or len(data)>393216*36:raise ValueError('Invalid raw size: '+str(path))
    rows=list(struct.iter_unpack('<9f',data))
    for r in rows:
        if not all(math.isfinite(x) for x in r) or min(r[3:6])<=0 or r[7] not in (0,1,2) or not 0<=r[8]<=1:
            raise ValueError('Invalid raw candidate: '+str(path))
    return rows


def record_rows(rows):
    return [{'center_lidar':list(r[:3]),'dimensions_lwh':list(r[3:6]),'yaw_lidar':r[6],
             'class_id':int(r[7]),'score':r[8]} for r in rows]


def saved_rows(path):
    return [tuple(p['center_lidar']+p['dimensions_lwh']+[p['yaw_lidar'],p['class_id'],p['score']])
            for p in json.loads(path.read_text())['detections']]


def component_error(a,b):
    d=[abs(a[i]-b[i]) for i in (0,1,2,3,4,5,6,8)]
    d[6]=abs((a[6]-b[6]+math.pi)%(2*math.pi)-math.pi)
    return max(d)


def match_rows(left,right,tolerance=.001):
    """Maximum cardinality one-to-one matching under declared component tolerance.

    Spatial hashing avoids comparing separated rows. Augmenting paths ensure two
    duplicates cannot both claim the same reference row. Yaw wraps at +/-pi.
    This reports a diagnostic tolerance, not a model acceptance threshold.
    """
    if not math.isfinite(tolerance) or tolerance<=0:raise ValueError('Invalid tolerance')
    grid=defaultdict(list)
    def key(r):return (int(r[7]),*(math.floor(v/tolerance) for v in r[:3]))
    for j,r in enumerate(right):grid[key(r)].append(j)
    adjacency=[]
    for row in left:
        cls,x,y,z=key(row);candidates=[]
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for dz in (-1,0,1):
                    candidates.extend(j for j in grid.get((cls,x+dx,y+dy,z+dz),()) if component_error(row,right[j])<=tolerance)
        adjacency.append(sorted(candidates,key=lambda j:component_error(row,right[j])))
    # Iterative alternating-path BFS avoids recursion limits for dense duplicates.
    owners={};mates={}
    for start in range(len(left)):
        queue=deque([start]);seen_left={start};seen_right=set();parents={};free=None
        while queue and free is None:
            i=queue.popleft()
            for j in adjacency[i]:
                if j in seen_right:continue
                seen_right.add(j);parents[j]=i
                if j not in owners:free=j;break
                k=owners[j]
                if k not in seen_left:seen_left.add(k);queue.append(k)
        if free is not None:
            j=free
            while True:
                i=parents[j];old=mates.get(i);owners[j]=i;mates[i]=j
                if old is None:break
                j=old
    errors=[component_error(left[i],right[j]) for i,j in mates.items()]
    return {'left':len(left),'right':len(right),'matched':len(mates),
            'unmatched_left':len(left)-len(mates),'unmatched_right':len(right)-len(mates),
            'match_fraction_of_larger':len(mates)/max(len(left),len(right)) if left or right else 1,
            'max_matched_component_error':max(errors,default=0),'tolerance':tolerance}


def image_id(image):return subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip()


def docker_run(image,gpu,mounts,args):
    cmd=['docker','run','--rm','--gpus','device='+gpu]
    for source,dest,writable in mounts:
        source=str(source.resolve())
        if ',' in source:raise ValueError('Docker mount path cannot contain comma')
        cmd+=['--mount','type=bind,src='+source+',dst='+dest+('' if writable else ',readonly')]
    return cmd+[image]+args


def build(output):
    for version,file in [('trt8','Dockerfile'),('trt10','Dockerfile.trt10')]:
        command(['docker','build','--progress','plain','-t',IMAGES[version],'-f',str(ROOT/'docker/reference'/file),str(ROOT/'docker/reference')],output/f'build-{version}.log')


def collect(dataset,baseline,output,container,repeats,gpu):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',container):raise ValueError('Invalid container')
    # Resolve to one physical GPU so both environments see the selected GPU as 0.
    gpu_info=subprocess.check_output(['nvidia-smi','--id='+gpu,'--query-gpu=uuid,name,driver_version','--format=csv,noheader'],text=True).strip()
    lines=gpu_info.splitlines()
    if len(lines)!=1:raise ValueError('Select exactly one GPU')
    gpu_uuid=gpu_info.split(',')[0].strip()
    if not re.fullmatch(r'GPU-[0-9a-fA-F-]+',gpu_uuid):raise ValueError('Invalid GPU UUID')
    manifest=json.loads((dataset/'manifest.json').read_text());base_run=json.loads((baseline/'run.json').read_text())
    if base_run['dataset_manifest_sha256']!=sha(dataset/'manifest.json'):raise ValueError('Baseline/dataset mismatch')
    index=json.loads((baseline/'prediction_manifest.json').read_text())
    if index['run_sha256']!=sha(baseline/'run.json'):raise ValueError('Baseline run mismatch')
    expected={f['frame_id']:f['sha256'] for f in index['frames']}
    if set(expected)!={f['frame_id'] for f in manifest['frames']}:raise ValueError('Incomplete baseline')
    inputs=[];jobs=[]
    for frame in manifest['frames']:
        f=frame['frame_id'];asset=frame['assets']['velodyne'];path=dataset/asset['path']
        if sha(path)!=asset['sha256'] or sha(baseline/f'predictions/{f}.json')!=expected[f]:raise ValueError('Frozen input/output changed')
        data=path.read_bytes()
        if not data or len(data)%16 or len(data)>204800*16:raise ValueError('Invalid cloud')
        h=hashlib.sha256(data);h.update(bytes(204800*16-len(data)))
        inputs.append({'frame_id':f,'split':frame['split'],'cloud_sha256':asset['sha256'],
                       'padded_points_sha256':h.hexdigest(),'num_points':len(data)//16,
                       'num_points_sha256':hashlib.sha256(struct.pack('<i',len(data)//16)).hexdigest()})
        jobs.append(f+'\t/dataset/'+asset['path']+'\n')
    info=json.loads(subprocess.check_output(['docker','inspect',container]))[0]
    commands=subprocess.check_output(['docker','top',container,'-eo','pid,args'],text=True)
    paths=set(re.findall(r'engine_path:=([^\s]+\.engine)',commands))
    if len(paths)!=1:raise ValueError('Expected one running baseline engine')
    engine=paths.pop()
    if not re.fullmatch(r'/var/lib/pp_infer/[0-9a-f]{64}\.engine',engine):raise ValueError('Unexpected engine path')
    engine_sha=subprocess.check_output(['docker','exec',container,'sha256sum',engine],text=True).split()[0]
    recipe={'schema_version':1,'dataset_manifest_sha256':sha(dataset/'manifest.json'),
            'baseline_prediction_manifest_sha256':sha(baseline/'prediction_manifest.json'),
            'model_sha256':MODEL_SHA,'images':{v:image_id(i) for v,i in IMAGES.items()},
            'deployment_image':info['Image'],'trt10_engine_sha256':engine_sha,'gpu':gpu_info,
            'repeats':repeats,'inputs':inputs,'builder':{'precision':'FP32','tf32':False,'workspace_mib':1024,'batch':1},
            'nms':{'threshold':.01,'top_n':4096,'class_agnostic':True},
            'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'src/postprocess.cpp',ROOT/'include/pp_infer/postprocess.h',*sorted((ROOT/'docker/reference').glob('*'))] if p.is_file()},
            'limit':'TRT8.6 compatibility reference with unchanged NVIDIA sample NMS; not an original training-framework fixture.'}
    output.mkdir(parents=True,exist_ok=True);freeze_json(output/'recipe.json',recipe)
    atomic_write(output/'jobs.tsv',''.join(jobs).encode())
    assets=output/'assets';assets.mkdir(exist_ok=True)
    for name,source,expected_sha in [('model.onnx','/opt/models/pointpillars.onnx',MODEL_SHA),('trt10.engine',engine,engine_sha)]:
        target=assets/name
        if not target.exists():
            pending=target.with_suffix(target.suffix+'.pending');command(['docker','cp',container+':'+source,str(pending)])
            if sha(pending)!=expected_sha:raise ValueError('Artifact copy digest mismatch')
            pending.replace(target)
        if sha(target)!=expected_sha:raise ValueError('Frozen artifact changed: '+name)
    engine8=assets/'trt8.engine';engine_record=assets/'trt8-engine.json'
    mounts=[(dataset,'/dataset',False),(output,'/out',True)]
    if engine8.exists():
        meta=json.loads(engine_record.read_text())
        if meta['recipe_sha256']!=sha(output/'recipe.json') or meta['engine_sha256']!=sha(engine8):raise ValueError('TRT8 engine provenance mismatch')
    else:
        pending=assets/'trt8.pending.engine'
        if pending.exists():pending.rename(assets/('trt8.interrupted-'+str(time.time_ns())+'.engine'))
        cmd=docker_run(IMAGES['trt8'],gpu_uuid,mounts,['/usr/src/tensorrt/bin/trtexec','--onnx=/out/assets/model.onnx',
           '--minShapes=points:1x204800x4,num_points:1','--optShapes=points:1x204800x4,num_points:1',
           '--maxShapes=points:1x204800x4,num_points:1','--noTF32','--memPoolSize=workspace:1024',
           '--skipInference','--saveEngine=/out/assets/trt8.pending.engine'])
        command(cmd,output/'engine-trt8.log');pending.replace(engine8)
        atomic_write(engine_record,encoded({'recipe_sha256':sha(output/'recipe.json'),'engine_sha256':sha(engine8),'command':cmd}))
    # Hash completed outputs before allowing reuse. Interrupted, unindexed outputs
    # are preserved and recollected; the runner only skips indexed files.
    raw_index=output/'raw-index.json'
    saved=json.loads(raw_index.read_text()) if raw_index.exists() else {'files':{}}
    if saved.get('recipe_sha256',sha(output/'recipe.json'))!=sha(output/'recipe.json'):raise ValueError('Raw index recipe changed')
    for version in IMAGES:
        raw=output/version/'raw';raw.mkdir(parents=True,exist_ok=True)
        for f in raw.glob('*.bin'):
            key=str(f.relative_to(output))
            if key in saved['files']:
                if sha(f)!=saved['files'][key]:raise ValueError('Raw output changed: '+key)
                read_rows(f)
            else:f.rename(f.with_suffix('.interrupted-'+str(time.time_ns())+'.bin'))
        # Keep quarantined observations outside the active raw directory.
        for f in raw.glob('*.interrupted-*.bin'):
            archive=output/'interrupted';archive.mkdir(exist_ok=True);f.rename(archive/(version+'-'+f.name))
        cmd=docker_run(IMAGES[version],gpu_uuid,mounts,['pp-reference','/out/assets/'+version+'.engine',
            '/out/jobs.tsv','/out/'+version+'/raw',str(repeats)])
        command(cmd,output/f'collect-{version}.log')
        for frame in manifest['frames']:
            for rep in range(repeats):
                f=raw/(frame['frame_id']+'-'+str(rep)+'.bin');read_rows(f)
                saved['files'][str(f.relative_to(output))]=sha(f)
        saved['recipe_sha256']=sha(output/'recipe.json');atomic_write(raw_index,encoded(saved))
        command(docker_run(IMAGES[version],gpu_uuid,mounts,['pp-reference-nms','/out/'+version+'/raw','/out/'+version+'/nvidia-nms']),output/f'nms-{version}.log')
    # Compile the existing CPU implementation unchanged, then apply to the same raw bytes.
    with tempfile.TemporaryDirectory(prefix='pp-current-nms-') as temp:
        executable=Path(temp)/'nms'
        command(['g++','-std=c++17','-O2','-DPP_CURRENT_NMS','-I'+str(ROOT/'include'),str(ROOT/'docker/reference/nms_driver.cpp'),
                 str(ROOT/'src/postprocess.cpp'),'-o',str(executable)],output/'compile-current-nms.log')
        for version in IMAGES:command([str(executable),str(output/version/'raw'),str(output/version/'current-nms')],output/f'current-nms-{version}.log')
        atomic_write(output/'current-nms-implementation.json',encoded({'source_sha256':sha(ROOT/'src/postprocess.cpp'),
            'header_sha256':sha(ROOT/'include/pp_infer/postprocess.h'),'driver_sha256':sha(ROOT/'docker/reference/nms_driver.cpp'),
            'binary_sha256':sha(executable),'compiler':subprocess.check_output(['g++','--version'],text=True).splitlines()[0]}))
    files={str(f.relative_to(output)):sha(f) for v in IMAGES for kind in ('raw','nvidia-nms','current-nms') for f in (output/v/kind).glob('*.bin')}
    atomic_write(output/'collection.json',encoded({'recipe_sha256':sha(output/'recipe.json'),'files':files,'complete':True}))
    print('PASS: reference collection complete',flush=True)


def export(dataset,output,version,kind):
    manifest=json.loads((dataset/'manifest.json').read_text());dest=output/f'{version}-{kind}-predictions';dest.mkdir(exist_ok=True)
    run={'dataset_manifest_sha256':sha(dataset/'manifest.json'),'reference_recipe_sha256':sha(output/'recipe.json'),
         'source':version+'/'+kind,'observation':'first repeat; lossless candidates, no coordinate adaptation'}
    freeze_json(dest/'run.json',run);frames=[]
    for frame in manifest['frames']:
        f=frame['frame_id'];path=dest/f'predictions/{f}.json'
        record={'frame_id':f,'split':frame['split'],'cloud_sha256':frame['assets']['velodyne']['sha256'],
                'run_sha256':sha(dest/'run.json'),'detections':record_rows(read_rows(output/version/kind/(f+'-0.bin')))}
        freeze_json(path,record);frames.append({'frame_id':f,'path':str(path.relative_to(dest)),'sha256':sha(path)})
    freeze_json(dest/'prediction_manifest.json',{'run_sha256':sha(dest/'run.json'),'frames':frames});return dest


def report(dataset,baseline,output):
    recipe=json.loads((output/'recipe.json').read_text());collection=json.loads((output/'collection.json').read_text())
    if collection['recipe_sha256']!=sha(output/'recipe.json') or not collection['complete']:raise ValueError('Incomplete collection')
    if recipe['dataset_manifest_sha256']!=sha(dataset/'manifest.json') or recipe['baseline_prediction_manifest_sha256']!=sha(baseline/'prediction_manifest.json'):
        raise ValueError('Report input changed')
    for key,h in collection['files'].items():
        if sha(output/key)!=h:raise ValueError('Collection changed: '+key)
    frames=[]
    for frame in recipe['inputs']:
        f=frame['frame_id'];record={'frame_id':f,'split':frame['split']}
        for version in IMAGES:
            raw=read_rows(output/version/'raw'/(f+'-0.bin'))
            old=read_rows(output/version/'nvidia-nms'/(f+'-0.bin'));new=read_rows(output/version/'current-nms'/(f+'-0.bin'))
            record[version]={'raw_count':len(raw),'nvidia_nms_count':len(old),'current_nms_count':len(new),
                            'same_raw_nms_comparison':match_rows(old,new,1e-6),
                            'raw_z_median':__import__('statistics').median(r[2] for r in raw) if raw else None,
                            'repeat_raw':[],'repeat_final':[]}
            for rep in range(1,recipe['repeats']):
                record[version]['repeat_raw'].append(match_rows(raw,read_rows(output/version/'raw'/(f+'-'+str(rep)+'.bin'))))
                record[version]['repeat_final'].append(match_rows(old,read_rows(output/version/'nvidia-nms'/(f+'-'+str(rep)+'.bin'))))
        for kind in ('raw','nvidia-nms','current-nms'):
            record['cross_version_'+kind]=match_rows(read_rows(output/'trt8'/kind/(f+'-0.bin')),read_rows(output/'trt10'/kind/(f+'-0.bin')))
        baseline_rows=saved_rows(baseline/f'predictions/{f}.json')
        record['trt10_current_vs_frozen_ros']=match_rows(read_rows(output/'trt10/current-nms'/(f+'-0.bin')),baseline_rows)
        frames.append(record)
    result={'recipe_sha256':sha(output/'recipe.json'),'collection_sha256':sha(output/'collection.json'),
            'matching':'maximum-cardinality one-to-one same-class match; all 8 float components <=0.001, yaw wrapped; same-raw NMS <=1e-6',
            'frames':frames,'limit':recipe['limit'],'accuracy_acceptance':False,'exact_training_reference_parity':False}
    for version,kind in [('trt8','nvidia-nms'),('trt10','nvidia-nms'),('trt10','current-nms')]:
        predictions=export(dataset,output,version,kind)
        evaluate(dataset,predictions,predictions/'evaluation')
    atomic_write(output/'comparison.json',encoded(result));print('PASS: comparison and accuracy reports written',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['build','collect','report','all'])
    p.add_argument('--dataset',type=Path,default=ROOT.parent/'datasets/kitti_object_diagnostic_v1')
    p.add_argument('--baseline',type=Path,default=ROOT/'.recovery/accuracy/kitti-baseline-v1')
    p.add_argument('--output',type=Path,default=ROOT/'.recovery/accuracy/kitti-reference-v1')
    p.add_argument('--container',default='pointpillars-validation');p.add_argument('--repeats',type=int,default=3);p.add_argument('--gpu',default='0')
    a=p.parse_args()
    if not 1<=a.repeats<=20:p.error('repeats must be 1..20')
    a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
    with (a.output/'.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if a.action in ('build','all'):build(a.output)
        if a.action in ('collect','all'):collect(a.dataset.resolve(),a.baseline.resolve(),a.output,a.container,a.repeats,a.gpu)
        if a.action in ('report','all'):report(a.dataset.resolve(),a.baseline.resolve(),a.output)

if __name__=='__main__':main()
