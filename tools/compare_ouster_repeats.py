#!/usr/bin/env python3
"""Measure repeat matching from frozen Ouster raw outputs; no new inference."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import numpy as np
from kitti_reference import match_rows
from compare_ouster_features import json_save, sha


def run(root):
    recipe=json.loads((root/'recipe.json').read_text())
    for name,checksum in json.loads((root/'raw-index.json').read_text()).items():
        if sha(root/name)!=checksum:
            raise ValueError('Raw evidence changed')
    comparisons={}
    for variant in recipe['variants']:
        pairs=[]
        for frame in recipe['frames']:
            identifier=frame['inputs'][variant]['id']
            def rows(repeat):
                values=np.fromfile(root/'raw'/f'{identifier}-{repeat}.bin',dtype='<f4').reshape(-1,9)
                valid=np.isfinite(values).all(axis=1)&(values[:,3:6]>0).all(axis=1)&np.isin(values[:,7],[0,1,2])
                return [tuple(row) for row in values[valid].astype(float)],int((~valid).sum())
            first,invalid0=rows(0)
            for repeat in range(1,recipe['repeats']):
                other,invalid=rows(repeat)
                pairs.append({'frame_id':frame['frame_id'],'repeat':repeat,'invalid_baseline_rows':invalid0,
                              'invalid_repeat_rows':invalid,**match_rows(first,other)})
        comparisons[variant]={'median_unique_valid_raw_match_fraction':statistics.median(p['match_fraction_of_larger'] for p in pairs) if pairs else None,'pairs':pairs}
    result={'recipe_sha256':sha(root/'recipe.json'),'tool_sha256':sha(Path(__file__)),
            'matcher_module_sha256':sha(Path(__file__).with_name('kitti_reference.py')),
            'comparisons':comparisons,
            'limit':'Diagnostic tolerance 0.001 for coordinates/dimensions/wrapped yaw/score. Invalid raw rows excluded only for this metric; production rejects their entire frame.'}
    json_save(root/'repeatability.json',result)
    print(json.dumps({v:r['median_unique_valid_raw_match_fraction'] for v,r in comparisons.items()},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'.recovery/accuracy/ouster-feature-v1')
    args=parser.parse_args()
    run(args.output.resolve())
