#!/usr/bin/env python3
"""Run KITTI devkit metrics on frozen ROS predictions with an explicit class mapping."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import zipfile

from kitti_geometry import Calibration, matvec, png_dimensions
from prepare_kitti_validation import atomic_write, encoded, freeze_json

CLASS_MAP = {0:'Car',1:'Pedestrian',2:'Cyclist'}
DEVKIT_SHA256 = 'ce0b76b69c0c5f89690a0d65b7302bbbdb962a0c7e8aba6efc7050d1b04b4cf1'
EDGES = [(i,j) for i in range(8) for j in range(i+1,8) if (i^j) in (1,2,4)]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def camera_prediction(prediction, calibration, image_size):
    """Fit benchmark camera-upright yaw, while projecting actual calibrated corners."""
    center = calibration.to_camera(prediction['center_lidar'])
    length,width,height = prediction['dimensions_lwh']
    yaw = prediction['yaw_lidar']
    c,s = math.cos(yaw),math.sin(yaw)
    corners=[]
    for sx in (-1,1):
        for sy in (-1,1):
            for sz in (-1,1):
                dx,dy,dz=sx*length/2,sy*width/2,sz*height/2
                corners.append(calibration.to_camera([prediction['center_lidar'][0]+c*dx-s*dy,
                    prediction['center_lidar'][1]+s*dx+c*dy,prediction['center_lidar'][2]+dz]))
    near=.001
    points=[p for p in corners if p[2]>=near]
    for a,b in EDGES:
        p,q=corners[a],corners[b]
        if (p[2]<near)!=(q[2]<near):
            t=(near-p[2])/(q[2]-p[2])
            points.append([x+t*(y-x) for x,y in zip(p,q)])
    pixels=[calibration.project_camera(p) for p in points]
    pixels=[p for p in pixels if p is not None]
    if not pixels:
        return None
    bbox=[max(0,min(p[0] for p in pixels)),max(0,min(p[1] for p in pixels)),
          min(image_size[0]-1,max(p[0] for p in pixels)),min(image_size[1]-1,max(p[1] for p in pixels))]
    if bbox[2]<=bbox[0] or bbox[3]<=bbox[1]:
        return None
    heading=matvec(calibration.rotation,[c,s,0])
    ry=math.atan2(-heading[2],heading[0])
    alpha=(ry-math.atan2(center[0],center[2])+math.pi)%(2*math.pi)-math.pi
    return {'type':CLASS_MAP[prediction['class_id']], 'bbox':bbox,'hwl':[height,width,length],
            'bottom_center':[center[0],center[1]+height/2,center[2]], 'rotation_y':ry,
            'alpha':alpha,'score':prediction['score'],
            'heading_vertical_component':heading[1]}


def prediction_line(box):
    values=[0,0,box['alpha']]+box['bbox']+box['hwl']+box['bottom_center']+[box['rotation_y'],box['score']]
    return box['type']+' '+' '.join(f'{x:.9g}' for x in values)+'\n'


# This adapter calls upstream overlap, cleanData, matching and AP unchanged.
# No server file paths, email, shell plotting, submission or deletion code is used.
ADAPTER = r'''
#include <fstream>
#include <iomanip>
#include <stdexcept>
int main(int argc,char**argv) {
  if(argc!=5) { std::cerr<<"usage: evaluator GT_DIR DET_DIR IDS_FILE OUTPUT\n"; return 2; }
  initGlobals();
  std::ifstream ids(argv[3]); std::vector<std::string> frames; std::string frame;
  while(ids>>frame) frames.push_back(frame);
  if(frames.empty()) return 3;
  vector<vector<tGroundtruth>> gt; vector<vector<tDetection>> det;
  bool aos=false; vector<bool> ei(3,false),eg(3,false),e3(3,false);
  for(const auto&f:frames) {
    bool gs,ds;
    gt.push_back(loadGroundtruth(string(argv[1])+"/"+f+".txt",gs));
    det.push_back(loadDetections(string(argv[2])+"/"+f+".txt",aos,ei,eg,e3,ds));
    if(!gs||!ds) return 4;
  }
  std::ofstream output(argv[4]); output<<std::setprecision(12);
  if(!output) return 5;
  output<<"{\"classes\":{";
  for(int cls=0;cls<3;cls++) {
    if(cls) output<<","; output<<"\""<<CLASS_NAMES_CAP[cls]<<"\":{";
    for(int metric=1;metric<=2;metric++) {
      if(metric>1)output<<","; output<<"\""<<(metric==1?"bev":"3d")<<"\":{";
      auto overlap=metric==1?groundBoxOverlap:box3DOverlap;
      for(int level=0;level<3;level++) {
        if(level)output<<",";
        const char*name=level==0?"easy":level==1?"moderate":"hard";
        vector<double> precision,orientation;
        FILE* temporary=tmpfile(); if(!temporary)return 6;
        eval_class(temporary,nullptr,(CLASSES)cls,gt,det,false,overlap,precision,orientation,(DIFFICULTY)level,(METRIC)metric);
        fclose(temporary);
        double ap=0; for(int i=1;i<=40;i++)ap+=precision[i]; ap/=40.;
        tPrData totals; int n_gt=0;
        output<<"\""<<name<<"\":{\"frames\":[";
        for(size_t i=0;i<frames.size();i++) {
          vector<int> ig,id;vector<tGroundtruth>dc;
          cleanData((CLASSES)cls,gt[i],det[i],ig,dc,id,n_gt,(DIFFICULTY)level);
          auto count=computeStatistics((CLASSES)cls,gt[i],det[i],dc,ig,id,true,overlap,(METRIC)metric,false,0.0);
          totals.tp+=count.tp;totals.fp+=count.fp;totals.fn+=count.fn;
          if(i)output<<",";
          output<<"{\"frame_id\":\""<<frames[i]<<"\",\"tp\":"<<count.tp<<",\"fp\":"<<count.fp<<",\"fn\":"<<count.fn<<"}";
        }
        output<<"],\"gt\":"<<n_gt<<",\"tp\":"<<totals.tp<<",\"fp\":"<<totals.fp<<",\"fn\":"<<totals.fn
              <<",\"precision\":"<<((totals.tp+totals.fp)?double(totals.tp)/(totals.tp+totals.fp):0.)
              <<",\"recall\":"<<((totals.tp+totals.fn)?double(totals.tp)/(totals.tp+totals.fn):0.)
              <<",\"ap_r40\":"<<ap<<"}";
      } output<<"}";
    }output<<"}";
  }output<<"}}\n";return 0;
}
'''


def build_evaluator(devkit, directory):
    if sha(devkit)!=DEVKIT_SHA256:
        raise ValueError('Devkit hash mismatch')
    with zipfile.ZipFile(devkit) as archive:
        original=archive.read('cpp/evaluate_object.cpp').decode()
    prefix=original[:original.index('void saveAndPlotPlots(')]
    prefix=prefix.replace('#include "mail.h"','')
    source=prefix+ADAPTER
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/'evaluator.cpp'
    binary=directory/'evaluator'
    changed=not path.exists() or path.read_text()!=source
    if changed:
        atomic_write(path,source.encode())
    if changed or not binary.exists():
        subprocess.run(['g++','-std=c++17','-O2',str(path),'-o',str(binary)],check=True)
    # The project can reside on a noexec data drive; copy the verified binary to /tmp
    # at execution time, not to another permanent source installation.
    return binary,{'devkit_sha256':DEVKIT_SHA256,'original_source_sha256':hashlib.sha256(original.encode()).hexdigest(),
                  'adapter_source_sha256':sha(path),'binary_sha256':sha(binary),
                  'metric_code':'upstream prefix unchanged except unused mail.h include removal; custom file/JSON adapter',
                  'compiler':subprocess.check_output(['g++','--version'],text=True).splitlines()[0]}


def run_binary(binary, gt, det, ids, output):
    import tempfile,shutil,os
    with tempfile.TemporaryDirectory(prefix='pp-kitti-evaluator-') as temporary:
        executable=Path(temporary)/'evaluator'
        shutil.copyfile(binary,executable);os.chmod(executable,0o700)
        subprocess.run([str(executable),str(gt),str(det),str(ids),str(output)],check=True)


def evaluate(dataset, predictions, output):
    manifest=json.loads((dataset/'manifest.json').read_text())
    index=json.loads((predictions/'prediction_manifest.json').read_text())
    run=json.loads((predictions/'run.json').read_text())
    if run['dataset_manifest_sha256']!=sha(dataset/'manifest.json') or index['run_sha256']!=sha(predictions/'run.json'):
        raise ValueError('Prediction/dataset identity mismatch')
    if {f['frame_id'] for f in manifest['frames']}!={f['frame_id'] for f in index['frames']}:
        raise ValueError('Incomplete or unexpected prediction set')
    hashes={f['frame_id']:f['sha256'] for f in index['frames']}
    output.mkdir(parents=True,exist_ok=True)
    policy={'schema_version':1,'name':'KITTI-compatible diagnostic Car/Pedestrian/Cyclist baseline',
      'mapping':{'Vehicle':'Car','Pedestrian':'Pedestrian','Cyclist':'Cyclist'},
      'vehicle_mapping_limit':'Evaluates Car compatibility; not all-vehicle accuracy. Original Van/Truck labels are not merged.',
      'overlap':{'Car':.7,'Pedestrian':.5,'Cyclist':.5},'difficulties':'upstream KITTI cleanData',
      'matching_and_ignore':'unmodified upstream KITTI computeStatistics for each metric',
      'visibility':'near-plane clipped projected full calibrated corners; require nonempty image-clipped rectangle',
      'camera_representation':'center transformed exactly; camera-upright dimensions/yaw fit from transformed heading. Small calibration tilt cannot be represented by KITTI yaw-only format.',
      'spatial_filter':'none for GT or predictions beyond camera visibility; model-range coverage reported separately',
      'threshold':'all published final ROS detections; engine decode minimum approximately 0.1; NMS/top-N unchanged',
      'ap':'upstream 41 precision entries; AP_R40 mean entries 1..40; sparse diagnostic samples limit interpretation',
      'dataset_manifest_sha256':sha(dataset/'manifest.json'),'prediction_manifest_sha256':sha(predictions/'prediction_manifest.json'),
      'run':run,'evaluator_tool_sha256':sha(Path(__file__))}
    freeze_json(output/'policy.json',policy)
    binary,implementation=build_evaluator(dataset/'.cache/devkit_object.zip',output/'build')
    visibility=[]
    for frame in manifest['frames']:
        f=frame['frame_id']; prediction_path=predictions/f'predictions/{f}.json'
        if sha(prediction_path)!=hashes[f]:raise ValueError('Prediction hash mismatch: '+f)
        record=json.loads(prediction_path.read_text())
        if record['cloud_sha256']!=frame['assets']['velodyne']['sha256'] or record['run_sha256']!=sha(predictions/'run.json'):
            raise ValueError('Per-frame prediction provenance mismatch')
        for kind in ('label_2','calib','image_2'):
            asset=frame['assets'][kind]
            if sha(dataset/asset['path'])!=asset['sha256']:raise ValueError('Ground-truth/calibration asset changed')
        calibration=Calibration((dataset/frame['assets']['calib']['path']).read_text())
        image_size=png_dimensions((dataset/frame['assets']['image_2']['path']).read_bytes())
        converted=[camera_prediction(p,calibration,image_size) for p in record['detections']]
        visible=[p for p in converted if p is not None]
        atomic_write(output/f'detections/{f}.txt',''.join(prediction_line(p) for p in visible).encode())
        visibility.append({'frame_id':f,'raw_predictions':len(converted),'camera_visible':len(visible),
                           'excluded_outside_camera':len(converted)-len(visible),
                           'max_heading_vertical_component':max([abs(p['heading_vertical_component']) for p in visible],default=0)})
    report={'schema_version':1,'policy_sha256':sha(output/'policy.json'),'implementation':implementation,
            'visibility':visibility,'splits':{},'status':'diagnostic-baseline-measured; acceptance-and-independent-inference-parity-pending'}
    for split in ('tuning','test'):
        selected=[f for f in manifest['frames'] if f['split']==split]
        ids=output/(split+'-frames.txt');atomic_write(ids,('\n'.join(f['frame_id'] for f in selected)+'\n').encode())
        raw=output/(split+'-metrics.json')
        run_binary(binary,dataset/'training/label_2',output/'detections',ids,raw)
        metrics=json.loads(raw.read_text())
        # Scenario counts overlap deliberately; they are separate diagnostic breakdowns.
        for cls,class_metrics in metrics['classes'].items():
            for metric,difficulties in class_metrics.items():
                for level,values in difficulties.items():
                    values['scenarios']={}
                    for tag in sorted({tag for f in selected for tag in f['scenarios']}):
                        frames={f['frame_id'] for f in selected if tag in f['scenarios']}
                        counts={k:sum(item[k] for item in values['frames'] if item['frame_id'] in frames) for k in ('tp','fp','fn')}
                        counts['frames']=len(frames);values['scenarios'][tag]=counts
        report['splits'][split]=metrics
    freeze_json(output/'report.json',report)
    print(json.dumps({split:{cls:{metric:values['moderate'] for metric,values in metrics.items()}
                    for cls,metrics in results['classes'].items()} for split,results in report['splits'].items()},indent=2))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--predictions',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    evaluate(args.dataset.resolve(),args.predictions.resolve(),args.output.resolve())


if __name__=='__main__':main()
