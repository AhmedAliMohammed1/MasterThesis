#!/usr/bin/env python3
"""Download and inspect Kenji Koide's pinned, non-KITTI Ouster ROS 2 bags."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import subprocess
import tarfile

SOURCE_URL = 'https://zenodo.org/records/7780490/files/ouster.tar.gz'
SOURCE_PAGE = 'https://zenodo.org/records/7780490'
ARCHIVE_BYTES = 1521635387
ARCHIVE_MD5 = 'a0a56bbb93433f729a9e924744ad6b0c'
POINT_CAPACITY = 204800


def digest(path, algorithm='sha256'):
    result = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def verify_archive(path):
    return path.is_file() and path.stat().st_size == ARCHIVE_BYTES and digest(path, 'md5') == ARCHIVE_MD5


def prepare_archive(root):
    final = root / 'ouster.tar.gz'
    pending = root / 'ouster.tar.gz.part'
    if final.exists():
        if not verify_archive(final):
            raise ValueError(f'Archive differs from publisher checksum: {final}')
        return final
    if not verify_archive(pending):
        if pending.exists() and pending.stat().st_size >= ARCHIVE_BYTES:
            raise ValueError(f'Invalid completed download; inspect {pending}')
        subprocess.run(['curl', '--fail', '--location', '--retry', '5', '--retry-delay', '3',
                        '--connect-timeout', '20', '--continue-at', '-', SOURCE_URL,
                        '--output', str(pending)], check=True)
        if not verify_archive(pending):
            raise ValueError('Download failed publisher size/MD5 verification; partial file preserved')
    pending.replace(final)
    return final


def safe_members(source):
    members = source.getmembers()
    for member in members:
        parts = PurePosixPath(member.name).parts
        if (not parts or parts[0] != 'ouster' or '..' in parts or
                member.name.startswith('/') or not (member.isdir() or member.isfile())):
            raise ValueError(f'Unsafe archive member: {member.name}')
    return members


def extract_archive(archive, root):
    marker = root / 'extraction.json'
    if marker.exists():
        inventory = json.loads(marker.read_text())
        if inventory.get('archive_md5') != ARCHIVE_MD5:
            raise ValueError('Extraction belongs to another source')
        for item in inventory['files']:
            path = root / item['path']
            if not path.is_file() or path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
                raise ValueError(f'Extracted file changed: {path}')
        return
    with tarfile.open(archive, 'r:gz') as source:
        members = safe_members(source)
        if shutil.disk_usage(root).free < sum(m.size for m in members) + 512 * 1024 * 1024:
            raise ValueError('Insufficient disk space for extracted bags')
        inventory = []
        for member in members:
            destination = root / member.name
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Existing files may belong to interrupted extraction; compare instead of overwriting.
            pending = destination.with_suffix(destination.suffix + '.extracting')
            with source.extractfile(member) as src, pending.open('wb') as out:
                shutil.copyfileobj(src, out, 4 * 1024 * 1024)
            checksum = digest(pending)
            if destination.exists():
                if destination.stat().st_size != member.size or digest(destination) != checksum:
                    raise ValueError(f'Existing extraction differs: {destination}')
                pending.unlink()
            else:
                pending.replace(destination)
            inventory.append({'path': member.name, 'bytes': member.size, 'sha256': checksum})
    marker.write_text(json.dumps({'archive_md5': ARCHIVE_MD5, 'files': inventory}, indent=2) + '\n')


def inspect_cloud(msg):
    fields = {field.name: field for field in msg.fields}
    if len(fields) != len(msg.fields):
        raise ValueError('Duplicate cloud fields')
    offsets = []
    for name in ('x', 'y', 'z', 'intensity'):
        field = fields.get(name)
        if field is None or field.datatype != 7 or field.count != 1 or field.offset + 4 > msg.point_step:
            raise ValueError(f'Cloud needs scalar FLOAT32 {name}; adaptation required')
        offsets.append(field.offset)
    offsets.sort()
    if any(b - a < 4 for a, b in zip(offsets, offsets[1:])):
        raise ValueError('Overlapping XYZI fields')
    count = msg.width * msg.height
    if msg.is_bigendian or msg.row_step < msg.width * msg.point_step or len(msg.data) != msg.row_step * msg.height:
        raise ValueError('Unsupported endian or inconsistent cloud layout')
    return count


def audit_bag(bag):
    # ROS packages are loaded only for inspection, not download/extraction.
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import PointCloud2
    import numpy as np
    summary = {'bag': bag.name, 'cloud_topic': '/points', 'clouds': 0, 'frames': [],
               'point_count_min': None, 'point_count_max': 0, 'oversized_clouds': 0,
               'intensity_min': None, 'intensity_max': None, 'nonfinite_xyzi_points': 0,
               'first_stamp_ns': None, 'last_stamp_ns': None}
    frames = set()
    for database in sorted(bag.glob('*.db3')):
        with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError(f'Corrupt bag database: {database}')
            topics = db.execute('SELECT id,name,type FROM topics').fetchall()
            matches = [t for t in topics if t[1] == '/points' and t[2] == 'sensor_msgs/msg/PointCloud2']
            if len(matches) != 1:
                raise ValueError(f'Expected /points PointCloud2 in {database}')
            summary['topics'] = [{'name': t[1], 'type': t[2]} for t in topics]
            for stamp, payload in db.execute('SELECT timestamp,data FROM messages WHERE topic_id=? ORDER BY timestamp', (matches[0][0],)):
                msg = deserialize_message(payload, PointCloud2)
                count = inspect_cloud(msg)
                summary['clouds'] += 1
                summary['point_count_min'] = min(summary['point_count_min'] if summary['point_count_min'] is not None else count, count)
                summary['point_count_max'] = max(summary['point_count_max'], count)
                summary['oversized_clouds'] += int(count > POINT_CAPACITY)
                frames.add(msg.header.frame_id)
                if summary['first_stamp_ns'] is None:
                    summary['first_stamp_ns'] = stamp
                    summary['fields'] = [{'name': f.name, 'offset': f.offset, 'datatype': f.datatype, 'count': f.count} for f in msg.fields]
                summary['last_stamp_ns'] = stamp
                channels = []
                for name in ('x', 'y', 'z', 'intensity'):
                    offset = next(f.offset for f in msg.fields if f.name == name)
                    channels.append(np.ndarray((msg.height, msg.width), dtype='<f4', buffer=msg.data,
                                              offset=offset, strides=(msg.row_step, msg.point_step)))
                valid = np.logical_and.reduce([np.isfinite(channel) for channel in channels])
                summary['nonfinite_xyzi_points'] += int(count - valid.sum())
                intensity = channels[3][valid]
                if intensity.size:
                    low, high = float(intensity.min()), float(intensity.max())
                    summary['intensity_min'] = min(summary['intensity_min'] if summary['intensity_min'] is not None else low, low)
                    summary['intensity_max'] = max(summary['intensity_max'] if summary['intensity_max'] is not None else high, high)
    if not summary['clouds']:
        raise ValueError(f'No point clouds in {bag}')
    summary['frames'] = sorted(frames)
    summary['duration_seconds'] = (summary['last_stamp_ns'] - summary['first_stamp_ns']) / 1e9
    summary['input_point_capacity'] = POINT_CAPACITY
    summary['pillar_capacity_enforced'] = False
    summary['intensity_rescaled'] = False
    summary['accuracy_validated'] = False
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--audit-only', action='store_true')
    args = parser.parse_args()
    root = args.data_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not args.audit_only:
        extract_archive(prepare_archive(root), root)
    bags = sorted(path.parent for path in (root / 'ouster').rglob('metadata.yaml'))
    if not bags:
        raise ValueError('No extracted ROS 2 bags found')
    summaries = [audit_bag(bag) for bag in bags]
    manifest = {'source': SOURCE_PAGE, 'download': SOURCE_URL, 'archive_bytes': ARCHIVE_BYTES,
                'archive_md5': ARCHIVE_MD5, 'author': 'Kenji Koide (AIST)', 'license': 'CC-BY-4.0',
                'sensor': 'Ouster OS1-32', 'bags': summaries}
    temporary = root / 'inventory.json.pending'
    temporary.write_text(json.dumps(manifest, indent=2) + '\n')
    temporary.replace(root / 'inventory.json')
    (root / 'playback_qos.yaml').write_text('/points:\n  reliability: reliable\n  durability: volatile\n  history: keep_last\n  depth: 5\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
