#!/usr/bin/env python3
"""Check actual C++ Ouster conversion/packing on pinned bags, without DDS/GPU.

Reads source databases only. Legacy signal naming and reconstructed live layouts
are explicit test fixtures, never written back to the source bags.
"""
import argparse
from array import array
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys

import numpy as np
from rclpy.serialization import deserialize_message, serialize_message
from sensor_msgs.msg import PointCloud2, PointField

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def channel(message, name):
    fields = [field for field in message.fields if field.name == name]
    if len(fields) != 1 or fields[0].count != 1 or message.is_bigendian:
        raise ValueError('Missing/ambiguous little-endian scalar field: ' + name)
    field = fields[0]
    dtype = {PointField.FLOAT32: '<f4', PointField.UINT16: '<u2',
             PointField.UINT8: 'u1', PointField.UINT32: '<u4'}[field.datatype]
    if (field.offset + np.dtype(dtype).itemsize > message.point_step or
            message.row_step < message.width * message.point_step or
            len(message.data) != message.row_step * message.height):
        raise ValueError('Invalid cloud layout')
    return np.ndarray((message.height, message.width), dtype=dtype, buffer=message.data,
                      offset=field.offset, strides=(message.row_step, message.point_step))


def legacy_signal_fixture(message):
    result = deepcopy(message)
    field = next(field for field in result.fields if field.name == 'intensity')
    if field.datatype != PointField.FLOAT32:
        raise ValueError('Legacy signal fixture requires recorded FLOAT32 intensity')
    field.name = 'signal'  # Explicit fixture mapping; no value conversion here.
    return result


def live_layout_fixture(message):
    signal = channel(message, 'intensity')
    reflectivity = channel(message, 'reflectivity')
    if (not np.isfinite(signal).all() or np.any(signal < 0) or np.any(signal > 65535)
            or np.any(signal != np.floor(signal)) or np.any(reflectivity > 255)):
        raise ValueError('Recorded values cannot be represented losslessly in live channel types')
    result = PointCloud2()
    result.header = deepcopy(message.header)
    result.width = message.width
    result.height = message.height
    result.point_step = 48
    result.row_step = result.width * result.point_step
    result.is_dense = message.is_dense
    fields = [('x', 0, 7), ('y', 4, 7), ('z', 8, 7), ('t', 16, 6),
              ('ring', 20, 4), ('range', 24, 6), ('signal', 28, 4),
              ('near_ir', 30, 4), ('reflectivity', 32, 2), ('flags', 33, 2)]
    result.fields = [PointField(name=name, offset=offset, datatype=kind, count=1)
                     for name, offset, kind in fields]
    result.data = array('B', bytes(result.height * result.row_step))
    for name in ('x', 'y', 'z', 't', 'ring', 'range'):
        channel(result, name)[:] = channel(message, name)
    channel(result, 'signal')[:] = signal.astype('<u2')
    channel(result, 'reflectivity')[:] = reflectivity.astype('u1')
    channel(result, 'near_ir')[:] = channel(message, 'ambient')
    # flags is zero: it is not used by the converter and absent in the recording.
    return result


def read_exact(stream, count):
    chunks = bytearray()
    while len(chunks) < count:
        block = stream.read(count - len(chunks))
        if not block:
            raise RuntimeError('C++ probe exited or returned truncated output')
        chunks.extend(block)
    return chunks


