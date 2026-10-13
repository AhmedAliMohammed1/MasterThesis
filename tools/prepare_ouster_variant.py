#!/usr/bin/env python3
"""Create an opt-in cloud-only replay with an explicit diagnostic fourth feature."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import shutil
from ouster_features import VARIANTS, converted_message, channel
from prepare_ouster_demo import digest


def prepare(root, name, variant):
    from rclpy.serialization import deserialize_message, serialize_message
    from sensor_msgs.msg import PointCloud2
    import rosbag2_py
    import numpy as np
    import fcntl
    if variant not in VARIANTS or variant == 'raw_signal':
        raise ValueError('Choose an explicit non-raw variant')
    inventory=json.loads((root/'extraction.json').read_text())
    source=root/'ouster'/name
    sources=sorted(source.glob('*.db3'))
    if not sources or '/' in name or name in ('.','..'):
        raise ValueError('Unknown sequence')
    hashes={}
    for path in sources:
        expected=next(x['sha256'] for x in inventory['files'] if x['path']=='ouster/'+name+'/'+path.name)
        hashes[path.name]=digest(path)
        if hashes[path.name]!=expected:
            raise ValueError('Source bag changed')
    recipe={'source_bag':name,'source_database_sha256':hashes,'variant':variant,'feature':VARIANTS[variant],
            'features_module_sha256':digest(Path(__file__).with_name('ouster_features.py')),
            'preparer_sha256':digest(Path(__file__)),
            'topics':['/points'],'coordinate_change':False,'point_selection_change':False,
            'point_order_change':False,'timestamp_change':False,
            'accuracy_validated':False,'training_calibration_validated':False}
    parent=root/'derived'/variant
    parent.mkdir(parents=True,exist_ok=True)
    target=parent/name
    with (parent/(name+'.lock')).open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if target.exists():
            manifest=json.loads((target/'feature_manifest.json').read_text())
            if manifest['recipe']!=recipe:
                raise ValueError('Existing variant recipe differs; preserve it and use a fresh data folder')
            for filename, checksum in manifest['files'].items():
                if digest(target/filename)!=checksum:
                    raise ValueError('Derived bag changed')
            return target
        pending=parent/(name+'.pending')
        if pending.exists():
            raise ValueError('Interrupted variant preparation; preserve/inspect its .pending directory first')
        writer=rosbag2_py.SequentialWriter()
        writer.open(rosbag2_py.StorageOptions(uri=str(pending),storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
        writer.create_topic(rosbag2_py.TopicMetadata(id=1,name='/points',type='sensor_msgs/msg/PointCloud2',serialization_format='cdr'))
        clouds=0
        try:
            for database in sources:
                with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as db:
                    topic=db.execute("SELECT id FROM topics WHERE name='/points'").fetchone()[0]
                    for stamp,payload in db.execute('SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp',(topic,)):
                        original=deserialize_message(payload,PointCloud2)
                        adapted=converted_message(original,variant)
                        if adapted.header!=original.header or adapted.fields!=original.fields or adapted.width!=original.width or adapted.height!=original.height:
                            raise ValueError('Adaptation changed cloud metadata')
                        # Every byte except each FLOAT32 intensity slot must be identical.
                        before=np.frombuffer(original.data,dtype=np.uint8).reshape(original.height,original.row_step)
                        after=np.frombuffer(adapted.data,dtype=np.uint8).reshape(adapted.height,adapted.row_step)
                        unchanged=np.ones(before.shape,dtype=bool)
                        offset=next(f.offset for f in original.fields if f.name=='intensity')
                        for shift in range(4):
                            unchanged[:,offset+shift:original.width*original.point_step:original.point_step]=False
                        if not np.array_equal(before[unchanged],after[unchanged]):
                            raise ValueError('Adaptation changed non-intensity bytes')
                        writer.write('/points',serialize_message(adapted),stamp)
                        clouds+=1
        finally:
            writer.close()
        files={p.name:digest(p) for p in pending.iterdir() if p.is_file()}
        (pending/'feature_manifest.json').write_text(json.dumps({'recipe':recipe,'clouds':clouds,'files':files},indent=2)+'\n')
        pending.rename(target)
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--sequence',required=True)
    parser.add_argument('--variant',choices=list(VARIANTS),required=True)
    args=parser.parse_args()
    print(prepare(args.data_dir.resolve(),args.sequence,args.variant))


if __name__=='__main__':
    main()
