#!/usr/bin/env python3
"""Run limited CUDA allocation memcheck on original/capped tuning frame 004804."""
import argparse
import json
from pathlib import Path
import subprocess
import uuid
from kitti_reference import ROOT,command,docker_run
from kitti_evaluation import sha
from prepare_kitti_validation import atomic_write,encoded,freeze_json


def run(dataset,reference):
    command(['docker','build','--progress','plain','-t','pp-infer:reference-memcheck',
             '-f',str(ROOT/'docker/REFERENCE_MEMCHECK.Dockerfile'),str(ROOT/'docker/reference')],reference/'memcheck-build.log')
    recipe=json.loads((reference/'recipe.json').read_text());gpu=recipe['gpu'].split(',')[0]
    control=reference/'voxel-controls/004804.bin'
    if sha(control)!=next(f['controlled_sha256'] for f in json.loads((reference/'voxel-controls/recipe.json').read_text())['frames'] if f['frame_id']=='004804'):
        raise ValueError('Control cloud changed')
    manifest=json.loads((dataset/'manifest.json').read_text());frame=next(f for f in manifest['frames'] if f['frame_id']=='004804')
    if frame['split']!='tuning' or sha(dataset/frame['assets']['velodyne']['path'])!=frame['assets']['velodyne']['sha256']:
        raise ValueError('Original tuning frame changed')
    results=[]
    for mode,path in [('original','/dataset/'+frame['assets']['velodyne']['path']),('capped','/out/voxel-controls/004804.bin')]:
        jobs=reference/('memcheck-'+mode+'.tsv');atomic_write(jobs,('004804\t'+path+'\n').encode())
        raw=reference/('memcheck-'+mode)
        # A saved output would make the runner skip execution; never call that a memcheck.
        if raw.exists():raw.rename(reference/('memcheck-'+mode+'-preserved-'+str(__import__('time').time_ns())))
        cmd=docker_run('pp-infer:reference-memcheck',gpu,[(dataset,'/dataset',False),(reference,'/out',True)],
            ['compute-sanitizer','--tool','memcheck','--error-exitcode','86','--print-limit','20','pp-reference',
             '/out/assets/trt10.engine','/out/'+jobs.name,'/out/memcheck-'+mode,'1'])
        token=uuid.uuid4().hex
        name='pp-reference-memcheck-'+token
        cmd[2:2]=['--name',name,'--label','pp_infer.reference_memcheck='+token]
        log=reference/('memcheck-'+mode+'.log')
        with log.open('w') as f:
            try:code=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=120).returncode
            except subprocess.TimeoutExpired:
                code='timeout'
                # Stop only this probe's uniquely labeled container; the Docker
                # client timing out alone can leave its GPU application alive.
                try:
                    info=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
                    if info['Config']['Labels'].get('pp_infer.reference_memcheck')==token:
                        subprocess.run(['docker','stop',name],check=True,stdout=f,stderr=subprocess.STDOUT)
                except subprocess.CalledProcessError:
                    pass  # --rm may have already removed the finished container.
        contents=log.read_text();passed=code==0 and 'ERROR SUMMARY: 0 errors' in contents and (raw/'004804-0.bin').exists()
        results.append({'mode':mode,'command':cmd,'exit_code':code,'zero_allocation_errors':passed,'log_sha256':sha(log)})
    atomic_write(reference/'memcheck-results.json',encoded({'results':results,'tool_sha256':sha(Path(__file__)),
        'scope':'Two tuning inputs, one execution each, CUDA allocation memcheck only. Does not establish internal tensor bounds, race freedom, full GPU memory safety or accuracy.'}))
    print(json.dumps(results,indent=2));return results

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,default=ROOT.parent/'datasets/kitti_object_diagnostic_v1')
    p.add_argument('--reference',type=Path,default=ROOT/'.recovery/accuracy/kitti-reference-v1');a=p.parse_args();run(a.dataset.resolve(),a.reference.resolve())
