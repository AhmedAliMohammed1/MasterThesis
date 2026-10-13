#!/usr/bin/env python3
"""Export PNG preview frames and record-time camera videos from the Ouster bags."""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
from prepare_ouster_demo import digest


def timeline(stamps,start,end):
    if not stamps or start>stamps[0] or end<stamps[-1] or end<=start:
        raise ValueError('Camera frames lie outside bag timeline')
    if any(b<=a for a,b in zip(stamps,stamps[1:])):
        raise ValueError('Camera record times must increase')
    records=[]
    if stamps[0]>start:records.append(('black.png',(stamps[0]-start)/1e9))
    for index,stamp in enumerate(stamps):
        until=stamps[index+1] if index+1<len(stamps) else end
        if until>stamp:records.append((f'{index:06d}.png',(until-stamp)/1e9))
    lines=['ffconcat version 1.0']
    for filename,duration in records:
        lines.extend([f"file '{filename}'",'option framerate 1000',f'duration {duration:.9f}'])
    lines.extend([f"file '{records[-1][0]}'",'option framerate 1000'])
    return '\n'.join(lines)+'\n'


def prepare_frames(root,bag,width):
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import Image as ROSImage
    from PIL import Image
    name=bag.name
    directory=root/'camera'/name
    directory.mkdir(parents=True,exist_ok=True)
    extraction=json.loads((root/'extraction.json').read_text())
    source_hashes={}
    for database in sorted(bag.glob('*.db3')):
        expected=next(item['sha256'] for item in extraction['files'] if item['path']=='ouster/'+name+'/'+database.name)
        source_hashes[database.name]=digest(database)
        if source_hashes[database.name]!=expected:raise ValueError('Source recording changed')
    recipe={'source_sha256':source_hashes,'preview_width':width,'tool_sha256':digest(Path(__file__)),
            'timing':'Bag record times; begins at first cloud, black until first image, last image held until final cloud',
            'video_fps':30,'source_frame_rate':'Approximately 2 Hz; frames held, no motion interpolation',
            'header_timestamps_changed':False,'source_images_changed':False,'detection_overlay':False}
    manifest=directory/'frames.json'
    if manifest.exists():
        current=json.loads(manifest.read_text())
        if current['recipe']!=recipe:raise ValueError('Existing camera export recipe changed')
        for filename,checksum in current['files'].items():
            if digest(directory/filename)!=checksum:raise ValueError('Camera preview changed')
        return directory,current
    images=[];start=None;end=None
    for database in sorted(bag.glob('*.db3')):
        with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as db:
            topic=db.execute("SELECT id FROM topics WHERE name='/image'").fetchone()[0]
            clouds=db.execute("SELECT id FROM topics WHERE name='/points'").fetchone()[0]
            lo,hi=db.execute('SELECT MIN(timestamp),MAX(timestamp) FROM messages WHERE topic_id=?',(clouds,)).fetchone()
            start=lo if start is None else min(start,lo);end=hi if end is None else max(end,hi)
            for stamp,payload in db.execute('SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp,id',(topic,)):
                msg=deserialize_message(payload,ROSImage)
                if msg.encoding not in ('bgr8','rgb8') or msg.step<msg.width*3 or len(msg.data)!=msg.step*msg.height:
                    raise ValueError('Unsupported camera image layout')
                frame=Image.frombytes('RGB',(msg.width,msg.height),bytes(msg.data),'raw','BGR' if msg.encoding=='bgr8' else 'RGB',msg.step,1)
                resized_width=min(width,msg.width)
                resized_width-=resized_width%2
                resized_height=round(msg.height*resized_width/msg.width/2)*2
                frame=frame.resize((resized_width,resized_height),Image.Resampling.LANCZOS)
                filename=f'{len(images):06d}.png'
                pending=directory/(filename+'.pending')
                frame.save(pending,format='PNG');pending.replace(directory/filename)
                images.append({'file':filename,'record_timestamp_ns':stamp,'header_timestamp_ns':msg.header.stamp.sec*10**9+msg.header.stamp.nanosec,
                               'frame_id':msg.header.frame_id,'source_cdr_sha256':__import__('hashlib').sha256(payload).hexdigest(),
                               'source_encoding':msg.encoding,'source_width':msg.width,'source_height':msg.height})
    if not images:raise ValueError('No camera images')
    Image.new('RGB',(resized_width,resized_height)).save(directory/'black.png')
    (directory/'timeline.ffconcat').write_text(timeline([image['record_timestamp_ns'] for image in images],start,end))
    result={'recipe':recipe,'bag':name,'frames':images,'source_image_count':len(images),
            'bag_start_timestamp_ns':start,'bag_end_timestamp_ns':end,'video_duration_seconds':(end-start)/1e9,
            'first_image_offset_seconds':(images[0]['record_timestamp_ns']-start)/1e9,
            'width':resized_width,'height':resized_height,
            'files':{p.name:digest(p) for p in directory.iterdir() if p.suffix=='.png' or p.name=='timeline.ffconcat'}}
    manifest.write_text(json.dumps(result,indent=2)+'\n')
    return directory,result


