#!/usr/bin/env python3
"""Inspect vertical errors for moderate-difficulty pairs matching KITTI BEV overlap."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import zipfile

from kitti_evaluation import DEVKIT_SHA256, run_binary, sha
from prepare_kitti_validation import atomic_write, encoded

ADAPTER=r'''
#include <fstream>
#include <iomanip>
int main(int argc,char**argv) {
 if(argc!=5)return 2;initGlobals();std::ifstream ids(argv[3]);std::string frame;
 std::ofstream out(argv[4]);out<<std::setprecision(12)<<"[";bool comma=false;
 while(ids>>frame) {
  bool gs,ds,aos=false;vector<bool>ei(3,false),eg(3,false),e3(3,false);
  auto gt=loadGroundtruth(string(argv[1])+"/"+frame+".txt",gs);
  auto det=loadDetections(string(argv[2])+"/"+frame+".txt",aos,ei,eg,e3,ds);
  if(!gs||!ds)return 3;
  for(int cls=0;cls<3;cls++) {
   vector<int>ig,id;vector<tGroundtruth>dc;int n=0;
   cleanData((CLASSES)cls,gt,det,ig,dc,id,n,MODERATE);
   vector<bool>used(det.size(),false);
   for(size_t i=0;i<gt.size();i++) {
    if(ig[i]!=0)continue;int best=-1;double best_overlap=MIN_OVERLAP[GROUND][cls];
    for(size_t j=0;j<det.size();j++) {
     if(id[j]!=0||used[j])continue;double overlap=groundBoxOverlap(det[j],gt[i],-1);
     if(overlap>best_overlap){best=j;best_overlap=overlap;}
    }
    if(best<0)continue;used[best]=true;auto d=det[best];auto g=gt[i];
    if(comma)out<<",";comma=true;
    out<<"{\"frame_id\":\""<<frame<<"\",\"class\":\""<<CLASS_NAMES_CAP[cls]<<"\",\"bev_iou\":"<<best_overlap
       <<",\"iou_3d\":"<<box3DOverlap(d,g,-1)<<",\"camera_center_y_error_m\":"<<(d.t2-d.h/2)-(g.t2-g.h/2)
       <<",\"predicted_height_m\":"<<d.h<<",\"ground_truth_height_m\":"<<g.h<<"}";
   }
  }
 }out<<"]\n";return 0;
}
'''


def diagnose(dataset,evaluation,output):
    devkit=dataset/'.cache/devkit_object.zip'
    if sha(devkit)!=DEVKIT_SHA256:raise ValueError('Devkit hash mismatch')
    with zipfile.ZipFile(devkit) as z:original=z.read('cpp/evaluate_object.cpp').decode()
    source=original[:original.index('void saveAndPlotPlots(')].replace('#include "mail.h"','')+ADAPTER
    output.mkdir(parents=True,exist_ok=True)
    src=output/'diagnostic.cpp';binary=output/'diagnostic'
    if not src.exists() or src.read_text()!=source or not binary.exists():
        atomic_write(src,source.encode());subprocess.run(['g++','-std=c++17','-O2',str(src),'-o',str(binary)],check=True)
    result={'status':'descriptive errors; no coordinate correction or accuracy tuning applied',
            'source_sha256':sha(src),'splits':{}}
    for split in ('tuning','test'):
        raw=output/(split+'-pairs.json')
        run_binary(binary,dataset/'training/label_2',evaluation/'detections',evaluation/(split+'-frames.txt'),raw)
        pairs=json.loads(raw.read_text())
        summary={}
        for cls in ('Car','Pedestrian','Cyclist'):
            values=[p for p in pairs if p['class']==cls]
            summary[cls]={'pairs':len(values),'median_camera_center_y_error_m':statistics.median(p['camera_center_y_error_m'] for p in values) if values else None,
                          'median_abs_camera_center_y_error_m':statistics.median(abs(p['camera_center_y_error_m']) for p in values) if values else None,
                          'median_3d_iou':statistics.median(p['iou_3d'] for p in values) if values else None}
        result['splits'][split]={'summary':summary,'pairs':pairs}
    atomic_write(output/'diagnostic.json',encoded(result));print(json.dumps(result,indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--evaluation',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();diagnose(a.dataset.resolve(),a.evaluation.resolve(),a.output.resolve())
