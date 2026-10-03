#!/usr/bin/env python3
"""Prepare a reproducible labeled diagnostic subset, never an accuracy certificate."""
import argparse
from collections import Counter
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

from kitti_geometry import Calibration, convert_box, difficulty, inspect_cloud, parse_labels, png_dimensions
from prepare_kitti_demo import RemoteZip, crc_matches, sha256

ROOT = Path(__file__).resolve().parents[1]
ALGORITHM = 'drive-disjoint-annotation-coverage-v1'
TARGET_CLASSES = ('Car', 'Pedestrian', 'Cyclist')
BUCKETS = ([f'class:{c}' for c in TARGET_CLASSES] + ['near', 'far', 'isolated', 'crowded',
           'occluded', 'truncated', 'easy', 'moderate', 'hard', 'outside_difficulty'])


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def identity(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.part')
    with pending.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)


def freeze_json(path, value):
    data = encoded(value)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f'Frozen file differs: {path}; use a new output directory for another selection/recipe')
    else:
        atomic_write(path, data)


def validate_members(archive):
    members = archive.infolist()
    if len(members) > 50000:
        raise ValueError('Too many ZIP members')
    seen = set()
    for m in members:
        p = PurePosixPath(m.filename)
        mode = m.external_attr >> 16
        if m.filename in seen or p.is_absolute() or '..' in p.parts or '\\' in m.filename or stat.S_ISLNK(mode):
            raise ValueError('Unsafe/duplicate ZIP member: ' + m.filename)
        seen.add(m.filename)
        if m.flag_bits & 1:
            raise ValueError('Encrypted ZIP member is unsupported')
    return identity([{'name': m.filename, 'bytes': m.file_size, 'crc32': f'{m.CRC:08x}'}
                     for m in sorted(members, key=lambda m: m.filename)])


