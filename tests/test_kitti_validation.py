"""Independent calibration fixtures, deterministic selection and preparation recovery."""
import contextlib
import io
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import kitti_geometry as geometry
import prepare_kitti_validation as preparation

RANGE = [-51.2, -51.2, -1.4, 51.2, 51.2, 4.4]
CALIB = ('P2: 100 0 50 0 0 100 40 0 0 0 1 0\n'
         'R0_rect: 1 0 0 0 1 0 0 0 1\n'
         'Tr_velo_to_cam: 0 -1 0 0 0 0 -1 0 1 0 0 0\n')
LABEL = 'Car 0 0 0 10 20 90 80 2 2 4 0 1 10 0\n'


def image_header(width=1242, height=375):
    chunk = b'IHDR' + struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + chunk + struct.pack('>I', zlib.crc32(chunk))


class GeometryTests(unittest.TestCase):
    def assertVector(self, actual, expected):
        for x, y in zip(actual, expected):
            self.assertAlmostEqual(x, y, places=8)

    def test_center_dimensions_corners_heading_independent_fixture(self):
        box = geometry.convert_box(geometry.parse_labels(LABEL)[0], geometry.Calibration(CALIB), RANGE)
        self.assertVector(box['center_lidar'], [10, 0, 0])
        self.assertEqual(box['dimensions_lwh'], [4, 2, 2])
        self.assertAlmostEqual(box['yaw_lidar_diagnostic'], -math.pi/2)
        # Construct expected extents directly, without the conversion's matrix math.
        expected = {(x, y, z) for x in (9, 11) for y in (-2, 2) for z in (-1, 1)}
        actual = {tuple(round(v, 8) for v in p) for p in box['corners_lidar']}
        self.assertEqual(actual, expected)
        self.assertTrue(box['all_corners_in_model_range'])

    def test_quarter_turn_heading_and_corners(self):
        label = geometry.parse_labels(LABEL)[0]
        label['rotation_y'] = math.pi/2
        box = geometry.convert_box(label, geometry.Calibration(CALIB), RANGE)
        self.assertVector(box['heading_lidar'], [-1, 0, 0])
        expected = {(x, y, z) for x in (8, 12) for y in (-1, 1) for z in (-1, 1)}
        self.assertEqual({tuple(round(v, 8) for v in p) for p in box['corners_lidar']}, expected)

    def test_nontrivial_rectification_translation_and_projection(self):
        text = CALIB.replace('R0_rect: 1 0 0 0 1 0 0 0 1', 'R0_rect: 0 -1 0 1 0 0 0 0 1')
        text = text.replace('0 -1 0 0 0 0 -1 0 1 0 0 0', '0 -1 0 1 0 0 -1 2 1 0 0 3')
        calib = geometry.Calibration(text)
        # LiDAR (7,2,-4) -> unrectified camera(-1,6,10) -> rectified(-6,-1,10).
        self.assertVector(calib.to_camera([7, 2, -4]), [-6, -1, 10])
        self.assertVector(calib.to_lidar([-6, -1, 10]), [7, 2, -4])
        self.assertVector(calib.project_camera([-6, -1, 10]), [-10, 30])
        label = geometry.parse_labels(LABEL)[0]
        label['bottom_center_camera'] = [-6, 0, 10]
        box = geometry.convert_box(label, calib, RANGE)
        self.assertVector(box['center_lidar'], [7, 2, -4])
        self.assertVector(box['heading_lidar'], [0, 0, 1])
        # Rectification tilt must survive; a yaw-only reconstruction would lose this.
        self.assertGreater(abs(box['orientation_lidar'][2][0]), .99)
        self.assertFalse(box['center_in_model_range'])

    def test_invalid_calibration_and_duplicate_keys(self):
        for text in [CALIB.replace('R0_rect:', 'unused:'), CALIB + 'P2: 1\n',
                     CALIB.replace('1 0 0 0 1 0 0 0 1', '-1 0 0 0 1 0 0 0 1'),
                     CALIB.replace('100', 'nan')]:
            with self.assertRaises(ValueError):
                geometry.Calibration(text)
        with self.assertRaises(ValueError):
            geometry.inverse3([[0]*3]*3)

    def test_behind_camera_has_no_projection(self):
        self.assertIsNone(geometry.Calibration(CALIB).project_camera([1, 2, -1]))

    def test_dontcare_retains_image_region_without_3d_box(self):
        label = geometry.parse_labels('DontCare -1 -1 -10 1 2 3 4 -1 -1 -1 -1000 -1000 -1000 -10')[0]
        self.assertIsNone(geometry.convert_box(label, geometry.Calibration(CALIB), RANGE))
        self.assertEqual(label['bbox_image'], [1, 2, 3, 4])
        self.assertEqual(geometry.difficulty(label), 'ignore')

    def test_label_validation_and_difficulty(self):
        label = geometry.parse_labels(LABEL)[0]
        self.assertEqual(geometry.difficulty(label), 'easy')
        label.update(occluded=1, truncated=.25)
        self.assertEqual(geometry.difficulty(label), 'moderate')
        label.update(occluded=2, truncated=.4)
        self.assertEqual(geometry.difficulty(label), 'hard')
        label['occluded'] = 3
        self.assertEqual(geometry.difficulty(label), 'outside_difficulty')
        for text in [LABEL + 'broken', LABEL.replace('Car', 'Unknown'), LABEL.replace('2 2 4', '-2 2 4'),
                     LABEL.replace('0 1 10', 'nan 1 10'), LABEL.rstrip() + ' .9', LABEL.replace('0 0 0 10', '0 .5 0 10')]:
            with self.assertRaises(ValueError):
                geometry.parse_labels(text)

    def test_cloud_endianness_finite_range_and_capacity(self):
        data = b''.join(struct.pack('<ffff', *p) for p in [(1, 2, 3, .5), (1, 2, -2, 2), (math.nan, 0, 0, .2)])
        report = geometry.inspect_cloud(data, RANGE, 2)
        self.assertEqual(report['points'], 3)
        self.assertEqual(report['finite_points_in_model_range'], 1)
        self.assertEqual(report['nonfinite_points'], 1)
        self.assertEqual(report['intensity_outside_0_1'], 1)
        self.assertTrue(report['exceeds_engine_capacity'])
        for data in [b'', b'bad']:
            with self.assertRaises(ValueError):
                geometry.inspect_cloud(data, RANGE, 2)

    def test_png_header_dimensions_and_integrity(self):
        self.assertEqual(geometry.png_dimensions(image_header()), [1242, 375])
        for data in [b'not png', image_header()[:-1], image_header()[:-1] + b'X', image_header(0, 1)]:
            with self.assertRaises(ValueError):
                geometry.png_dimensions(data)