def encoder_command(directory,image,program,args):
    native=shutil.which(program)
    if native:return [native,*args],None
    # Encoder-only container: no ROS or GPU requirement, files owned by desktop user.
    import os
    docker=['docker']
    if subprocess.run(['docker','info'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        docker=['sudo','docker']
    subprocess.run([*docker,'image','inspect',image],stdout=subprocess.DEVNULL,check=True)
    command=[*docker,'run','--rm','--user',f'{os.getuid()}:{os.getgid()}',
             '--mount','type=bind,src='+str(directory)+',dst=/camera',image,program,*args]
    return command,'/camera'


def encode(directory,manifest,image):
    final=directory/'camera.mp4'
    record=directory/'video.json'
    if final.exists():
        current=json.loads(record.read_text())
        if current['video_sha256']!=digest(final) or current['frames_manifest_sha256']!=digest(directory/'frames.json'):
            raise ValueError('Existing video differs from camera export')
        return final
    command,mount=encoder_command(directory,image,'ffmpeg',[])
    prefix=Path(mount) if mount else directory
    pending=directory/'camera.pending.mp4'
    command += ['-hide_banner','-loglevel','warning','-y','-f','concat','-safe','0','-i',str(prefix/'timeline.ffconcat'),
                '-vf','fps=30','-t',str(manifest['video_duration_seconds']),'-c:v','libx264','-crf','20','-preset','medium',
                '-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(prefix/pending.name)]
    with (directory/'ffmpeg.log').open('w') as logfile:subprocess.run(command,stdout=logfile,stderr=subprocess.STDOUT,check=True)
    probe,probe_mount=encoder_command(directory,image,'ffprobe',[])
    probe += ['-v','error','-select_streams','v:0','-show_entries','stream=codec_name,width,height,nb_frames:format=duration',
              '-of','json',str((Path(probe_mount) if probe_mount else directory)/pending.name)]
    metadata=json.loads(subprocess.check_output(probe,text=True))
    stream=metadata['streams'][0];duration=float(metadata['format']['duration'])
    if stream['codec_name']!='h264' or stream['width']!=manifest['width'] or stream['height']!=manifest['height'] or abs(duration-manifest['video_duration_seconds'])>.1:
        raise ValueError('Video probe differs from requested dimensions/timing')
    pending.replace(final)
    record.write_text(json.dumps({'video_sha256':digest(final),'frames_manifest_sha256':digest(directory/'frames.json'),
                                  'probe':metadata,'duration_error_seconds':duration-manifest['video_duration_seconds'],
                                  'source_frames':manifest['source_image_count']},indent=2)+'\n')
    return final


def main():
    import fcntl
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--width',type=int,default=1280)
    parser.add_argument('--encoder-image',default='pp-infer:demo-tools')
    args=parser.parse_args()
    if not 320<=args.width<=2448:raise ValueError('Preview width must be 320..2448')
    root=args.data_dir.resolve()
    with (root/'.camera.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        for bag in sorted((root/'ouster').iterdir()):
            directory,manifest=prepare_frames(root,bag,args.width)
            print(encode(directory,manifest,args.encoder_image),flush=True)


if __name__=='__main__':main()
