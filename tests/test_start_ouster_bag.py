"""Primary and historical bag routing without starting real Docker containers."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/start_ouster_bag.sh'


class FreshBagLauncherTests(unittest.TestCase):
    def launch(self, args=(), missing_bag=False, **settings):
        with tempfile.TemporaryDirectory(prefix='ouster bag ') as folder:
            root = Path(folder)
            data = root / 'original'
            for name, filename in (('raw01', 'ouster1_raw_01_0-001.mcap'),
                                   ('ouster1', 'ouster1_raw_02_0-001.mcap')):
                bag = data / name
                bag.mkdir(parents=True)
                if not missing_bag:
                    (bag / filename).write_bytes(b'original bytes')
            for name in ('dry', '30mmh', '100mmh'):
                bag = data / ('digitrans_40kmh_' + name)
                bag.mkdir(parents=True)
                if not missing_bag:
                    (bag / 'metadata.yaml').write_text('fixture')
                    (bag / 'original.mcap').write_bytes(b'original bytes')
            docker = root / 'docker'
            capture = root / 'calls.jsonl'
            docker.write_text('''#!/usr/bin/env python3
import json,os,sys
args=sys.argv[1:]
with open(os.environ['BAG_TEST_CALLS'],'a') as output:output.write(json.dumps(args)+'\\n')
if args[:2]==['container','inspect']:sys.exit(0 if os.environ.get('BAG_TEST_EXISTING')=='1' else 1)
if args[:2]==['image','inspect']:sys.exit(1 if os.environ.get('BAG_TEST_NO_IMAGE')=='1' else 0)
if args[0] not in ('info','run'):sys.exit('Unexpected mutation')
''')
            docker.chmod(0o755)
            env = dict(os.environ)
            for key in ('PP_IMAGE', 'PP_OUSTER_CONTAINER', 'PP_BAG_RATE', 'PP_BAG_LOOP',
                        'PP_BAG_DELAY', 'PP_ROSBAGS_DIR', 'PP_OUSTER_FRESH_DIR', 'ROS_DOMAIN_ID',
                        'RMW_IMPLEMENTATION', 'OUSTER_POINT_CLOUD_TOPIC'):
                env.pop(key, None)
            env.update(PATH=str(root) + ':' + env['PATH'], BAG_TEST_CALLS=str(capture),
                       PP_OUSTER_FRESH_DIR=str(data), PP_ROSBAGS_DIR=str(data), **settings)
            result = subprocess.run(['bash', str(SCRIPT), *args], env=env,
                                    text=True, capture_output=True, timeout=5)
            calls = [json.loads(line) for line in capture.read_text().splitlines()] if capture.exists() else []
            for path in data.rglob('*.mcap'):
                self.assertEqual(path.read_bytes(), b'original bytes')
            return result, calls

    def test_zero_delay_is_omitted_and_positive_delay_is_preserved(self):
        for delay in ('0', '0.0', '00.000'):
            with self.subTest(delay=delay):
                result, calls = self.launch(PP_BAG_DELAY=delay, PP_BAG_LOOP='0', PP_BAG_RATE='1.0')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn('--delay', calls[-1])
                self.assertNotIn('--loop', calls[-1])
                self.assertIn('--disable-keyboard-controls', calls[-1])
        for delay in ('3', '0.1'):
            with self.subTest(delay=delay):
                result, calls = self.launch(PP_BAG_DELAY=delay)
                self.assertEqual(result.returncode, 0, result.stderr)
                run = calls[-1]
                self.assertEqual(run[run.index('--delay') + 1], delay)

    def test_default_mounts_primary_raw01_readonly_without_metadata(self):
        result, calls = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        run = calls[-1]
        self.assertEqual(run[0], 'run')
        self.assertIn('--pull=never', run)
        self.assertIn('pp-infer:jazzy-trt10', run)
        self.assertIn('ROS_DOMAIN_ID=99', run)
        self.assertIn('RMW_IMPLEMENTATION=rmw_fastrtps_cpp', run)
        self.assertIn('--loop', run)
        self.assertNotIn('--remap', run)
        mount = run[run.index('--mount') + 1]
        self.assertIn('/raw01/ouster1_raw_01_0-001.mcap,target=/bag.mcap,readonly', mount)
        self.assertIn('ouster bag ', mount)
        self.assertEqual(run[run.index('--topics') + 1], '/ouster1/points')
        self.assertEqual(run[run.index('--storage') + 1], 'mcap')
        self.assertIn('/bag.mcap', run)

    def test_second_primary_and_topic_override(self):
        result, calls = self.launch(('ouster1',), OUSTER_POINT_CLOUD_TOPIC='/experiment/points')
        self.assertEqual(result.returncode, 0, result.stderr)
        run = calls[-1]
        self.assertIn('/ouster1/ouster1_raw_02_0-001.mcap,target=/bag.mcap,readonly',
                      run[run.index('--mount') + 1])
        self.assertEqual(run[run.index('--topics') + 1], '/ouster1/points')
        self.assertIn('/ouster1/points:=/experiment/points', run)

    def test_historical_default_remaps_to_shared_adapter_topic(self):
        result, calls = self.launch(('dry',))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('/sensing/lidar/points:=/ouster1/points', calls[-1])
        self.assertNotIn('--storage', calls[-1])

    def test_other_recordings_and_custom_routing(self):
        for selection, suffix in [('rain30', '30mmh'), ('rain100', '100mmh')]:
            result, calls = self.launch((selection,), ROS_DOMAIN_ID='7', PP_BAG_LOOP='0',
                                        PP_BAG_RATE='1', PP_BAG_DELAY='0', PP_IMAGE='custom:image',
                                        OUSTER_POINT_CLOUD_TOPIC='/ouster1/points', RMW_IMPLEMENTATION='rmw_zenoh_cpp')
            self.assertEqual(result.returncode, 0, result.stderr)
            run = calls[-1]
            self.assertIn('/digitrans_40kmh_' + suffix + ',target=/bag,readonly', run[run.index('--mount') + 1])
            self.assertNotIn('--loop', run)
            self.assertIn('ROS_DOMAIN_ID=7', run)
            self.assertIn('custom:image', run)
            self.assertIn('RMW_IMPLEMENTATION=rmw_zenoh_cpp', run)
            self.assertIn('/sensing/lidar/points:=/ouster1/points', run)

    def test_existing_player_and_missing_image_are_preserved(self):
        for flag in ('BAG_TEST_EXISTING', 'BAG_TEST_NO_IMAGE'):
            result, calls = self.launch(**{flag: '1'})
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(any(call[0] in ('run', 'stop', 'rm', 'pull', 'build') for call in calls))

    def test_invalid_settings_and_missing_source_do_not_call_docker(self):
        for settings in ({'PP_BAG_RATE': '0'}, {'PP_BAG_LOOP': 'yes'}, {'PP_BAG_DELAY': '-1'},
                         {'ROS_DOMAIN_ID': '233'}, {'OUSTER_POINT_CLOUD_TOPIC': 'relative'}):
            result, calls = self.launch(**settings)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(calls, [])
        result, calls = self.launch(missing_bag=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])
        result, calls = self.launch(('unknown',))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])
        result, calls = self.launch(('--help',), missing_bag=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
