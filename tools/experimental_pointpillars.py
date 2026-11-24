#!/usr/bin/env python3
"""Experimental offline PointPillars runner; never changes the production detector.

Requires user-supplied zhulf0804/PointPillars source and checkpoint, plus a frozen
JSON {"inputs": [{"input": "/absolute/scan.bin", "sha256": "..."}]} manifest.
Each input must be little-endian float32 XYZI. Example:
  python tools/experimental_pointpillars.py --source /path/PointPillars \
    --checkpoint /path/epoch_160.pth --expected-source-commit COMMIT \
    --expected-checkpoint-sha256 SHA --input-manifest manifest.json \
    --input /absolute/scan.bin --output /new/result-directory --full360 --repeats 3

Install nothing globally: use an existing environment with NumPy and PyTorch.
CPU first-arrival voxelization and polygon NMS replace compiled extensions;
numerical parity is unverified. Experimental results need independent matched-GT
evaluation. Full360 sector boundaries can miss/duplicate objects. Model source is
trusted executable Python; a hash pins identity, not safety or accuracy.
"""
import argparse, hashlib, json, math, os, subprocess, sys, time, types
from pathlib import Path
import numpy as np
import torch
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from ouster_gt_evaluation import box_iou

def voxel_numpy(points, size, bounds, max_points, max_voxels):
    size=np.asarray(size,dtype=np.float32); bounds=np.asarray(bounds,dtype=np.float32)
    grid=np.round((bounds[3:]-bounds[:3])/size).astype(np.int32)
    valid=np.isfinite(points).all(1)
    points=points[valid]
    coords=np.floor((points[:,:3]-bounds[:3])/size).astype(np.int32)
    valid=((coords>=0)&(coords<grid)).all(1)
    points=points[valid]; coords=coords[valid]
    voxels=np.zeros((max_voxels,max_points,4),np.float32)
    outcoords=np.zeros((max_voxels,3),np.int32); counts=np.zeros(max_voxels,np.int32)
    lookup={}
    for point,coord in zip(points,coords):
        key=tuple(coord)
        idx=lookup.get(key)
        if idx is None:
            if len(lookup)>=max_voxels: continue
            idx=len(lookup); lookup[key]=idx; outcoords[idx]=coord
        if counts[idx]<max_points:
            voxels[idx,counts[idx]]=point; counts[idx]+=1
    n=len(lookup)
    return voxels[:n],outcoords[:n],counts[:n]

class Voxelization(torch.nn.Module):
    def __init__(self,voxel_size,point_cloud_range,max_num_points,max_voxels):
        super().__init__(); self.settings=(voxel_size,point_cloud_range,max_num_points,max_voxels)
    def forward(self,points):
        size,bounds,n,m=self.settings
        out=voxel_numpy(points.detach().cpu().numpy(),size,bounds,n,m[0 if self.training else 1])
        if len(out[0])==0: raise ValueError('No valid in-ROI pillars')
        return tuple(torch.from_numpy(v).to(points.device) for v in out)

def nms_cuda(boxes,scores,thresh,pre_maxsize=None,post_max_size=None):
    arr=boxes.detach().cpu().numpy(); sc=scores.detach().cpu().numpy()
    order=np.argsort(-sc,kind='stable').tolist()
    if pre_maxsize is not None: order=order[:pre_maxsize]
    adapted=[[(r[0]+r[2])/2,(r[1]+r[3])/2,0.,r[2]-r[0],r[3]-r[1],1.,-r[4]] for r in arr]
    adapted=[list(map(float,b)) for b in adapted]
    keep=[]
    while order:
        i=order.pop(0);keep.append(i)
        order=[j for j in order if box_iou(adapted[i],adapted[j])['bev']<=thresh]
    if post_max_size is not None:keep=keep[:post_max_size]
    return torch.tensor(keep,dtype=torch.long,device=boxes.device)

