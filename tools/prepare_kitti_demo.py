#!/usr/bin/env python3
"""Prepare pinned sample data and a camera reference clip using standard Python + FFmpeg."""
import argparse
from collections import OrderedDict
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
import zlib

BAG_REVISION = '410f471b4995acc94f728a9c590fb7645eff376e'
BAG_URL = f'https://huggingface.co/datasets/kubchud/kitti_to_ros/resolve/{BAG_REVISION}/kitti_seq04_ros2.zip'
BAG_SHA256 = '6903a1c3f68cf327cbbd2f579803184c6158ef8a1c41c086b26a85d5cc84cecd'
BAG_BYTES = 501598025
BAG_NAME = '2011_09_30_drive_0016_extract_ros2'
RAW_URL = 'https://s3.eu-central-1.amazonaws.com/avg-kitti/raw_data/2011_09_30_drive_0016/2011_09_30_drive_0016_extract.zip'
RAW_ETAG = '"78d1f40e3341bd7ae246e49d6ed12094-206"'
CAMERA_PREFIX = '2011_09_30/2011_09_30_drive_0016_extract/image_02/'
VIDEO_NAME = 'kitti04_left_camera.mp4'


def open_url(request):
    for attempt in range(4):
        try:
            return urllib.request.urlopen(request, timeout=30)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(attempt + 1)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def download_bag(path):
    if path.exists():
        if sha256(path) != BAG_SHA256:
            raise ValueError(f'Checksum mismatch: {path}; preserve/inspect it before retrying.')
        print('Reusing verified bag archive.', flush=True)
        return
    pending = path.with_suffix(path.suffix + '.part')
    offset = pending.stat().st_size if pending.exists() else 0
    if offset >= BAG_BYTES:
        if offset == BAG_BYTES and sha256(pending) == BAG_SHA256:
            os.replace(pending, path)
            print('Recovered completed pending bag download.', flush=True)
            return
        raise ValueError(f'Invalid completed/oversized pending archive: {pending}; inspect it before retrying.')
    request = urllib.request.Request(BAG_URL, headers={'Range': f'bytes={offset}-'} if offset else {})
    with open_url(request) as response:
        if response.status == 206:
            content_range = response.headers.get('Content-Range', '')
            if not content_range.startswith(f'bytes {offset}-'):
                raise ValueError('Unexpected resume range for bag.')
        elif response.status == 200:
            offset = 0  # Server does not support resume; restart only the pending file.
        else:
            raise ValueError(f'Unexpected download status {response.status}')
        with pending.open('ab' if offset else 'wb') as output:
            while chunk := response.read(4 * 1024 * 1024):
                output.write(chunk)
    if sha256(pending) != BAG_SHA256:
        raise ValueError(f'Bag checksum mismatch in {pending}; no final archive was promoted.')
    os.replace(pending, path)
    print('Bag download checksum passed.', flush=True)


def crc_matches(path, member):
    if not path.is_file() or path.stat().st_size != member.file_size:
        return False
    crc = 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            crc = zlib.crc32(chunk, crc)
    return crc & 0xffffffff == member.CRC


def prepare_bag(data_dir):
    archive = data_dir / 'kitti_seq04_ros2.zip'
    download_bag(archive)
    target = data_dir / BAG_NAME
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            parts = PurePosixPath(member.filename).parts
            if not parts or parts[0] != BAG_NAME or '..' in parts or member.filename.startswith('/'):
                raise ValueError('Unsafe or unexpected bag archive layout.')
        files = [m for m in source.infolist() if not m.is_dir()]
        if target.exists():
            if not all(crc_matches(data_dir / m.filename, m) for m in files):
                raise ValueError(f'Existing bag is incomplete or changed: {target}; inspect it before retrying.')
            print('Reusing verified extracted bag.', flush=True)
        else:
            pending = Path(tempfile.mkdtemp(prefix='.bag-pending-', dir=data_dir))
            try:
                source.extractall(pending)  # Layout checked; read verifies archive member CRCs.
                os.replace(pending / BAG_NAME, target)
            finally:
                shutil.rmtree(pending)
    database = target / (BAG_NAME + '.db3')
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
        topics = connection.execute('SELECT name,type FROM topics').fetchall()
        if ('/velodyne_points', 'sensor_msgs/msg/PointCloud2') not in topics:
            raise ValueError('Expected PointCloud2 topic is absent.')
        span = connection.execute("SELECT MIN(timestamp),MAX(timestamp),COUNT(*) FROM messages WHERE topic_id=(SELECT id FROM topics WHERE name='/velodyne_points')").fetchone()
    return {'path': BAG_NAME, 'url': BAG_URL, 'sha256': BAG_SHA256,
            'cloud_first_ns': span[0], 'cloud_last_ns': span[1], 'cloud_count': span[2], 'topics': topics}


