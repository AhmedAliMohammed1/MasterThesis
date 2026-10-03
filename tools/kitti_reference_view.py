#!/usr/bin/env python3
"""Overlay frozen TRT8 reference boxes on matching live KITTI clouds in RViz."""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import time

from kitti_evaluation import sha
from kitti_reference import ROOT, read_rows


def stop(output):
    path=output/'overlay-owner.json'
    if not path.exists():raise ValueError('No owned reference overlay recorded')
    saved=json.loads(path.read_text());proc=Path('/proc')/str(saved['pid'])
    if not proc.exists():print('Reference overlay already stopped');return
    start=(proc/'stat').read_text().split(') ',1)[1].split()[19]
    args=(proc/'cmdline').read_bytes().split(b'\0')
    if start!=saved['start_ticks'] or not any(b'kitti_reference_view.py' in a for a in args):
        raise ValueError('Process identity changed; refusing to signal it')
    os.kill(saved['pid'],signal.SIGINT)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.recovery/accuracy/kitti-reference-v1')
    parser.add_argument('--stop',action='store_true');a=parser.parse_args();a.output=a.output.resolve()
    if a.stop:stop(a.output);return
    collection=json.loads((a.output/'collection.json').read_text());recipe=json.loads((a.output/'recipe.json').read_text())
    if not collection['complete'] or collection['recipe_sha256']!=sha(a.output/'recipe.json'):raise ValueError('Incomplete/changed reference')
    records={}
    for frame in recipe['inputs']:
        key='trt8/nvidia-nms/'+frame['frame_id']+'-0.bin';path=a.output/key
        if sha(path)!=collection['files'][key]:raise ValueError('Reference predictions changed')
        records[frame['cloud_sha256']]=(frame['frame_id'],read_rows(path))
    with (a.output/'.overlay.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        import rclpy
        from rclpy.qos import QoSProfile,DurabilityPolicy
        from sensor_msgs.msg import PointCloud2
        from visualization_msgs.msg import Marker,MarkerArray
        from geometry_msgs.msg import Point
        pid=os.getpid();start=Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[19]
        (a.output/'overlay-owner.json').write_text(json.dumps({'pid':pid,'start_ticks':start,'kind':'kitti_reference_view.py'})+'\n')
        rclpy.init();node=rclpy.create_node('kitti_reference_overlay')
        pub=node.create_publisher(MarkerArray,'/kitti/reference',QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
        edges=[(i,j) for i in range(8) for j in range(i+1,8) if (i^j) in (1,2,4)]
        observed=[]
        def callback(cloud):
            # Only exact original XYZI bytes/layout may select this saved reference.
            fields={f.name:(f.offset,f.datatype,f.count) for f in cloud.fields}
            if cloud.header.frame_id!='velodyne' or cloud.is_bigendian or cloud.point_step!=16 or cloud.height!=1 or cloud.row_step!=len(cloud.data):return
            if any(fields.get(name)!=(i*4,7,1) for i,name in enumerate(('x','y','z','intensity'))):return
            record=records.get(hashlib.sha256(bytes(cloud.data)).hexdigest())
            if record is None:return
            frame,rows=record;markers=MarkerArray();clear=Marker();clear.action=Marker.DELETEALL;markers.markers.append(clear)
            for index,row in enumerate(rows):
                c,s=math.cos(row[6]),math.sin(row[6]);corners=[]
                for sx in (-1,1):
                    for sy in (-1,1):
                        for sz in (-1,1):
                            x,y=sx*row[3]/2,sy*row[4]/2
                            corners.append((row[0]+c*x-s*y,row[1]+s*x+c*y,row[2]+sz*row[5]/2))
                m=Marker();m.header=cloud.header;m.ns='trt8_reference';m.id=index;m.type=Marker.LINE_LIST;m.action=Marker.ADD
                m.pose.orientation.w=1.;m.scale.x=.08;m.color.g=.8;m.color.b=1.;m.color.a=1.
                m.points=[Point(x=float(corners[k][0]),y=float(corners[k][1]),z=float(corners[k][2])) for e in edges for k in e]
                markers.markers.append(m)
            label=Marker();label.header=cloud.header;label.ns='reference_info';label.id=0;label.type=Marker.TEXT_VIEW_FACING
            label.pose.orientation.w=1.;label.pose.position.x=8.;label.pose.position.z=6.;label.scale.z=.65
            label.color.g=.8;label.color.b=1.;label.color.a=1.
            label.text=f'{frame}: cyan TRT8 reference (frozen first repeat); green ground truth'
            markers.markers.append(label);pub.publish(markers)
            observed.append({'frame_id':frame,'boxes':len(rows),'stamp':{'sec':cloud.header.stamp.sec,'nanosec':cloud.header.stamp.nanosec}})
            print(f'Reference overlay {frame}: {len(rows)} boxes',flush=True)
        sub=node.create_subscription(PointCloud2,'/kitti/point_cloud',callback,10)
        try:rclpy.spin(node)
        except KeyboardInterrupt:pass
        finally:
            (a.output/'overlay-observations.json').write_text(json.dumps({'observations':observed,'limit':'Frozen TRT8 output synchronized to exact cloud bytes; live TRT10 can vary.'},indent=2)+'\n')
            node.destroy_node()
            if rclpy.ok():rclpy.shutdown()

if __name__=='__main__':main()