class Probe:
    def __init__(self, executable, source, divisor):
        self.process = subprocess.Popen([str(executable), source, str(divisor)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def convert(self, message):
        payload = serialize_message(message)
        self.process.stdin.write(struct.pack('<I', len(payload)))
        self.process.stdin.write(payload)
        self.process.stdin.flush()
        size, valid = struct.unpack('<II', read_exact(self.process.stdout, 8))
        if size > 67174400:
            raise ValueError('Probe output exceeds configured bound')
        output = deserialize_message(bytes(read_exact(self.process.stdout, size)), PointCloud2)
        return output, valid

    def close(self):
        self.process.stdin.close()
        try:
            code = self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
            raise
        finally:
            self.process.stdout.close()
        if code:
            raise RuntimeError(f'C++ probe failed with status {code}')


def verify(original, output, valid, source, divisor):
    if (output.header != original.header or output.width != original.width or
            output.height != original.height or output.point_step != 16 or
            output.row_step != output.width * 16 or output.is_bigendian):
        raise ValueError('Header/dimensions/output layout mismatch')
    if [(f.name, f.offset, f.datatype, f.count) for f in output.fields] != [
            (name, index * 4, 7, 1) for index, name in enumerate(('x', 'y', 'z', 'intensity'))]:
        raise ValueError('Output does not have exactly scalar FLOAT32 XYZI')
    finite = np.ones((original.height, original.width), dtype=bool)
    for name in ('x', 'y', 'z'):
        expected = channel(original, name)
        if channel(output, name).tobytes() != expected.tobytes():
            raise ValueError('XYZ bits/order changed')
        finite &= np.isfinite(expected)
    expected_intensity = (channel(original, source).astype(np.float64) / divisor).astype('<f4')
    actual = channel(output, 'intensity')
    if actual.tobytes() != expected_intensity.tobytes():
        raise ValueError('Intensity differs from independent numeric conversion')
    finite &= np.isfinite(expected_intensity)
    if valid != int(finite.sum()):
        raise ValueError('Detector packer returned wrong valid point count')
    return float(actual.min()), float(actual.max()), int(original.width * original.height)


def run(args):
    inventory = json.loads((ROOT / 'config/ouster_demo_inventory.json').read_text())
    root = args.data_dir.resolve()
    expected = {item['path']: item['sha256'] for item in inventory['extracted_files']}
    cases = [('recorded_reflectivity', 'reflectivity', 255.0),
             ('legacy_signal_name_mapping', 'signal', 65535.0),
             ('reconstructed_live_reflectivity', 'reflectivity', 255.0),
             ('reconstructed_live_signal', 'signal', 65535.0)]
    report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'test_mode': 'offline CDR -> production C++ converter -> detector XYZI packer',
              'gpu_inference_tested': False, 'network_transport_tested': False,
              'source_databases_unchanged': False,
              'fixture_notes': [
                  'Original bags contain FLOAT32 intensity (recorded signal) and UINT16 reflectivity.',
                  'Legacy signal fixture explicitly renames intensity to signal in memory.',
                  'Live-layout fixtures numerically convert integer-valued signal to UINT16 and reflectivity to UINT8.',
                  'Reconstructed point_step=48 uses documented live offsets; scan dimensions remain those recorded.',
                  'No physical 128-channel recording, GPU detections, accuracy or cross-process transport is validated.'],
              'probe_sha256': digest(args.probe),
              'source_sha256': {str(path.relative_to(ROOT)): digest(path) for path in (
                  ROOT / 'src/ouster_adapter.cpp', ROOT / 'src/pointcloud_adapter.cpp', Path(__file__).resolve())},
              'bags': []}
    for bag in inventory['bags']:
        folder = root / 'ouster' / bag['bag']
        databases = sorted(folder.glob('*.db3'))
        if not databases:
            raise ValueError('Missing databases: ' + str(folder))
        checksums = {str(path.relative_to(root)): digest(path) for path in databases}
        if any(expected.get(name) != checksum for name, checksum in checksums.items()):
            raise ValueError('Bag does not match pinned source hashes')
        probes = []
        summaries = {name: {'frames': 0, 'points': 0, 'intensity_min': None, 'intensity_max': None}
                     for name, _, _ in cases}
        try:
            probes = [Probe(args.probe, source, divisor) for _, source, divisor in cases]
            for path in databases:
                with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
                    topic = db.execute("SELECT id,type FROM topics WHERE name='/points'").fetchone()
                    if not topic or topic[1] != 'sensor_msgs/msg/PointCloud2':
                        raise ValueError('Missing /points PointCloud2')
                    for _, payload in db.execute('SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp', (topic[0],)):
                        original = deserialize_message(payload, PointCloud2)
                        signal = legacy_signal_fixture(original)
                        live = live_layout_fixture(original)
                        for probe, (name, source, divisor), message in zip(probes, cases, (original, signal, live, live)):
                            output, valid = probe.convert(message)
                            low, high, count = verify(message, output, valid, source, divisor)
                            # Fixtures must also preserve original geometry/header/order.
                            if message.header != original.header or any(
                                    channel(message, n).tobytes() != channel(original, n).tobytes()
                                    for n in ('x', 'y', 'z')):
                                raise ValueError('Fixture changed recorded geometry/header')
                            summary = summaries[name]
                            summary['frames'] += 1
                            summary['points'] += count
                            summary['intensity_min'] = low if summary['intensity_min'] is None else min(low, summary['intensity_min'])
                            summary['intensity_max'] = high if summary['intensity_max'] is None else max(high, summary['intensity_max'])
        finally:
            for probe in probes:
                probe.close()
        if any(summary['frames'] != bag['clouds'] for summary in summaries.values()):
            raise ValueError('Frame count differs from source inventory')
        if any(digest(root / name) != checksum for name, checksum in checksums.items()):
            raise ValueError('Source database changed during verification')
        report['bags'].append({'bag': bag['bag'], 'source_database_sha256': checksums, 'cases': summaries})
        print(f"PASS {bag['bag']}: {bag['clouds']} scans x {len(cases)} cases", flush=True)
    report['source_databases_unchanged'] = True
    report['status'] = 'passed'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('Report: ' + str(args.output.resolve()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / '.recovery/rosbags/ouster_calibration_v3')
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.probe = args.probe.resolve()
    if sys.byteorder != 'little':
        parser.error('The CDR probe protocol currently requires a little-endian host')
    run(args)


if __name__ == '__main__':
    main()