def unsupported(*args,**kwargs):raise RuntimeError('Training functionality intentionally unavailable')
def load_model(source,checkpoint,device):
    package=types.ModuleType('pointpillars');package.__path__=[str(source/'pointpillars')];sys.modules['pointpillars']=package
    sub=types.ModuleType('pointpillars.model');sub.__path__=[str(source/'pointpillars/model')];sys.modules[sub.__name__]=sub
    ops=types.ModuleType('pointpillars.ops');ops.Voxelization=Voxelization;ops.nms_cuda=nms_cuda;sys.modules[ops.__name__]=ops
    utils=types.ModuleType('pointpillars.utils');utils.limit_period=lambda val,offset=.5,period=math.pi:val-torch.floor(val/period+offset)*period
    utils.iou2d_nearest=unsupported;sys.modules[utils.__name__]=utils
    from pointpillars.model.pointpillars import PointPillars
    model=PointPillars()
    state=torch.load(checkpoint,map_location='cpu',weights_only=True)
    model.load_state_dict(state,strict=True)
    return model.eval().to(device)

def adapt_box(b):return [float(b[0]),float(b[1]),float(b[2]+b[5]/2),float(b[3]),float(b[4]),float(b[5]),float(-b[6])]
def rotate_points(points, degrees):
    angle=math.radians(degrees);c,s=math.cos(angle),math.sin(angle)
    out=points.copy();out[:,0]=c*points[:,0]-s*points[:,1];out[:,1]=s*points[:,0]+c*points[:,1]
    return out

def inverse_box(box,degrees):
    angle=math.radians(degrees);c,s=math.cos(angle),math.sin(angle)
    x,y=box[:2]
    return [c*x+s*y,-s*x+c*y,*box[2:6],box[6]-angle]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

PINNED_SOURCE_COMMIT='620e6b0d07e4cb37b7b0114f26b934e8be92a0ba'

def git(source,*args):
    return subprocess.check_output(['git','-C',str(source),*args],text=True).strip()

def validate_source(source,expected):
    """Pin the supported architecture and reject tracked/untracked source changes."""
    source=Path(source).resolve()
    if expected!=PINNED_SOURCE_COMMIT:
        raise ValueError('Only the independently reviewed upstream commit is supported')
    if Path(git(source,'rev-parse','--show-toplevel')).resolve()!=source:
        raise ValueError('Source must be the root of its own Git checkout')
    if git(source,'rev-parse','HEAD')!=expected or git(source,'status','--porcelain','--untracked-files=all'):
        raise ValueError('Source commit mismatch or dirty source checkout')
    # Ignore rules cannot hide modified tracked code; hash every tracked source.
    names=subprocess.check_output(['git','-C',str(source),'ls-files','-z']).decode().split('\0')
    tracked={name for name in names if name}
    for path in (source/'pointpillars').rglob('*'):
        if path.is_file() and path.suffix in {'.py','.so','.pyd'} and str(path.relative_to(source)) not in tracked:
            raise ValueError('Untracked executable source, including ignored files: '+str(path))
    return {name:sha(source/name) for name in tracked}

def validate_inputs(manifest_path,filenames):
    raw=json.loads(Path(manifest_path).read_text())
    entries=raw['inputs'] if isinstance(raw,dict) else raw
    if not isinstance(entries,list) or not entries:
        raise ValueError('Manifest must contain a nonempty inputs list')
    frozen={}
    for entry in entries:
        path=Path(entry['input'])
        digest=entry['sha256']
        if not path.is_absolute() or not path.is_file() or path.is_symlink():
            raise ValueError('Manifest inputs must be absolute regular non-symlink files')
        path=str(path.resolve())
        if path in frozen or not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Duplicate input or malformed SHA256')
        if Path(path).stat().st_size==0 or Path(path).stat().st_size%16:
            raise ValueError('Input must contain complete nonempty float32 XYZI records')
        if sha(path)!=digest:raise ValueError('Input hash mismatch: '+path)
        frozen[path]=digest
    selected=[str(Path(p).resolve()) for p in filenames]
    if len(set(selected))!=len(selected) or set(selected)!=set(frozen):
        raise ValueError('Requested inputs must match the manifest exactly, without duplicates')
    return [(p,frozen[p]) for p in selected]

def stable_points(path,digest):
    """Infer from the exact hashed byte snapshot, then check disk again afterwards."""
    data=Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Input changed before snapshot')
    points=np.frombuffer(data,dtype='<f4').reshape(-1,4).copy()
    count=len(points)
    return points[np.isfinite(points).all(1)&np.any(points[:,:3]!=0,axis=1)],count

