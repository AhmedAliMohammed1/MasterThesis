#!/usr/bin/env python3
"""Add an original-signal visualization topic without changing inference inputs."""
import argparse
import heapq
import json
from pathlib import Path
import sqlite3
from prepare_ouster_demo import digest
from prepare_ouster_visual import rows


def prepare(root,name,feature):
    import rosbag2_py
    import fcntl
    visual=root/'visual'/feature/name
    original=root/'ouster'/name
    index=json.loads((visual/'visual_manifest.json').read_text())
    for filename,checksum in index['files'].items():
        if digest(visual/filename)!=checksum:raise ValueError('Visual source changed')
    extraction=json.loads((root/'extraction.json').read_text())
    raw_hashes={}
    for database in original.glob('*.db3'):
        expected=next(x['sha256'] for x in extraction['files'] if x['path']=='ouster/'+name+'/'+database.name)
        raw_hashes[database.name]=digest(database)
        if raw_hashes[database.name]!=expected:raise ValueError('Original source changed')
    recipe={'visual_manifest_sha256':digest(visual/'visual_manifest.json'),'raw_source_sha256':raw_hashes,
            'tool_sha256':digest(Path(__file__)),'raw_topic':'/ouster/raw_points',
            'inference_topic':'/points','inference_input_change':False,'raw_payload_change':False,
            'timestamps_changed':False,'field_of_view_crop':False,'point_sampling':False}
    parent=root/'raw_view'/feature;parent.mkdir(parents=True,exist_ok=True)
    target=parent/name
    with (parent/(name+'.lock')).open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if target.exists():
            current=json.loads((target/'raw_view_manifest.json').read_text())
            if current['recipe']!=recipe:raise ValueError('Raw-view recipe changed')
            for filename,checksum in current['files'].items():
                if digest(target/filename)!=checksum:raise ValueError('Raw-view bag changed')
            return target
        pending=parent/(name+'.pending')
        if pending.exists():raise ValueError('Interrupted raw-view preparation; preserve/inspect .pending')
        writer=rosbag2_py.SequentialWriter()
        writer.open(rosbag2_py.StorageOptions(uri=str(pending),storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
        types={'/points':'sensor_msgs/msg/PointCloud2','/ouster/raw_points':'sensor_msgs/msg/PointCloud2','/image':'sensor_msgs/msg/Image','/camera_info':'sensor_msgs/msg/CameraInfo'}
        for ident,(topic,typ) in enumerate(types.items(),1):
            writer.create_topic(rosbag2_py.TopicMetadata(id=ident,name=topic,type=typ,serialization_format='cdr'))
        def raw_rows(database):
            for timestamp,topic,payload in rows(database,['/points']):yield timestamp,'/ouster/raw_points',payload
        iterators=[rows(db,['/points','/image','/camera_info']) for db in sorted(visual.glob('*.db3'))]+[raw_rows(db) for db in sorted(original.glob('*.db3'))]
        counts={topic:0 for topic in types}
        try:
            for timestamp,topic,payload in heapq.merge(*iterators,key=lambda r:r[0]):
                writer.write(topic,payload,timestamp);counts[topic]+=1
        finally:writer.close()
        if counts['/points']!=counts['/ouster/raw_points']:raise ValueError('Raw/adapted count mismatch')
        files={p.name:digest(p) for p in pending.iterdir() if p.is_file()}
        (pending/'raw_view_manifest.json').write_text(json.dumps({'recipe':recipe,'counts':counts,'files':files},indent=2)+'\n')
        pending.rename(target)
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--sequence',required=True)
    parser.add_argument('--feature',required=True,choices=['signal_div65535','reflectivity_div255','reflectivity_fraction'])
    args=parser.parse_args()
    if '/' in args.sequence or args.sequence in ('.','..'):raise ValueError('Invalid sequence')
    print(prepare(args.data_dir.resolve(),args.sequence,args.feature))
