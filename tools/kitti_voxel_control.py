#!/usr/bin/env python3
"""Tuning-only capacity experiment; does not modify production inputs or baseline."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import struct

from kitti_reference import ROOT,IMAGES,MODEL_SHA,command,docker_run,read_rows,match_rows
from kitti_evaluation import sha
from prepare_kitti_validation import atomic_write,encoded,freeze_json


def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]


def voxel_key(point,attributes):
    rng=attributes['point_cloud_range'];size=attributes['voxel_size']
    if not all(rng[j]<=point[j]<rng[j+3] for j in range(3)):return None
    # Match the float32 subtraction/division and XY floorf in NVIDIA's kernel.
    return tuple(math.floor(f32(f32(point[j]-rng[j])/size[j])) for j in (0,1))


def capped_cloud(data,attributes):
    counts=Counter();output=[];occupied=0;discarded_capacity=0;outside=0
    for index,point in enumerate(struct.iter_unpack('<4f',data)):
        if not all(math.isfinite(x) for x in point):raise ValueError('Nonfinite point')
        key=voxel_key(point,attributes)
        if key is None:outside+=1;continue
        if key not in counts:
            if occupied>=attributes['max_voxels']:discarded_capacity+=1;continue
            occupied+=1;counts[key]=0
        if counts[key]>=attributes['max_num_points_per_voxel']:discarded_capacity+=1;continue
        counts[key]+=1;output.append(data[index*16:(index+1)*16])
    return b''.join(output),{'retained_points':len(output),'retained_voxels':occupied,
                           'outside_range_points':outside,'capacity_discarded_points':discarded_capacity}


def run(dataset,reference):
    recipe=json.loads((reference/'recipe.json').read_text());contract=json.loads((ROOT/'config/model_contract.json').read_text())
    if contract['model']['sha256']!=MODEL_SHA or recipe['dataset_manifest_sha256']!=sha(dataset/'manifest.json'):raise ValueError('Input identity changed')
    attributes=contract['input']['voxel_plugin_attributes'];manifest=json.loads((dataset/'manifest.json').read_text())
    candidates=[];audit=[]
    for frame in manifest['frames']:
        asset=frame['assets']['velodyne'];path=dataset/asset['path']
        if sha(path)!=asset['sha256']:raise ValueError('Changed cloud')
        cloud=path.read_bytes();counts=Counter(k for point in struct.iter_unpack('<4f',cloud) if (k:=voxel_key(point,attributes)) is not None)
        item={'frame_id':frame['frame_id'],'split':frame['split'],'occupied_voxels':len(counts),'voxels_above_point_limit':sum(n>32 for n in counts.values()),
              'points_above_per_voxel_capacity':sum(max(0,n-32) for n in counts.values()),'exceeds_max_voxels':len(counts)>attributes['max_voxels']}
        audit.append(item)
        if frame['split']=='tuning':candidates.append((frame,cloud,item))
    # Select two tuning controls by input occupancy only; held-out test stays unchanged.
    selected=[max(candidates,key=lambda x:x[2]['occupied_voxels']),max(candidates,key=lambda x:x[2]['points_above_per_voxel_capacity'])]
    selected={f['frame_id']:(f,c,a) for f,c,a in selected}
    directory=reference/'voxel-controls';directory.mkdir(exist_ok=True);frames=[];jobs=[]
    for f,cloud,audit_frame in selected.values():
        capped,stats=capped_cloud(cloud,attributes);path=directory/(f['frame_id']+'.bin')
        if path.exists() and path.read_bytes()!=capped:raise ValueError('Control input changed')
        atomic_write(path,capped);frames.append({**audit_frame,**stats,'original_sha256':sha(dataset/f['assets']['velodyne']['path']),'controlled_sha256':sha(path)})
        jobs.append(f['frame_id']+'\t/out/voxel-controls/'+path.name+'\n')
    control={'reference_recipe_sha256':sha(reference/'recipe.json'),'tool_sha256':sha(Path(__file__)),
             'attributes':attributes,'selection':'two tuning frames with maximal occupied voxel count or point overflow; deduplicated',
             'adaptation':'First max_voxels encountered in original cloud order; first max_num_points_per_voxel points per voxel; discard out-of-range points. XYZI bits retained, no translation/scaling.',
             'frames':frames,'all_frame_capacity_audit':audit}
    freeze_json(directory/'recipe.json',control);atomic_write(directory/'jobs.tsv',''.join(jobs).encode())
    gpu=recipe['gpu'].split(',')[0].strip();comparisons={}
    for version,image in IMAGES.items():
        raw=directory/version/'raw'
        # Existing observations are immutable; reruns verify the completed index.
        index=directory/(version+'-index.json')
        if raw.exists() and list(raw.glob('*.bin')) and not index.exists():raise ValueError('Interrupted unindexed control outputs; preserve and use a new reference output directory')
        if index.exists():
            for key,digest in json.loads(index.read_text()).items():
                if sha(directory/key)!=digest:raise ValueError('Changed control output')
        command(docker_run(image,gpu,[(reference,'/out',True)],['pp-reference','/out/assets/'+version+'.engine',
             '/out/voxel-controls/jobs.tsv','/out/voxel-controls/'+version+'/raw','3']),directory/(version+'.log'))
        hashes={str(p.relative_to(directory)):sha(p) for p in raw.glob('*.bin')};freeze_json(index,hashes)
        result=[]
        for frame in frames:
            f=frame['frame_id'];first=read_rows(raw/(f+'-0.bin'))
            result.append({'frame_id':f,'raw_count':len(first),'repeats':[match_rows(first,read_rows(raw/(f+'-'+str(rep)+'.bin'))) for rep in (1,2)]})
        comparisons[version]=result
    result={'control_recipe_sha256':sha(directory/'recipe.json'),'repeat_comparisons':comparisons,
            'conclusion_limit':'Two altered tuning clouds only. Improvement in repeatability does not establish accuracy, training compatibility or eliminate other sources of nondeterminism.'}
    freeze_json(directory/'report.json',result);print(json.dumps(result,indent=2));return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,default=ROOT.parent/'datasets/kitti_object_diagnostic_v1')
    p.add_argument('--reference',type=Path,default=ROOT/'.recovery/accuracy/kitti-reference-v1');a=p.parse_args();run(a.dataset.resolve(),a.reference.resolve())