def extract_member(archive, name, path, max_bytes):
    m = archive.getinfo(name)
    if m.file_size > max_bytes or m.is_dir():
        raise ValueError('Unexpected member size/type: ' + name)
    if path.exists():
        if not crc_matches(path, m):
            raise ValueError(f'Existing asset is changed or corrupt: {path}; preserve it and inspect before retrying')
        return
    pending = path.with_name(path.name + '.part')
    if crc_matches(pending, m):
        os.replace(pending, path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(m) as source, pending.open('wb') as output:
        total = 0
        while chunk := source.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise ValueError('Member exceeded extraction limit')
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    if not crc_matches(pending, m):
        raise ValueError('Pending asset CRC/size mismatch: ' + name)
    os.replace(pending, path)


class Sources:
    def __init__(self, config, cache, archives_dir=None):
        self.config, self.cache, self.archives_dir = config, cache, archives_dir
        self.stack = contextlib.ExitStack()
        self.archives, self.records, self.streams = {}, {}, {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stack.__exit__(*args)

    def open(self, kind):
        if kind in self.archives:
            return self.archives[kind]
        spec = self.config['archives'][kind]
        local = self.archives_dir / spec['file'] if self.archives_dir else None
        record = {'file': spec['file']}
        if local:
            if local.stat().st_size != spec['bytes']:
                raise ValueError('Offline archive size differs from pinned official object: ' + str(local))
            stream = self.stack.enter_context(local.open('rb'))
            record.update({'mode': 'offline-user-provided', 'bytes': local.stat().st_size,
                           'publisher_authentication': 'not established by size/CRC; selected member SHA256 recorded'})
        elif spec['bytes'] <= 8 * 1024 * 1024:
            local = self.cache / spec['file']
            expected_sha = spec['sha256']
            pending = local.with_name(local.name + '.part')
            if not local.exists() and pending.is_file() and pending.stat().st_size == spec['bytes'] and sha256(pending) == expected_sha:
                os.replace(pending, local)
            if local.exists():
                if sha256(local) != expected_sha or local.stat().st_size != spec['bytes']:
                    raise ValueError('Small archive cache changed: ' + str(local))
            else:
                with RemoteZip(spec['url'], spec['etag']) as remote:
                    if remote.size != spec['bytes']:
                        raise ValueError('Source size changed')
                    data = remote.read()
                if hashlib.sha256(data).hexdigest() != expected_sha:
                    raise ValueError('Small archive SHA256 mismatch')
                # Validate layout before promoting; a completed pending file can resume.
                import io
                with zipfile.ZipFile(io.BytesIO(data)) as check:
                    validate_members(check)
                atomic_write(local, data)
            stream = self.stack.enter_context(local.open('rb'))
            record.update({'mode': 'pinned-public-small-archive', 'url': spec['url'],
                           'etag': spec['etag'], 'bytes': spec['bytes'], 'archive_sha256': sha256(local)})
        else:
            stream = self.stack.enter_context(RemoteZip(spec['url'], spec['etag']))
            if stream.size != spec['bytes']:
                raise ValueError('Source size changed')
            self.streams[kind] = stream
            record.update({'mode': 'pinned-public-byte-ranges', 'url': spec['url'],
                           'etag': spec['etag'], 'bytes': spec['bytes']})
        archive = self.stack.enter_context(zipfile.ZipFile(stream))
        record['member_directory_sha256'] = validate_members(archive)
        self.records[kind], self.archives[kind] = record, archive
        return archive


def recording_groups(devkit, frame_count):
    permutation = [int(x) for x in re.split(r'[\s,]+', devkit.read('mapping/train_rand.txt').decode().strip()) if x]
    rows = [line.split() for line in devkit.read('mapping/train_mapping.txt').decode().splitlines() if line.strip()]
    if len(permutation) != frame_count or sorted(permutation) != list(range(1, frame_count+1)) or len(rows) != frame_count:
        raise ValueError('Invalid KITTI raw recording mapping/permutation')
    result = {}
    for i, index in enumerate(permutation):
        row = rows[index-1]
        if len(row) != 3:
            raise ValueError('Invalid recording mapping row')
        result[f'{i:06d}'] = {'date': row[0], 'drive': row[1], 'raw_frame': row[2], 'group': row[0] + '/' + row[1]}
    return result


def scenario_tags(labels):
    relevant = [label for label in labels if label['type'] in TARGET_CLASSES]
    tags = {f'class:{label["type"]}' for label in relevant}
    if len(relevant) == 1:
        tags.add('isolated')
    if len(relevant) >= 5:
        tags.add('crowded')
    for label in relevant:
        depth = label['bottom_center_camera'][2]
        if 0 < depth < 20:
            tags.add('near')
        if depth >= 40:
            tags.add('far')
        if label['occluded'] in (1, 2):
            tags.add('occluded')
        if label['truncated'] > .15:
            tags.add('truncated')
        tags.add(difficulty(label))
    return sorted(tags)


def select_frames(cohort, groups, per_split, seed):
    if per_split < 3:
        raise ValueError('At least three frames per split are required')
    result, coverage = {}, {}
    for split, parity in [('tuning', 0), ('test', 1)]:
        candidates = {f: scenario_tags(labels) for f, labels in cohort.items()
                      if int(hashlib.sha256((seed + ':' + groups[f]['group']).encode()).hexdigest(), 16) % 2 == parity}
        candidates = {f: tags for f, tags in candidates.items() if tags}
        if len(candidates) < per_split:
            raise ValueError('Not enough labeled candidates in ' + split)
        frequency = Counter(tag for tags in candidates.values() for tag in tags)
        counts = Counter()
        chosen = []
        for _ in range(per_split):
            # Cover missing scenarios first; prefer rare classes, then balance repeats.
            def rank(frame):
                tags = candidates[frame]
                novelty = sum(counts[tag] == 0 for tag in tags)
                balance = sum(1 / ((1+counts[tag]) * frequency[tag]) for tag in tags)
                tie = hashlib.sha256((seed + ':' + split + ':' + frame).encode()).hexdigest()
                return (-novelty, -balance, tie)
            frame = min(candidates, key=rank)
            tags = candidates.pop(frame)
            chosen.append({'frame_id': frame, 'scenarios': tags, 'recording': groups[frame]})
            counts.update(tags)
        result[split] = chosen
        coverage[split] = {'frames_per_bucket': dict(sorted(counts.items())),
                           'missing_buckets': sorted(set(BUCKETS) - set(counts))}
        if any(counts[f'class:{c}'] == 0 for c in TARGET_CLASSES):
            raise ValueError('Selection failed class coverage; increase count or change seed in a new output directory')
    return result, coverage


def prepare(output, *, per_split=16, seed='pp-kitti-diagnostic-v1', archives_dir=None,
            sources_path=ROOT/'config/kitti_sources.json', contract_path=ROOT/'config/model_contract.json'):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    atomic_write(output / '.gitignore', b'*\n!.gitignore\n')
    with (output / '.prepare.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config = json.loads(sources_path.read_text())
        contract = json.loads(contract_path.read_text())
        spatial_range = contract['input']['voxel_plugin_attributes']['point_cloud_range']
        capacity = contract['input']['tensors'][0]['shape'][1]
        recipe = {'algorithm': ALGORITHM, 'seed': seed, 'frames_per_split': per_split,
                  'model_sha256': contract['model']['sha256'], 'model_spatial_range': spatial_range,
                  'point_capacity': capacity, 'source_config_sha256': sha256(sources_path),
                  'selection_inputs': 'annotations only; raw-drive-disjoint partitions',
                  'class_mapping_to_model': 'pending; original KITTI types retained',
                  'accuracy_evaluator': 'not implemented; no official or custom AP claimed',
                  'pretrained_training_overlap': 'unknown',
                  'tool_sha256': sha256(Path(__file__)), 'geometry_sha256': sha256(ROOT/'tools/kitti_geometry.py'),
                  'http_helper_sha256': sha256(ROOT/'tools/prepare_kitti_demo.py')}
        with Sources(config, output/'.cache', archives_dir) as sources:
            labels_archive = sources.open('label_2')
            ids = [f'{i:06d}' for i in range(config['training_frames'])]
            cohort, hashes = {}, {}
            for frame in ids:
                name = f'training/label_2/{frame}.txt'
                if labels_archive.getinfo(name).file_size > 128 * 1024:
                    raise ValueError('Label file too large')
                data = labels_archive.read(name)
                cohort[frame] = parse_labels(data.decode())
                hashes[frame] = hashlib.sha256(data).hexdigest()
            devkit = sources.open('devkit')
            groups = recording_groups(devkit, len(ids))
            splits, coverage = select_frames(cohort, groups, per_split, seed)
            selection = {'schema_version': 1, 'recipe': recipe, 'cohort_annotation_sha256': identity(hashes),
                         'raw_mapping_sha256': identity(groups), 'splits': splits, 'coverage': coverage}
            freeze_json(output/'selection.json', selection)
            frames = []
            for split, selected in splits.items():
                for selected_frame in selected:
                    frame = selected_frame['frame_id']
                    print(f'Preparing {split} frame {frame}', flush=True)
                    paths = {}
                    for kind, extension, limit in [('label_2', 'txt', 128*1024), ('calib', 'txt', 128*1024),
                                                    ('velodyne', 'bin', 16*1024*1024), ('image_2', 'png', 8*1024*1024)]:
                        name = f'training/{kind}/{frame}.{extension}'
                        path = output/name
                        extract_member(sources.open(kind), name, path, limit)
                        paths[kind] = path
                    calibration = Calibration(paths['calib'].read_text())
                    image_size = png_dimensions(paths['image_2'].read_bytes())
                    objects = []
                    for label in cohort[frame]:
                        objects.append({'annotation_camera': label, 'box_lidar': convert_box(label, calibration, spatial_range)})
                    cloud = inspect_cloud(paths['velodyne'].read_bytes(), spatial_range, capacity)
                    if cloud['nonfinite_points'] or cloud['exceeds_engine_capacity']:
                        raise ValueError(f'Invalid/runtime-capacity cloud: {frame}: {cloud}')
                    report = {'frame_id': frame, 'split': split, 'scenarios': selected_frame['scenarios'],
                              'recording': selected_frame['recording'], 'image_dimensions': image_size,
                              'point_cloud_audit': cloud, 'objects': objects,
                              'assets': {kind: {'path': path.relative_to(output).as_posix(), 'bytes': path.stat().st_size,
                                                'sha256': sha256(path)} for kind, path in paths.items()}}
                    freeze_json(output/f'annotations_lidar/{frame}.json', report)
                    frames.append(report)
            summary = {'frames': len(frames), 'point_clouds': {
                'min_points': min(f['point_cloud_audit']['points'] for f in frames),
                'max_points': max(f['point_cloud_audit']['points'] for f in frames),
                'intensity_outside_0_1': sum(f['point_cloud_audit']['intensity_outside_0_1'] for f in frames)},
                'objects_by_original_class': dict(sorted(Counter(o['annotation_camera']['type'] for f in frames for o in f['objects']).items())),
                'object_coverage': {}}
            for kind in TARGET_CLASSES:
                boxes = [o['box_lidar'] for f in frames for o in f['objects'] if o['annotation_camera']['type'] == kind]
                summary['object_coverage'][kind] = {'objects': len(boxes),
                    'centers_in_model_range': sum(b['center_in_model_range'] for b in boxes),
                    'all_corners_in_model_range': sum(b['all_corners_in_model_range'] for b in boxes)}
            manifest = {'schema_version': 1, 'status': 'diagnostic-data-prepared; inference-and-accuracy-pending',
                        'selection_sha256': sha256(output/'selection.json'), 'recipe': recipe,
                        'sources': sources.records, 'coverage': coverage, 'summary': summary,
                        'frames': [{k: f[k] for k in ('frame_id', 'split', 'recording', 'scenarios', 'assets')} for f in frames]}
            freeze_json(output/'manifest.json', manifest)
            print(json.dumps(summary, indent=2), flush=True)
            print('Manifest:', output/'manifest.json', flush=True)
            print('Network bytes this run:', {k: s.transferred for k, s in sources.streams.items()}, flush=True)
            return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames-per-split', type=int, default=16)
    parser.add_argument('--seed', default='pp-kitti-diagnostic-v1')
    parser.add_argument('--archives-dir', type=Path, help='Use official ZIP downloads locally, without HTTP')
    args = parser.parse_args()
    try:
        prepare(args.output, per_split=args.frames_per_split, seed=args.seed, archives_dir=args.archives_dir)
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, f'Preparation failed: {error}\nCompleted assets preserved; rerun the identical command after resolving the error.\n')


if __name__ == '__main__':
    main()