class PreparationTests(unittest.TestCase):
    def test_safe_zip_layout_and_duplicates(self):
        for name in ['../outside', '/absolute', 'a\\b']:
            payload = io.BytesIO()
            with zipfile.ZipFile(payload, 'w') as z:
                z.writestr(name, b'bad')
            with zipfile.ZipFile(io.BytesIO(payload.getvalue())) as z:
                with self.assertRaisesRegex(ValueError, 'Unsafe'):
                    preparation.validate_members(z)

    def test_pending_promotion_and_preserved_corrupt_final(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, 'w') as z:
            z.writestr('member', b'expected')
        with tempfile.TemporaryDirectory() as directory, zipfile.ZipFile(io.BytesIO(payload.getvalue())) as z:
            path = Path(directory)/'asset'
            path.with_name('asset.part').write_bytes(b'expected')
            with patch.object(z, 'open', side_effect=AssertionError('No download needed')):
                preparation.extract_member(z, 'member', path, 100)
            self.assertEqual(path.read_bytes(), b'expected')
            path.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'changed or corrupt'):
                preparation.extract_member(z, 'member', path, 100)
            self.assertEqual(path.read_bytes(), b'corrupt')

    def test_small_archive_completed_pending_resumes_without_http(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, 'w') as z:
            z.writestr('member', b'content')
        data = payload.getvalue()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'labels.zip.part').write_bytes(data)
            spec = {'file': 'labels.zip', 'url': 'https://unused.invalid/archive',
                    'etag': '"pinned"', 'bytes': len(data), 'sha256': preparation.hashlib.sha256(data).hexdigest()}
            with patch.object(preparation, 'RemoteZip', side_effect=AssertionError('No HTTP needed')):
                with preparation.Sources({'archives': {'label_2': spec}}, root) as sources:
                    self.assertEqual(sources.open('label_2').read('member'), b'content')
            self.assertFalse((root/'labels.zip.part').exists())
            (root/'labels.zip').write_bytes(b'corrupt')
            with preparation.Sources({'archives': {'label_2': spec}}, root) as sources:
                with self.assertRaisesRegex(ValueError, 'cache changed'):
                    sources.open('label_2')

    def test_downloaded_small_archive_hash_mismatch_never_promotes(self):
        from test_kitti_demo import serve
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, 'w') as z:
            z.writestr('member', b'content')
        with tempfile.TemporaryDirectory() as directory, serve(payload.getvalue()) as (url, _):
            spec = {'file': 'labels.zip', 'url': url, 'etag': '"test-object"',
                    'bytes': len(payload.getvalue()), 'sha256': '0'*64}
            root = Path(directory)
            with preparation.Sources({'archives': {'label_2': spec}}, root) as sources:
                with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
                    sources.open('label_2')
            self.assertFalse((root/'labels.zip').exists())

    def make_archives(self, directory):
        # Six frames from two drives; choose names belonging to opposite partitions.
        seed = 'pp-kitti-diagnostic-v1'
        groups = {}
        for i in range(100):
            name = f'{i:04d}'
            parity = int(preparation.hashlib.sha256((seed + ':2011_09_28/' + name).encode()).hexdigest(), 16) % 2
            groups.setdefault(parity, name)
            if len(groups) == 2:
                break
        config = {'training_frames': 6, 'archives': {}}
        for kind in ['label_2', 'calib', 'velodyne', 'image_2', 'devkit']:
            path = directory/(kind + '.zip')
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
                if kind == 'devkit':
                    z.writestr('mapping/train_rand.txt', '1,2,3,4,5,6')
                    z.writestr('mapping/train_mapping.txt', '\n'.join(f'2011_09_28 {groups[i//3]} {i}' for i in range(6)))
                else:
                    for i in range(6):
                        if kind == 'label_2':
                            data = LABEL + LABEL.replace('Car', 'Pedestrian') + LABEL.replace('Car', 'Cyclist')
                            ext = 'txt'
                        elif kind == 'calib':
                            data, ext = CALIB, 'txt'
                        elif kind == 'velodyne':
                            data, ext = struct.pack('<ffff', 10, 0, 0, .5), 'bin'
                        else:
                            data, ext = image_header(), 'png'
                        z.writestr(f'training/{kind}/{i:06d}.{ext}', data)
            config['archives'][kind] = {'file': path.name, 'bytes': path.stat().st_size}
        config_path = directory/'sources.json'
        config_path.write_bytes(preparation.encoded(config))
        return config_path

    def test_full_offline_prepare_interruption_resume_and_split(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            sources = self.make_archives(root)
            output = root/'dataset'
            extract = preparation.extract_member
            calls = 0
            def interrupted(*args):
                nonlocal calls
                if '/velodyne/' in args[1]:
                    calls += 1
                    if calls == 2:
                        raise OSError('simulated interruption')
                return extract(*args)
            with patch.object(preparation, 'extract_member', side_effect=interrupted):
                with self.assertRaisesRegex(OSError, 'simulated'):
                    preparation.prepare(output, per_split=3, archives_dir=root, sources_path=sources)
            self.assertTrue((output/'selection.json').exists())
            self.assertFalse((output/'manifest.json').exists())
            first = preparation.prepare(output, per_split=3, archives_dir=root, sources_path=sources)
            second = preparation.prepare(output, per_split=3, archives_dir=root, sources_path=sources)
            self.assertEqual(first, second)
            self.assertEqual(first['summary']['frames'], 6)
            tuning = {f['recording']['group'] for f in first['frames'] if f['split'] == 'tuning'}
            test = {f['recording']['group'] for f in first['frames'] if f['split'] == 'test'}
            self.assertFalse(tuning & test)
            selection = json.loads((output/'selection.json').read_text())
            self.assertEqual({x['frame_id'] for x in selection['splits']['tuning']} &
                             {x['frame_id'] for x in selection['splits']['test']}, set())
            # Reproducible manifests must be independent of the absolute output path.
            other = preparation.prepare(root/'other', per_split=3, archives_dir=root, sources_path=sources)
            self.assertEqual(first, other)
            cloud = output/first['frames'][0]['assets']['velodyne']['path']
            cloud.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'changed or corrupt'):
                preparation.prepare(output, per_split=3, archives_dir=root, sources_path=sources)
            self.assertEqual(cloud.read_bytes(), b'corrupt')

    def test_frozen_manifest_requires_new_destination_for_changed_recipe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'selection.json'
            preparation.freeze_json(path, {'seed': 'first'})
            preparation.freeze_json(path, {'seed': 'first'})
            with self.assertRaisesRegex(ValueError, 'Frozen file differs'):
                preparation.freeze_json(path, {'seed': 'second'})
            self.assertEqual(json.loads(path.read_text()), {'seed': 'first'})


if __name__ == '__main__':
    unittest.main()
