#!/usr/bin/env python3
"""Frozen signal/reflection experiment using unchanged production inference sources.

Two stages: prepare verifies the frozen source data and writes identical-geometry
inputs. run compiles the current production runtime in an existing development
image, uses an existing engine read-only, and preserves all observations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
VARIANTS={'signal_div65535':(3,65535.0),'reflectivity_div255':(5,255.0)}
ENGINE='bea83e579931a273617c656538b132346dde6fe96ad37aafd22c46af1e055e29.engine'
IMAGE='pp-infer:reference-trt10'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def save(path,value):
    path=Path(path);pending=path.with_suffix(path.suffix+'.pending')
    pending.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');pending.replace(path)


def prepare(args):
    import numpy as np
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);(out/'inputs').mkdir()
    contract=json.loads((ROOT/'config/model_contract.json').read_text())['input']['voxel_plugin_attributes']
    lo=np.asarray(contract['point_cloud_range'][:3],dtype='<f4');hi=np.asarray(contract['point_cloud_range'][3:],dtype='<f4')
    frames=[]
    if args.kind=='mosep':
        from rclpy.serialization import deserialize_message
        from sensor_msgs.msg import PointCloud2
        from ouster_features import channel
        src=args.source.resolve();source_recipe=json.loads((src/'recipe.json').read_text())
        originals=ROOT/'.recovery/rosbags/ouster_mosep_fresh_20261107'
        for relative,want in source_recipe['source_files'].items():
            if sha(originals/relative)!=want:raise ValueError('Original source changed: '+relative)
        def iterator():
            for f in source_recipe['frames']:
                path=src/'clouds'/(f['frame_id']+'.cdr')
                if sha(path)!=f['cdr_sha256']:raise ValueError('Frozen CDR changed')
                m=deserialize_message(path.read_bytes(),PointCloud2)
                rows=np.stack([channel(m,n).ravel() for n in ('x','y','z','intensity','reflectivity')],axis=1)
                yield f['frame_id'],f['condition'],'unlabeled',rows[:,:3],rows[:,3],rows[:,4],{'source_cdr_sha256':sha(path),'ground_truth':[]}
        source_identity={'kind':'MOSEP','source_recipe_sha256':sha(src/'recipe.json'),'original_files':source_recipe['source_files']}
    else:
        src=args.source.resolve();selection=json.loads((src/'frozen-selection-final.json').read_text())
        data=src/'original/Dur360BEV_Dataset_Extended'
        checks={}
        for line in (data/'md5sums.txt').read_text().splitlines():
            digest,name=line.split(maxsplit=1);checks[name.lstrip('*').removeprefix('./')]=digest
        def verified(path):
            relative=str(path.relative_to(data))
            want=checks.get(relative) or checks.get('Dur360BEV_Dataset_Extended/'+relative)
            if want is None:raise ValueError('Missing publisher MD5: '+relative)
            if hashlib.md5(path.read_bytes()).hexdigest()!=want:raise ValueError('Publisher MD5 mismatch: '+relative)
        def iterator():
            for f in selection['frames']:
                stem=f['stem'];path=data/'ouster_points/data'/(stem+'.bin');label=data/'labels/data'/(stem+'.txt')
                verified(path);verified(label)
                rows=np.fromfile(path,dtype='<f4').reshape(-1,9)
                ground=[];unsupported={}
                for line in label.read_text().splitlines():
                    if not line.strip():continue
                    cls,*values=line.split()
                    if len(values)!=7:raise ValueError('Unexpected label format')
                    h,w,l,x,y,z,yaw=map(float,values)
                    mapping={'Car':0,'Bus':0,'Truck':0,'Pedestrian':1}
                    if cls in mapping:ground.append({'class_id':mapping[cls],'source_class':cls,'row':[x,y,z,l,w,h,yaw]})
                    else:unsupported[cls]=unsupported.get(cls,0)+1
                yield stem,'dur360',f['split'],rows[:,:3],rows[:,3],rows[:,5],{
                  'original_point_sha256':sha(path),'original_label_sha256':sha(label),'publisher_md5_verified':True,
                  'ground_truth':ground,'unsupported_ground_truth_classes':unsupported,'original_points':len(rows)}
        source_identity={'kind':'Dur360BEV-Extended','selection_sha256':sha(src/'frozen-selection-final.json'),
          'published_md5_list_sha256':sha(data/'md5sums.txt'),'selection':selection.get('method',selection.get('selection_method')),
          'qualification':'Published train/test indices from a single collection, not independent drives. Publisher annotations independent of this experiment; no official benchmark score claimed.'}
    for frame_id,condition,split,xyz,signal,reflectivity,details in iterator():
        if not np.isfinite(xyz).all() or not np.isfinite(signal).all() or not np.isfinite(reflectivity).all():raise ValueError('Nonfinite source values')
        if signal.min()<0 or signal.max()>65535 or reflectivity.min()<0 or reflectivity.max()>255:raise ValueError('Channel exceeds declared profile')
        original=len(xyz)
        # The 128-beam source exceeds engine capacity. Crop only by encoded model
        # ROI, identically for both channels. Never silently truncate a scan.
        if args.kind=='dur360':
            mask=np.all((xyz>=lo)&(xyz<hi),axis=1)&np.any(xyz!=0,axis=1);xyz=xyz[mask];signal=signal[mask];reflectivity=reflectivity[mask]
        if args.bounded_voxels:
            from ouster_point_policy import bounded_indices
            retained,selection_audit=bounded_indices(xyz,lo,hi,contract['voxel_size'][:2])
            xyz=xyz[retained];signal=signal[retained];reflectivity=reflectivity[retained]
            details['bounded_selection']=selection_audit
        if len(xyz)>204800:raise ValueError('ROI still exceeds engine capacity; declare a separate selection policy')
        inside=np.all((xyz>=lo)&(xyz<hi),axis=1)
        xy=np.floor((xyz[inside,:2]-lo[:2])/np.asarray(contract['voxel_size'][:2],dtype='<f4')).astype(np.int32)
        _,occ=np.unique(xy,axis=0,return_counts=True)
        frame={'frame_id':frame_id,'condition':condition,'split':split,'original_points':original,'points':len(xyz),
          'xyz_sha256':hashlib.sha256(xyz.tobytes()).hexdigest(),'zero_xyz_points':int(np.all(xyz==0,axis=1).sum()),
          'occupied_pillars':len(occ),'pillars_above_32':int((occ>32).sum()),'pillar_capacity_exceeded':len(occ)>10000,
          **details,'inputs':{}}
        for variant,(values,divisor) in {'signal_div65535':(signal,65535.0),'reflectivity_div255':(reflectivity,255.0)}.items():
            packed=np.empty((len(xyz),4),dtype='<f4');packed[:,:3]=xyz
            # Match the production C++ adapter's double division then float cast.
            packed[:,3]=(values.astype(np.float64)/divisor).astype('<f4')
            assert packed[:,:3].tobytes()==xyz.tobytes()
            relative='inputs/'+frame_id+'-'+variant+'.bin';(out/relative).write_bytes(packed.tobytes())
            frame['inputs'][variant]={'path':relative,'sha256':sha(out/relative),'feature_min':float(packed[:,3].min()),'feature_max':float(packed[:,3].max())}
        frames.append(frame)
    jobs=[];rng=random.Random(args.seed)
    for _ in range(3):
        for v in VARIANTS:jobs.append({'frame_id':frames[len(frames)//2]['frame_id'],'variant':v,'repeat':-1,'warmup':True})
    for repeat in range(args.repeats):
        batch=[{'frame_id':f['frame_id'],'variant':v,'repeat':repeat,'warmup':False} for f in frames for v in VARIANTS]
        rng.shuffle(batch);jobs.extend(batch)
    by_frame={f['frame_id']:f for f in frames}
    for i,job in enumerate(jobs):job['id']=f'{i:06d}'
    (out/'jobs.tsv').write_text(''.join(j['id']+'\t/out/'+by_frame[j['frame_id']]['inputs'][j['variant']]['path']+'\n' for j in jobs))
    save(out/'recipe.json',{'source':source_identity,'frames':frames,'jobs':jobs,'repeats':args.repeats,'seed':args.seed,'bounded_voxels':args.bounded_voxels,'preparation_tool_sha256':sha(__file__),
      'primary_variants':list(VARIANTS),'point_policy':('Separate capacity-control sensitivity: finite nonzero model-ROI points, first10000 encountered XY pillars, first32points each, preserved input order, same selection for both variants.' if args.bounded_voxels else 'MOSEP unchanged points. Dur360 encoded model ROI and all-zero-XYZ invalid-return removal, required for engine capacity, identical for both variants. Original files preserved. No coordinate shifts, arbitrary truncation, or voxel-cap correction.'),
      'evaluation_policy':{'region_center_xyz':[-50,-50,-1.4,50,50,4.4],'iou_thresholds':{'Vehicle':.7,'Pedestrian':.5},'deployment_threshold':.4,'threshold_sensitivity':[0,.1,.2,.3,.4,.5,.6,.7,.8,.9]},
      'accuracy_claim':'MOSEP unlabeled. Dur360 diagnostic subset only; not official KITTI or Dur360 leaderboard.'})
    print('Prepared',len(frames),'frames and',len(jobs),'jobs',flush=True)


def run(args):
    import struct
    out=args.output.resolve();recipe=json.loads((out/'recipe.json').read_text())
    if (out/'runtime.json').exists() or (out/'raw').exists():raise ValueError('Preserve existing inference; use a new prepared output directory')
    for f in recipe['frames']:
        for v in f['inputs'].values():
            if sha(out/v['path'])!=v['sha256']:raise ValueError('Prepared input changed')
    image=subprocess.check_output(['docker','image','inspect',args.image,'--format','{{.Id}}'],text=True).strip()
    source_files=['src/pointpillar.cpp','src/postprocess.cpp','include/pp_infer/pointpillar.h','include/pp_infer/postprocess.h','include/pp_infer/cuda_resources.hpp','include/pp_infer/model_contract.hpp','include/pp_infer/output_contract.hpp','docker/reference/production_runner.cpp']
    runtime={'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'source_sha256':{p:sha(ROOT/p) for p in source_files},'image_id':image,
      'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=name,uuid,driver_version','--format=csv,noheader'],text=True).strip(),
      'engine':ENGINE,'parameters':{'nms_iou':.01,'top_n':4096,'class_count':3,'score_gate_for_export':0},'recipe_sha256':sha(out/'recipe.json')}
    base=['docker','run','--rm','--pull=never','--network','none','--entrypoint','/bin/bash','--mount','type=bind,src='+str(ROOT)+',dst=/repo,readonly','--mount','type=bind,src='+str(out)+',dst=/out']
    compile_command='g++ -std=c++17 -O2 -I/repo/include -I/usr/local/cuda/include /repo/docker/reference/production_runner.cpp /repo/src/pointpillar.cpp /repo/src/postprocess.cpp -L/opt/tensorrt/lib -L/opt/cuda/lib -l:libnvinfer.so.10 -l:libnvinfer_plugin.so.10 -l:libcudart.so.12 -o /out/production-runner'
    with (out/'compile.log').open('w') as log:subprocess.run(base+[image,'-lc',compile_command],stdout=log,stderr=subprocess.STDOUT,check=True)
    runtime['runner_sha256']=sha(out/'production-runner')
    engine_command='sha256sum /engines/'+ENGINE
    runtime['engine_sha256']=subprocess.check_output(base+['--mount','type=volume,src=pp-engines,dst=/engines,readonly',image,'-lc',engine_command],text=True).split()[0]
    save(out/'runtime.json',runtime)
    with (out/'inference.log').open('w') as log:
        subprocess.run(base+['--gpus','all','--mount','type=volume,src=pp-engines,dst=/engines,readonly',image,'-lc','/out/production-runner /engines/'+ENGINE+' /out/jobs.tsv /out/raw 1'],stdout=log,stderr=subprocess.STDOUT,check=True)
    statuses={r['id']:r for r in map(json.loads,(out/'raw/status.jsonl').read_text().splitlines())}
    frames={f['frame_id']:f for f in recipe['frames']};observations=[];warmups=[]
    for job in recipe['jobs']:
        r=statuses[job['id']];f=frames[job['frame_id']];rows=[]
        if r['status']=='ok':rows=list(struct.iter_unpack('<9f',(out/'raw'/(job['id']+'-0.bin')).read_bytes()))
        record={**job,'condition':f['condition'],'split':f['split'],'status':r['status'],'rows':rows,
           'seconds':r['seconds'],'error':r.get('error'),'ground_truth':f['ground_truth'],'pillar_capacity_exceeded':f['pillar_capacity_exceeded']}
        (warmups if job['warmup'] else observations).append(record)
    save(out/'observations.json',{'complete':True,'observations':observations,'warmups':warmups,'new_gpu_inference':True})
    save(out/'evidence-sha256.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='evidence-sha256.json'})
    print('Completed',len(observations),'production inferences',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['prepare','run']);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--kind',choices=['mosep','dur360']);parser.add_argument('--source',type=Path)
    parser.add_argument('--bounded-voxels',action='store_true',help='Separate capacity-control sensitivity; changes input selection identically for both channels')
    parser.add_argument('--image',default=IMAGE);parser.add_argument('--repeats',type=int,default=5);parser.add_argument('--seed',type=int,default=20261108)
    args=parser.parse_args()
    if args.mode=='prepare' and (args.kind is None or args.source is None):parser.error('prepare requires --kind and --source')
    if not 3<=args.repeats<=20:parser.error('repeats must be3..20')
    (prepare if args.mode=='prepare' else run)(args)


if __name__=='__main__':main()
