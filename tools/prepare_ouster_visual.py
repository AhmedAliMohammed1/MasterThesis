#!/usr/bin/env python3
"""Merge original camera payloads with a verified feature-converted cloud bag."""
import argparse
import heapq
import json
from pathlib import Path
import sqlite3
from prepare_ouster_demo import digest


def rows(database, names):
    db=sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        topics={ident:name for ident,name in db.execute('SELECT id,name FROM topics') if name in names}
        identifiers=list(topics)
        query='SELECT timestamp,topic_id,data FROM messages WHERE topic_id IN ('+','.join('?' for _ in identifiers)+') ORDER BY timestamp,id'
        for timestamp,ident,payload in db.execute(query,identifiers):
            yield timestamp,topics[ident],payload
    finally:
        db.close()


def prepare(root,name,feature):
    import rosbag2_py
    import fcntl
    if feature=='raw_signal':
        return root/'ouster'/name
    raw=root/'ouster'/name
    clouds=root/'derived'/feature/name
    cloud_manifest=json.loads((clouds/'feature_manifest.json').read_text())
    for filename,checksum in cloud_manifest['files'].items():
        if digest(clouds/filename)!=checksum:raise ValueError('Converted cloud bag changed')
    extraction=json.loads((root/'extraction.json').read_text())
    source_hashes={}
    for database in raw.glob('*.db3'):
        expected=next(item['sha256'] for item in extraction['files'] if item['path']=='ouster/'+name+'/'+database.name)
        source_hashes[database.name]=digest(database)
        if source_hashes[database.name]!=expected:raise ValueError('Original camera source changed')
    recipe={'source_bag':name,'feature':feature,'source_sha256':source_hashes,
            'cloud_manifest_sha256':digest(clouds/'feature_manifest.json'),'tool_sha256':digest(Path(__file__)),
            'topics':['/points','/image','/camera_info'],
            'camera_payload_change':False,'cloud_payload_change_from_derived':False,
            'header_change':False,'record_timestamp_change':False,
            'timing':'Original bag record times; camera and LiDAR header clocks are not aligned here',
            'detection_overlay':False}
    parent=root/'visual'/feature
    parent.mkdir(parents=True,exist_ok=True)
    target=parent/name
    with (parent/(name+'.lock')).open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if target.exists():
            manifest=json.loads((target/'visual_manifest.json').read_text())
            if manifest['recipe']!=recipe:raise ValueError('Existing visual bag recipe changed')
            for filename,checksum in manifest['files'].items():
                if digest(target/filename)!=checksum:raise ValueError('Visual bag changed')
            return target
        pending=parent/(name+'.pending')
        if pending.exists():raise ValueError('Interrupted visual preparation; preserve/inspect .pending folder')
        writer=rosbag2_py.SequentialWriter()
        writer.open(rosbag2_py.StorageOptions(uri=str(pending),storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
        types={'/points':'sensor_msgs/msg/PointCloud2','/image':'sensor_msgs/msg/Image','/camera_info':'sensor_msgs/msg/CameraInfo'}
        for ident,(topic,typ) in enumerate(types.items(),1):
            writer.create_topic(rosbag2_py.TopicMetadata(id=ident,name=topic,type=typ,serialization_format='cdr'))
        counts={topic:0 for topic in types}
        iterators=[rows(db,['/points']) for db in sorted(clouds.glob('*.db3'))]+[rows(db,['/image','/camera_info']) for db in sorted(raw.glob('*.db3'))]
        try:
            for timestamp,topic,payload in heapq.merge(*iterators,key=lambda row:row[0]):
                writer.write(topic,payload,timestamp)
                counts[topic]+=1
        finally:writer.close()
        if counts['/points']!=cloud_manifest['clouds'] or not counts['/image'] or not counts['/camera_info']:
            raise ValueError('Incomplete merged topics; .pending preserved')
        files={p.name:digest(p) for p in pending.iterdir() if p.is_file()}
        (pending/'visual_manifest.json').write_text(json.dumps({'recipe':recipe,'counts':counts,'files':files},indent=2)+'\n')
        pending.rename(target)
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--sequence',required=True)
    parser.add_argument('--feature',choices=['raw_signal','signal_div65535','reflectivity_div255','reflectivity_fraction'],required=True)
    args=parser.parse_args()
    if '/' in args.sequence or args.sequence in ('.','..'):raise ValueError('Invalid sequence')
    print(prepare(args.data_dir.resolve(),args.sequence,args.feature))