class RemoteZip(io.RawIOBase):
    """Read only requested blocks of the public ZIP; pin its object with If-Match."""
    block_size = 1024 * 1024

    def __init__(self, url, etag):
        super().__init__()
        self.url, self.etag, self.position = url, etag, 0
        self.cache = OrderedDict()
        self.transferred = 0
        with open_url(urllib.request.Request(url, method='HEAD')) as response:
            if response.headers.get('ETag') != etag:
                raise ValueError('KITTI object changed; review source before updating the pinned ETag.')
            self.size = int(response.headers['Content-Length'])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        origins = {0: 0, 1: self.position, 2: self.size}
        if whence not in origins or origins[whence] + offset < 0:
            raise ValueError('Invalid ZIP seek')
        self.position = origins[whence] + offset
        return self.position

    def read(self, size=-1):
        remaining = max(0, self.size - self.position)
        size = remaining if size < 0 else min(size, remaining)
        result = bytearray()
        while size:
            start = self.position // self.block_size * self.block_size
            if start not in self.cache:
                end = min(start + self.block_size, self.size) - 1
                request = urllib.request.Request(self.url, headers={'Range': f'bytes={start}-{end}', 'If-Match': self.etag})
                with open_url(request) as response:
                    expected = f'bytes {start}-{end}/{self.size}'
                    if response.status != 206 or response.headers.get('Content-Range') != expected:
                        raise ValueError('Source must support exact byte ranges; full raw ZIP download was not attempted.')
                    block = response.read(end - start + 2)
                if len(block) != end - start + 1:
                    raise ValueError('Incomplete ZIP range; rerun to continue completed frames.')
                self.transferred += len(block)
                self.cache[start] = block
                if len(self.cache) > 4:
                    self.cache.popitem(last=False)
            self.cache.move_to_end(start)
            block = self.cache[start]
            offset = self.position - start
            chunk = block[offset:offset + size]
            result.extend(chunk)
            self.position += len(chunk)
            size -= len(chunk)
        return bytes(result)


