#!/usr/bin/env python3
"""Score all saved reference repeats and summarize diagnostic numerical comparisons."""
import argparse
import json
from pathlib import Path
import statistics

from kitti_reference import ROOT, read_rows,record_rows
from kitti_evaluation import sha,evaluate
from kitti_diagnose import diagnose
from prepare_kitti_validation import freeze_json,atomic_write,encoded


def median_or_none(values):
    values=list(values)
    return statistics.median(values) if values else None


def summarize(dataset,output):
    recipe=json.loads((output/'recipe.json').read_text());collection=json.loads((output/'collection.json').read_text())
    if collection['recipe_sha256']!=sha(output/'recipe.json') or recipe['dataset_manifest_sha256']!=sha(dataset/'manifest.json'):
        raise ValueError('Recipe/collection/dataset changed')
    for key,digest in collection['files'].items():
        if sha(output/key)!=digest:raise ValueError('Reference observation changed: '+key)
    manifest=json.loads((dataset/'manifest.json').read_text());scores={}
    for version,kind in [('trt8','nvidia-nms'),('trt10','current-nms')]:
        measurements=[]
        for rep in range(recipe['repeats']):
            if rep==0:dest=output/f'{version}-{kind}-predictions'
            else:
                dest=output/f'{version}-{kind}-repeat{rep}-predictions';dest.mkdir(exist_ok=True)
                run={'dataset_manifest_sha256':sha(dataset/'manifest.json'),'reference_recipe_sha256':sha(output/'recipe.json'),
                     'source':version+'/'+kind,'repeat':rep,'outputs':'Frozen final boxes; no input/output adaptation'}
                freeze_json(dest/'run.json',run);index=[]
                for frame in manifest['frames']:
                    f=frame['frame_id'];path=dest/f'predictions/{f}.json'
                    record={'frame_id':f,'split':frame['split'],'cloud_sha256':frame['assets']['velodyne']['sha256'],
                            'run_sha256':sha(dest/'run.json'),'detections':record_rows(read_rows(output/version/kind/(f+'-'+str(rep)+'.bin')))}
                    freeze_json(path,record);index.append({'frame_id':f,'path':str(path.relative_to(dest)),'sha256':sha(path)})
                freeze_json(dest/'prediction_manifest.json',{'run_sha256':sha(dest/'run.json'),'frames':index})
                evaluate(dataset,dest,dest/'evaluation')
            diagnostic=diagnose(dataset,dest/'evaluation',dest/'diagnostics')
            measurement={'repeat':rep,'vertical':{s:v['summary'] for s,v in diagnostic['splits'].items()},'metrics':{}}
            for split in ('tuning','test'):
                metric=json.loads((dest/'evaluation'/f'{split}-metrics.json').read_text())
                measurement['metrics'][split]={c:{m:v['moderate'] for m,v in fields.items()} for c,fields in metric['classes'].items()}
            measurements.append(measurement)
        scores[version]=measurements
    comparison=json.loads((output/'comparison.json').read_text());frames=comparison['frames'];numeric={}
    for key in ('cross_version_raw','cross_version_nvidia-nms','cross_version_current-nms','trt10_current_vs_frozen_ros'):
        rows=[f[key] for f in frames]
        numeric[key]={'matched':sum(r['matched'] for r in rows),'left':sum(r['left'] for r in rows),'right':sum(r['right'] for r in rows),
                      'median_frame_match_fraction':statistics.median(r['match_fraction_of_larger'] for r in rows)}
    for version in ('trt8','trt10'):
        same=[f[version]['same_raw_nms_comparison'] for f in frames]
        numeric[version]={'same_raw_nms_different_frames':sum(bool(r['unmatched_left'] or r['unmatched_right']) for r in same),
                          'repeat_raw_median_match_fraction':median_or_none(r['match_fraction_of_larger'] for f in frames for r in f[version]['repeat_raw']),
                          'repeat_final_median_match_fraction':median_or_none(r['match_fraction_of_larger'] for f in frames for r in f[version]['repeat_final'])}
        for kind in ('raw','nvidia-nms'):
            counts=[[len(read_rows(output/version/kind/(f['frame_id']+'-'+str(rep)+'.bin'))) for rep in range(recipe['repeats'])] for f in frames]
            numeric[version][kind+'_repeat_count_varied_frames']=sum(len(set(c))>1 for c in counts)
            numeric[version][kind+'_repeat_max_count_span']=max(max(c)-min(c) for c in counts)
    result={'recipe_sha256':sha(output/'recipe.json'),'comparison_sha256':sha(output/'comparison.json'),
            'summarizer_sha256':sha(Path(__file__)),'numeric':numeric,'scores':scores,
            'conclusion':'Both independent TRT8 compatibility and current TRT10 pipelines remain poor on unadapted KITTI. No same-raw NMS disagreement in measured first passes. Broad failure is not isolated to the TRT10 migration; exact training/input convention and numerical parity remain unresolved.',
            'accuracy_accepted':False,'exact_training_reference_parity':False}
    atomic_write(output/'summary.json',encoded(result));return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,default=ROOT.parent/'datasets/kitti_object_diagnostic_v1')
    p.add_argument('--output',type=Path,default=ROOT/'.recovery/accuracy/kitti-reference-v1');a=p.parse_args()
    summarize(a.dataset.resolve(),a.output.resolve())