def infer(model,points,full360):
    boxes=[]
    for degrees in ([0,90,180,270] if full360 else [0]):
        view=rotate_points(points,degrees)
        with torch.inference_mode():result=model([torch.from_numpy(view)],mode='test')[0]
        if isinstance(result,dict):
            for b,c,s in zip(result['lidar_bboxes'],result['labels'],result['scores']):
                local=adapt_box(b);azimuth=math.atan2(local[1],local[0])
                if full360 and not(local[0]>0 and -math.pi/4<=azimuth<math.pi/4):continue
                boxes.append({'class_id':{0:1,1:2,2:0}[int(c)],'score':float(s),'box':inverse_box(local,degrees),'upstream_box':b.tolist(),'view_degrees':degrees})
    return boxes

def atomic_json(path,value):
    # Parent directory is exclusively reserved; final files are never overwritten.
    temp=path.with_suffix('.tmp')
    with temp.open('w') as handle:
        json.dump(value,handle,indent=2,allow_nan=False);handle.flush();os.fsync(handle.fileno())
    temp.replace(path)

def run(args):
    if not 1<=args.repeats<=100 or not 1<=args.threads<=256:
        raise ValueError('Repeats must be 1..100 and threads 1..256')
    source=args.source.resolve();checkpoint=args.checkpoint.resolve()
    source_hashes=validate_source(source,args.expected_source_commit)
    if sha(checkpoint)!=args.expected_checkpoint_sha256:raise ValueError('Checkpoint hash mismatch')
    manifest_hash=sha(args.input_manifest)
    inputs=validate_inputs(args.input_manifest,args.input)
    # mkdir is atomic and rejects any existing destination, even an empty one.
    args.output.mkdir(parents=False,exist_ok=False)
    torch.set_num_threads(args.threads);torch.manual_seed(20261123);torch.use_deterministic_algorithms(True)
    metadata={'status':'partial','expected_records':len(inputs)*args.repeats,'source_commit':args.expected_source_commit,'source_hashes':source_hashes,'checkpoint_sha256':args.expected_checkpoint_sha256,'adapter_sha256':sha(__file__),'input_manifest_sha256':manifest_hash,'torch':torch.__version__,'device':'cpu','threads':args.threads,'seed':20261123,'full360':args.full360,'preprocessing':'finite XYZI and nonzero original XYZ; intensity unchanged; no height shift','view_policy':'fixed [0,90,180,270] degrees; predicted local center azimuth [-45,45)' if args.full360 else 'original forward view','adapter':'CPU first-arrival voxelization and polygon NMS; framework extension parity unverified','records':[]}
    atomic_json(args.output/'checkpoint.json',metadata)
    try:
        model=load_model(source,checkpoint,'cpu')
        for filename,digest in inputs:
            for repeat in range(args.repeats):
                points,count=stable_points(filename,digest);start=time.perf_counter()
                boxes=infer(model,points,args.full360)
                if sha(filename)!=digest:raise ValueError('Input changed during inference')
                metadata['records'].append({'input':filename,'sha256':digest,'repeat':repeat,'input_count':count,'valid_count':len(points),'seconds':time.perf_counter()-start,'boxes':boxes})
                atomic_json(args.output/'checkpoint.json',metadata)
        if validate_source(source,args.expected_source_commit)!=source_hashes or sha(checkpoint)!=args.expected_checkpoint_sha256 or sha(args.input_manifest)!=manifest_hash:
            raise ValueError('Source, checkpoint or manifest changed during inference')
        for filename,digest in inputs:
            if sha(filename)!=digest:raise ValueError('Input changed before completion')
        metadata['status']='complete';atomic_json(args.output/'complete.json',metadata)
    except Exception as error:
        atomic_json(args.output/'failure.json',{'status':'failed','error':str(error),'completed_records':len(metadata['records'])})
        raise

def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--expected-source-commit',required=True);parser.add_argument('--expected-checkpoint-sha256',required=True)
    parser.add_argument('--input-manifest',type=Path,required=True);parser.add_argument('--input',action='append',required=True)
    parser.add_argument('--output',type=Path,required=True,help='New exclusive output directory; parent must exist')
    parser.add_argument('--full360',action='store_true');parser.add_argument('--repeats',type=int,default=1);parser.add_argument('--threads',type=int,default=4)
    run(parser.parse_args())
if __name__=='__main__':main()
