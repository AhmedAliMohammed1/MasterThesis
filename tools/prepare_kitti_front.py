#!/usr/bin/env python3
"""Official KITTI synced drive 0005 -> full-cloud ROS 2 bag and frontal camera video."""
import argparse
from array import array
import hashlib
import heapq
import io
import json
from pathlib import Path, PurePosixPath
import sqlite3
import subprocess
import zipfile
import numpy as np
from prepare_kitti_demo import timestamp_ns
from export_ouster_camera import encoder_command
from prepare_ouster_demo import digest

DRIVE='2011_09_26_drive_0005_sync'
PREFIX='2011_09_26/'+DRIVE+'/'
ASSETS={
 '2011_09_26_drive_0005_sync.zip':{'url':'https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data/2011_09_26_drive_0005/2011_09_26_drive_0005_sync.zip','bytes':645940900,'sha256':'eaa3635b6ad6a707a8bab53ca38567ada8c78eb743e96d558497872fa436c136'},
 '2011_09_26_calib.zip':{'url':'https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data/2011_09_26_calib.zip','bytes':4068,'sha256':'e0108cfd000cf802c14ed94fba38601185c792e5640abba015a34b7a85b812e0'},
}


def archives(root):
    for name,identity in ASSETS.items():
        final=root/name;pending=root/(name+'.part')
        if not final.exists():
            if not pending.exists() or pending.stat().st_size!=identity['bytes']:
                subprocess.run(['curl','--fail','--location','--retry','5','--connect-timeout','20','--continue-at','-',identity['url'],'--output',str(pending)],check=True)
            if pending.stat().st_size!=identity['bytes'] or digest(pending)!=identity['sha256']:
                raise ValueError('Download identity mismatch: '+name)
            pending.rename(final)
        if final.stat().st_size!=identity['bytes'] or digest(final)!=identity['sha256']:
            raise ValueError('Source archive changed: '+name)


def stamp(header,value,frame):
    header.frame_id=frame
    header.stamp.sec=value//10**9
    header.stamp.nanosec=value%10**9


def camera_projection(text):
    for line in text.splitlines():
        if line.startswith('P_rect_02:'):
            values=[float(x) for x in line.split(':',1)[1].split()]
            if len(values)!=12 or not np.isfinite(values).all():raise ValueError('Invalid camera projection')
            return values
    raise ValueError('No left color camera projection')


