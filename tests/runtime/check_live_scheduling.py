#!/usr/bin/env python3
"""Opt-in GPU/ROS scheduling integration check. Does not attach to live topics.
Usage: ROS_DOMAIN_ID=118 python3 check_live_scheduling.py NODE ENGINE
"""
import json
import os
import signal
import struct
import subprocess
import sys
import time

import rclpy
from diagnostic_msgs.msg import DiagnosticArray
from sensor_msgs.msg import PointCloud2, PointField
from rclpy.qos import QoSProfile, DurabilityPolicy


def check(binary, engine, mode):
    node = rclpy.create_node('scheduling_probe')
    messages = []
    sent = {}
    latencies = {}
    def record(message):
        messages.append(message)
        stamp = message.header.stamp.sec
        if stamp in sent:
            latencies[stamp] = (time.monotonic() - sent[stamp]) * 1000
    qos = QoSProfile(depth=100, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    subscription = node.create_subscription(DiagnosticArray, '/latency_test/performance', record, qos)
    publisher = node.create_publisher(PointCloud2, '/latency_test/input', 100)
    log_path = f'/tmp/pp-scheduling-{mode}.log'
    with open(log_path, 'w') as log:
        child = subprocess.Popen([binary, '--ros-args', '-r', '__node:=latency_test',
            '-r', '/point_cloud:=/latency_test/input', '-r', 'bbox:=/latency_test/bbox',
            '-p', 'class_names:=[Vehicle, Pedestrian, Cyclist]',
            '-p', f'engine_path:={engine}', '-p', f'processing_mode:={mode}'], stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 30
            while publisher.get_subscription_count() == 0:
                rclpy.spin_once(node, timeout_sec=0.05)
                if child.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError(f'Node unavailable; see {log_path}')
            cloud = PointCloud2()
            cloud.header.frame_id = 'test_lidar'
            cloud.height, cloud.width = 1, 128
            cloud.fields = [PointField(name=name, offset=i*4, datatype=PointField.FLOAT32, count=1)
                            for i, name in enumerate(('x', 'y', 'z', 'intensity'))]
            cloud.point_step, cloud.row_step = 16, 128*16
            cloud.is_dense = True
            cloud.data = b''.join(struct.pack('<ffff', 5+(i % 16)*.1, (i//16)*.1, 0, .5) for i in range(128))
            # Warm up and wait for a completed GPU inference before the burst.
            cloud.header.stamp.sec = 1
            publisher.publish(cloud)
            deadline = time.monotonic() + 30
            while not messages:
                rclpy.spin_once(node, timeout_sec=.05)
                if time.monotonic() > deadline:
                    raise RuntimeError('Warm-up timeout')
            messages.clear()
            for i in range(2, 62):
                cloud.header.stamp.sec = i
                sent[i] = time.monotonic()
                publisher.publish(cloud)
                rclpy.spin_once(node, timeout_sec=.001)
            deadline = time.monotonic() + 30
            while not messages or messages[-1].header.stamp.sec != 61:
                rclpy.spin_once(node, timeout_sec=.05)
                if time.monotonic() > deadline:
                    raise RuntimeError(f'Final scan not processed; see {log_path}')
            stamps = [m.header.stamp.sec for m in messages]
            assert stamps == sorted(set(stamps)), stamps
            assert all(m.header.frame_id == 'test_lidar' and m.status[0].message == 'ok' for m in messages)
            stats = [dict((v.key, v.value) for v in m.status[0].values) for m in messages]
            for values in stats:
                for key in ('pack_ms', 'gpu_pipeline_ms', 'decode_ms', 'nms_ms', 'processing_ms', 'queue_wait_ms'):
                    assert float(values[key]) >= 0, values
            if mode == 'all_frames':
                assert stamps == list(range(2, 62)), stamps
            else:
                assert len(stamps) < 60, stamps
                assert int(stats[-1]['replaced_pending_frames_total']) > 0, stats[-1]
            result = {'mode': mode, 'received_outputs': len(stamps), 'final_stamp': stamps[-1],
                      'replaced_pending': int(stats[-1]['replaced_pending_frames_total']),
                      'final_publish_to_diagnostics_ms': latencies[61]}
            for key in ('pack_ms', 'gpu_pipeline_ms', 'decode_ms', 'nms_ms', 'processing_ms', 'queue_wait_ms'):
                samples = sorted(float(s[key]) for s in stats)
                result[key] = {'median': samples[len(samples)//2], 'max': max(samples)}
            print(json.dumps(result), flush=True)
        finally:
            child.send_signal(signal.SIGINT)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait()
            node.destroy_node()
    assert child.returncode == 0, f'Unclean shutdown: {child.returncode}; see {log_path}'


if __name__ == '__main__':
    if os.environ.get('ROS_DOMAIN_ID') != '118':
        raise SystemExit('Use isolated ROS_DOMAIN_ID=118')
    rclpy.init()
    try:
        for mode in ('all_frames', 'latest'):
            check(sys.argv[1], os.path.abspath(sys.argv[2]), mode)
    finally:
        rclpy.shutdown()
