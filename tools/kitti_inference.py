#!/usr/bin/env python3
"""Publish fixed labeled KITTI frames, export matched ROS detections, and show GT in RViz."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time

from prepare_kitti_validation import atomic_write, encoded, freeze_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def detection_record(message):
    result = []
    for det in message.detections:
        if len(det.results) != 1:
            raise ValueError('Expected one model hypothesis per exported box')
        hypothesis = det.results[0].hypothesis
        position, q = det.bbox.center.position, det.bbox.center.orientation
        yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
        row = {'center_lidar': [position.x, position.y, position.z],
               'dimensions_lwh': [det.bbox.size.x, det.bbox.size.y, det.bbox.size.z],
               'yaw_lidar': yaw, 'class_id': int(hypothesis.class_id), 'score': hypothesis.score}
        values = row['center_lidar']+row['dimensions_lwh']+[yaw,row['score']]
        if not all(math.isfinite(x) for x in values) or min(row['dimensions_lwh']) <= 0 or row['class_id'] not in (0,1,2) or not 0 <= row['score'] <= 1:
            raise ValueError('Invalid detection output')
        result.append(row)
    return result


def main():
    import rclpy
    from rclpy.qos import QoSProfile, DurabilityPolicy
    from sensor_msgs.msg import PointCloud2, PointField
    from geometry_msgs.msg import Point
    from vision_msgs.msg import Detection3DArray
    from visualization_msgs.msg import Marker, MarkerArray

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--loop', action='store_true', help='Continue live inference/display after the first measured pass')
    parser.add_argument('--period', type=float, default=2.0)
    parser.add_argument('--timeout', type=float, default=60.0)
    args = parser.parse_args()
    manifest = json.loads((args.dataset/'manifest.json').read_text())
    runtime = json.loads((args.output/'runtime.json').read_text())
    for frame in manifest['frames']:
        for asset in frame['assets'].values():
            if sha(args.dataset/asset['path']) != asset['sha256']:
                raise ValueError('Dataset asset hash mismatch: '+asset['path'])
    recipe = {'schema_version':1, 'dataset_manifest_sha256':sha(args.dataset/'manifest.json'),
              'runtime':runtime, 'exporter_sha256':sha(Path(__file__)),
              'input_topic':'/kitti/point_cloud','output_topic':'/kitti/predictions',
              'point_packing':'original little-endian XYZI; no filtering/scaling/translation',
              'outputs':'ROS final boxes after existing runtime NMS; pre-NMS reference parity pending'}
    args.output.mkdir(parents=True, exist_ok=True)
    freeze_json(args.output/'run.json', recipe)
    rclpy.init()
    node = rclpy.create_node('kitti_validation_player')
    received = []
    sub = node.create_subscription(Detection3DArray,'/kitti/predictions',received.append,10)
    pub = node.create_publisher(PointCloud2,'/kitti/point_cloud',10)
    gt_pub = node.create_publisher(MarkerArray,'/kitti/ground_truth',QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))
    edges = [(i,j) for i in range(8) for j in range(i+1,8) if (i^j) in (1,2,4)]
    deadline = time.monotonic()+args.timeout
    while not pub.get_subscription_count() or not node.count_publishers('/kitti/predictions'):
        if time.monotonic()>deadline:
            raise RuntimeError('Detector discovery timed out; check isolated ROS domain/container startup')
        rclpy.spin_once(node, timeout_sec=.1)
    time.sleep(1)
    try:
        while rclpy.ok():
            for frame in manifest['frames']:
                started = time.monotonic()
                frame_id = frame['frame_id']
                cloud = (args.dataset/frame['assets']['velodyne']['path']).read_bytes()
                msg = PointCloud2()
                msg.header.frame_id = 'velodyne'
                msg.header.stamp = node.get_clock().now().to_msg()
                msg.height, msg.width = 1, len(cloud)//16
                msg.point_step, msg.row_step = 16, len(cloud)
                msg.fields = [PointField(name=name, offset=i*4, datatype=PointField.FLOAT32, count=1)
                              for i,name in enumerate(('x','y','z','intensity'))]
                msg.data, msg.is_dense = cloud, True
                annotations = json.loads((args.dataset/f'annotations_lidar/{frame_id}.json').read_text())
                markers = MarkerArray()
                clear = Marker(); clear.action=Marker.DELETEALL; markers.markers.append(clear)
                for index, obj in enumerate(annotations['objects']):
                    box = obj['box_lidar']
                    if box is None:
                        continue
                    marker = Marker(); marker.header = msg.header; marker.ns='ground_truth'; marker.id=index
                    marker.type=Marker.LINE_LIST; marker.action=Marker.ADD; marker.pose.orientation.w=1.0
                    marker.scale.x=.07; marker.color.g=1.; marker.color.a=1.
                    marker.points=[Point(x=float(box['corners_lidar'][k][0]),y=float(box['corners_lidar'][k][1]),z=float(box['corners_lidar'][k][2]))
                                   for edge in edges for k in edge]
                    markers.markers.append(marker)
                label = Marker(); label.header=msg.header; label.ns='frame'; label.id=0; label.type=Marker.TEXT_VIEW_FACING
                label.pose.orientation.w=1.; label.pose.position.x=8.; label.pose.position.z=5.
                label.scale.z=.8; label.color.r=label.color.g=label.color.b=label.color.a=1.
                label.text=f"KITTI {frame_id} ({frame['split']}) | green: ground truth"
                markers.markers.append(label)
                gt_pub.publish(markers)
                received.clear()
                pub.publish(msg)
                deadline = time.monotonic()+args.timeout
                while not any(item.header == msg.header for item in received):
                    if time.monotonic()>deadline:
                        raise RuntimeError('Missing matching inference output for frame '+frame_id)
                    rclpy.spin_once(node,timeout_sec=.05)
                output = next(item for item in received if item.header==msg.header)
                predictions = detection_record(output)
                record = {'schema_version':1,'frame_id':frame_id,'split':frame['split'],
                          'cloud_sha256':frame['assets']['velodyne']['sha256'],
                          'run_sha256':sha(args.output/'run.json'),'detections':predictions}
                path = args.output/f'predictions/{frame_id}.json'
                if not path.exists():
                    atomic_write(path,encoded(record))
                else:
                    # Retain the first observation; repeat display never tunes or overwrites it.
                    saved=json.loads(path.read_text())
                    if saved['run_sha256'] != record['run_sha256'] or saved['cloud_sha256'] != record['cloud_sha256']:
                        raise ValueError('Existing prediction provenance differs: '+str(path))
                print(f"KITTI {frame_id} {frame['split']}: {len(predictions)} predictions",flush=True)
                while time.monotonic()-started < args.period:
                    rclpy.spin_once(node,timeout_sec=.05)
            index={'run_sha256':sha(args.output/'run.json'), 'frames':[
                {'frame_id':f['frame_id'],'path':f'predictions/{f["frame_id"]}.json',
                 'sha256':sha(args.output/f'predictions/{f["frame_id"]}.json')} for f in manifest['frames']]}
            freeze_json(args.output/'prediction_manifest.json',index)
            print('PASS: all fixed frames exported; '+str(args.output/'prediction_manifest.json'),flush=True)
            if not args.loop:
                break
    finally:
        node.destroy_node(); rclpy.shutdown()


if __name__=='__main__':
    main()