def prepare(root):
    import rosbag2_py
    from rclpy.serialization import serialize_message
    from sensor_msgs.msg import PointCloud2,PointField,Image,CameraInfo
    from PIL import Image as PILImage
    root.mkdir(parents=True,exist_ok=True)
    archives(root)
    target=root/'rosbag'
    recipe={'drive':DRIVE,'archives':ASSETS,'tool_sha256':digest(Path(__file__)),
            'clouds':'All original little-endian FLOAT32 XYZI bits, full 360 degree scan, no crop/sampling/scaling',
            'camera':'Original image_02 forward-facing synced/rectified left-color frames, decoded losslessly',
            'clock':'Naive KITTI timestamp strings encoded as UTC for deterministic epoch; original strings retained',
            'frame':'velodyne','camera_frame':'kitti_rectified_reference',
            'camera_info':'Official P_rect_02 maps common rectified KITTI reference coordinates into image_02; no invented TF',
            'accuracy_validated':False,'ground_truth_published':False}
    manifest=root/'manifest.json'
    if manifest.exists():
        current=json.loads(manifest.read_text())
        if current['recipe']!=recipe:raise ValueError('Existing preparation recipe changed')
        for name,checksum in current['files'].items():
            if digest(root/name)!=checksum:raise ValueError('Prepared data changed: '+name)
        return current
    if target.exists() or (root/'rosbag.pending').exists():raise ValueError('Unindexed/interrupted bag exists; preserve/inspect it')
    pending=root/'rosbag.pending'
    camera=root/'camera';camera.mkdir(exist_ok=True)
    calibration=root/'calibration';calibration.mkdir(exist_ok=True)
    with zipfile.ZipFile(root/'2011_09_26_calib.zip') as source:
        for member in source.infolist():
            path=PurePosixPath(member.filename)
            if '..' in path.parts or path.is_absolute() or member.is_dir():raise ValueError('Unsafe calibration entry')
            (calibration/path.name).write_bytes(source.read(member))
    projection=camera_projection((calibration/'calib_cam_to_cam.txt').read_text())
    fields=[PointField(name=name,offset=index*4,datatype=PointField.FLOAT32,count=1) for index,name in enumerate(('x','y','z','intensity'))]
    records=[];cloud_stats=[]
    with zipfile.ZipFile(root/'2011_09_26_drive_0005_sync.zip') as source:
        for member in source.infolist():
            path=PurePosixPath(member.filename)
            if '..' in path.parts or path.is_absolute():raise ValueError('Unsafe source ZIP entry')
        clouds=sorted(m for m in source.namelist() if m.startswith(PREFIX+'velodyne_points/data/') and m.endswith('.bin'))
        images=sorted(m for m in source.namelist() if m.startswith(PREFIX+'image_02/data/') and m.endswith('.png'))
        cloud_text=source.read(PREFIX+'velodyne_points/timestamps.txt').decode()
        image_text=source.read(PREFIX+'image_02/timestamps.txt').decode()
        cloud_times=[timestamp_ns(t) for t in cloud_text.splitlines() if t.strip()]
        image_times=[timestamp_ns(t) for t in image_text.splitlines() if t.strip()]
        if len(clouds)!=len(cloud_times) or len(images)!=len(image_times) or len(clouds)!=len(images):
            raise ValueError('Synced stream count mismatch')
        (root/'cloud_timestamps.txt').write_text(cloud_text);(camera/'timestamps.txt').write_text(image_text)
        writer=rosbag2_py.SequentialWriter()
        writer.open(rosbag2_py.StorageOptions(uri=str(pending),storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
        types={'/point_cloud':'sensor_msgs/msg/PointCloud2','/image':'sensor_msgs/msg/Image','/camera_info':'sensor_msgs/msg/CameraInfo'}
        for ident,(topic,typ) in enumerate(types.items(),1):
            writer.create_topic(rosbag2_py.TopicMetadata(id=ident,name=topic,type=typ,serialization_format='cdr'))
        try:
            # Process paired source frames, then emit by sensor timestamp to preserve inter-stream timing.
            for index,(cloud_name,image_name) in enumerate(zip(clouds,images)):
                payload=source.read(cloud_name)
                if len(payload)%16:raise ValueError('Invalid XYZI byte count')
                points=np.frombuffer(payload,dtype='<f4').reshape(-1,4)
                if len(points)>204800:raise ValueError('Cloud exceeds current engine capacity; no implicit sampling')
                message=PointCloud2();stamp(message.header,cloud_times[index],'velodyne')
                message.height=1;message.width=len(points);message.fields=fields
                message.is_bigendian=False;message.point_step=16;message.row_step=len(payload)
                message.data=array('B',payload);message.is_dense=bool(np.isfinite(points).all())
                image_payload=source.read(image_name)
                (camera/f'{index:06d}.png').write_bytes(image_payload)
                decoded=PILImage.open(io.BytesIO(image_payload)).convert('RGB')
                img=Image();stamp(img.header,image_times[index],'kitti_rectified_reference')
                img.height=decoded.height;img.width=decoded.width;img.encoding='rgb8';img.is_bigendian=False
                img.step=decoded.width*3;img.data=array('B',decoded.tobytes())
                info=CameraInfo();info.header=img.header;info.width=img.width;info.height=img.height
                info.distortion_model='plumb_bob';info.d=[0.]*5
                info.k=[projection[r*4+c] for r in range(3) for c in range(3)]
                info.r=[1.,0.,0.,0.,1.,0.,0.,0.,1.];info.p=projection
                paired=[(cloud_times[index],'/point_cloud',serialize_message(message)),(image_times[index],'/image',serialize_message(img)),(image_times[index],'/camera_info',serialize_message(info))]
                for timestamp,topic,data in sorted(paired,key=lambda item:item[0]):writer.write(topic,data,timestamp)
                cloud_stats.append({'index':index,'points':len(points),'xyzi_sha256':hashlib.sha256(payload).hexdigest(),
                                    'finite_points':int(np.isfinite(points).all(axis=1).sum()),'zero_xyz_points':int((points[:,:3]==0).all(axis=1).sum()),
                                    'intensity_min':float(points[:,3].min()),'intensity_max':float(points[:,3].max()),
                                    'cloud_timestamp_ns':cloud_times[index],'image_timestamp_ns':image_times[index],
                                    'camera_png_sha256':hashlib.sha256(image_payload).hexdigest()})
        finally:writer.close()
    pending.rename(target)
    # Camera-only concat at native timestamps; no resize/crop (one padding row for H.264).
    lines=['ffconcat version 1.0']
    for index,value in enumerate(image_times):
        duration=(image_times[index+1]-value)/1e9 if index+1<len(image_times) else float(np.median(np.diff(image_times)))/1e9
        lines.extend([f"file '{index:06d}.png'",'option framerate 1000',f'duration {duration:.9f}'])
    lines.extend([f"file '{len(image_times)-1:06d}.png'",'option framerate 1000'])
    (camera/'timeline.ffconcat').write_text('\n'.join(lines)+'\n')
    counts=[s['points'] for s in cloud_stats]
    result={'recipe':recipe,'frames':cloud_stats,'cloud_count':len(cloud_stats),'camera_count':len(images),
            'point_count_min':min(counts),'point_count_max':max(counts),'point_count_median':float(np.median(counts)),
            'cloud_duration_seconds':(cloud_times[-1]-cloud_times[0])/1e9,
            'camera_duration_seconds':(image_times[-1]-image_times[0]+int(np.median(np.diff(image_times))))/1e9,
            'camera_width':img.width,'camera_height':img.height,
            'camera_minus_lidar_seconds_min':min((a-b)/1e9 for a,b in zip(image_times,cloud_times)),
            'camera_minus_lidar_seconds_max':max((a-b)/1e9 for a,b in zip(image_times,cloud_times)),
            'files':{str(p.relative_to(root)):digest(p) for directory in (target,camera,calibration) for p in directory.rglob('*') if p.is_file()}}
    manifest.write_text(json.dumps(result,indent=2)+'\n')
    return result


def video(root,manifest,encoder_image):
    camera=root/'camera';final=camera/'front_camera.mp4';index=camera/'video.json'
    if final.exists():
        if json.loads(index.read_text())['sha256']!=digest(final):raise ValueError('Video changed')
        return final
    command,mount=encoder_command(camera,encoder_image,'ffmpeg',[])
    prefix=Path(mount) if mount else camera
    pending=camera/'front_camera.pending.mp4'
    command+=['-hide_banner','-loglevel','warning','-y','-f','concat','-safe','0','-i',str(prefix/'timeline.ffconcat'),
              '-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2,fps=30','-t',str(manifest['camera_duration_seconds']),
              '-c:v','libx264','-crf','20','-preset','medium','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(prefix/pending.name)]
    with (camera/'ffmpeg.log').open('w') as logfile:subprocess.run(command,stdout=logfile,stderr=subprocess.STDOUT,check=True)
    probe,mount=encoder_command(camera,encoder_image,'ffprobe',[])
    probe+=['-v','error','-show_entries','stream=codec_name,width,height:format=duration','-of','json',str((Path(mount) if mount else camera)/pending.name)]
    metadata=json.loads(subprocess.check_output(probe,text=True));stream=metadata['streams'][0]
    if stream['width']!=manifest['camera_width'] or stream['height'] not in (manifest['camera_height'],manifest['camera_height']+1) or abs(float(metadata['format']['duration'])-manifest['camera_duration_seconds'])>.1:
        raise ValueError('Video dimensions/timing mismatch')
    pending.rename(final);index.write_text(json.dumps({'sha256':digest(final),'probe':metadata,'original_resolution_preserved':True,'padding_only':True},indent=2)+'\n')
    return final


def main():
    import fcntl
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--encoder-image',default='pp-infer:demo-tools')
    args=parser.parse_args();root=args.data_dir.resolve();root.mkdir(parents=True,exist_ok=True)
    with (root/'.prepare.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        manifest=prepare(root)
        print(video(root,manifest,args.encoder_image),flush=True)
        print(json.dumps({k:v for k,v in manifest.items() if k not in ('frames','files')},indent=2))


if __name__=='__main__':main()