def timestamp_ns(line):
    whole, fraction = line.strip().split('.')
    base = datetime.strptime(whole, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    return int(base.timestamp()) * 1_000_000_000 + int(fraction.ljust(9, '0'))


def prepare_video(data_dir, bag):
    manifest_path = data_dir / 'camera_manifest.json'
    video = data_dir / VIDEO_NAME
    if video.exists() and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get('raw_etag') == RAW_ETAG and sha256(video) == manifest.get('video_sha256'):
            print(f'Reusing verified camera video: {video}', flush=True)
            return manifest
        raise ValueError('Existing camera video differs from its manifest; preserve/inspect it before retrying.')
    camera = data_dir / 'camera/image_02'
    camera.mkdir(parents=True, exist_ok=True)
    remote = RemoteZip(RAW_URL, RAW_ETAG)
    with remote, zipfile.ZipFile(remote) as source:
        frames = sorted((m for m in source.infolist() if m.filename.startswith(CAMERA_PREFIX + 'data/') and m.filename.endswith('.png')), key=lambda m: m.filename)
        if not frames:
            raise ValueError('No left-color camera frames in the selected drive.')
        timestamps = source.read(CAMERA_PREFIX + 'timestamps.txt').decode().splitlines()
        if len(frames) != len(timestamps):
            raise ValueError('Camera frame/timestamp count mismatch.')
        for index, member in enumerate(frames):
            filename = PurePosixPath(member.filename).name
            if not filename.removesuffix('.png').isdigit():
                raise ValueError('Unexpected camera frame name.')
            target = camera / filename
            if not crc_matches(target, member):
                payload = source.read(member)  # zipfile verifies each frame CRC.
                pending = target.with_suffix('.png.part')
                pending.write_bytes(payload)
                os.replace(pending, target)
            if index % 20 == 0 or index == len(frames) - 1:
                print(f'Camera frames ready: {index + 1}/{len(frames)}', flush=True)
        (camera / 'timestamps.txt').write_text('\n'.join(timestamps) + '\n')
    times = [timestamp_ns(line) for line in timestamps]
    intervals = [(b - a) / 1e9 for a, b in zip(times, times[1:])]
    if not intervals or any(dt <= 0 or dt > 1 for dt in intervals):
        raise ValueError('Invalid camera timing.')
    concat = data_dir / 'camera_frames.ffconcat'
    lines = ['ffconcat version 1.0']
    for index, member in enumerate(frames):
        path = camera / PurePosixPath(member.filename).name
        lines += [f"file '{path}'", f'duration {intervals[min(index, len(intervals) - 1)]:.9f}']
    lines += [f"file '{path}'"]  # Concat demuxer needs a final repeat for the last duration.
    concat.write_text('\n'.join(lines) + '\n')
    pending = video.with_name('kitti04_left_camera.pending.mp4')
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'warning', '-y', '-f', 'concat', '-safe', '0', '-i', str(concat), '-fps_mode', 'vfr', '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(pending)], check=True)
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height,codec_name:format=duration', '-of', 'json', str(pending)], text=True))
    if not probe.get('streams') or float(probe['format']['duration']) <= 0:
        raise ValueError('Encoded clip has no valid video stream.')
    os.replace(pending, video)
    manifest = {'raw_url': RAW_URL, 'raw_etag': RAW_ETAG, 'raw_archive_size': remote.size,
                'downloaded_range_bytes_this_run': remote.transferred, 'camera': 'image_02: left color, unsynced/unrectified',
                'frame_count': len(frames), 'first_timestamp_ns': times[0], 'last_timestamp_ns': times[-1],
                'camera_start_minus_lidar_start_seconds': (times[0] - bag['cloud_first_ns']) / 1e9,
                'video_path': VIDEO_NAME, 'video_sha256': sha256(video), 'probe': probe,
                'timing': 'Camera timestamp intervals encoded; timestamps.txt retained. Independent video playback is not synchronized with ROS playback.',
                'ground_truth': False, 'crc_verified': True}
    manifest_pending = manifest_path.with_suffix('.json.part')
    manifest_pending.write_text(json.dumps(manifest, indent=2) + '\n')
    os.replace(manifest_pending, manifest_path)
    print(f'Camera clip ready: {video}', flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    args = parser.parse_args()
    data_dir = args.data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    ignore = data_dir / '.gitignore'
    if not ignore.exists():
        ignore.write_text('# Downloaded/generated sample assets; do not commit.\n*\n')
    bag = prepare_bag(data_dir)
    camera = prepare_video(data_dir, bag)
    manifest = {'bag': bag, 'camera': camera, 'accuracy_validated': False}
    pending = data_dir / 'demo_manifest.json.part'
    pending.write_text(json.dumps(manifest, indent=2) + '\n')
    os.replace(pending, data_dir / 'demo_manifest.json')
    (data_dir / 'playback_qos.yaml').write_text('/velodyne_points:\n  reliability: reliable\n  durability: volatile\n  history: keep_last\n  depth: 5\n')
    print('Sample preparation complete.', flush=True)


if __name__ == '__main__':
    main()
