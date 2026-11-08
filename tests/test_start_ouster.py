"""Ouster launcher routing and supervisor lifecycle without Docker/GPU access."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'tools/start_ouster.sh'
SUPERVISOR = ROOT / 'docker/ouster_stack.sh'


class OusterLauncherTests(unittest.TestCase):
    def launch(self, args=(), **settings):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            capture = directory / 'calls.jsonl'
            docker = directory / 'docker'
            docker.write_text('''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ['TEST_DOCKER_CALLS'], 'a') as stream:
    stream.write(json.dumps(args) + '\\n')
if args[:2] == ['container', 'inspect']:
    sys.exit(0 if os.environ.get('TEST_EXISTING') == '1' else 1)
if args[:2] == ['image', 'inspect']:
    sys.exit(1 if os.environ.get('TEST_MISSING_IMAGE') == '1' else 0)
if args[0] == 'run' and '--entrypoint' in args:
    sys.exit(1 if os.environ.get('TEST_MISSING_ADAPTER') == '1' else 0)
if args[0] not in ('info', 'run'):
    sys.exit('Unexpected Docker mutation')
''')
            docker.chmod(0o755)
            env = dict(os.environ)
            for key in ('PP_IMAGE', 'PP_CONTAINER_NAME', 'PP_ENGINE_VOLUME', 'ROS_DOMAIN_ID',
                        'RMW_IMPLEMENTATION', 'POINT_CLOUD_TOPIC', 'DETECTIONS_TOPIC',
                        'OUSTER_POINT_CLOUD_TOPIC', 'PP_OUSTER_INTENSITY_SOURCE',
                        'PP_OUSTER_INTENSITY_DIVISOR', 'PP_CONFIDENCE_THRESHOLD',
                        'PP_GPU_INDEX', 'PP_WORKSPACE_MIB'):
                env.pop(key, None)
            env.update(PATH=str(directory) + ':' + env['PATH'], TEST_DOCKER_CALLS=str(capture), **settings)
            result = subprocess.run(['bash', str(LAUNCHER), *args], env=env,
                                    capture_output=True, text=True, timeout=8)
            calls = [json.loads(line) for line in capture.read_text().splitlines()] if capture.exists() else []
            return result, calls

    def test_default_runs_one_stack_and_checks_saved_adapter(self):
        result, calls = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        runs = [call for call in calls if call[0] == 'run']
        self.assertEqual(len(runs), 2)
        self.assertIn('none', runs[0])
        self.assertIn('/usr/bin/test', runs[0])
        self.assertIn('/workspace/install/pp_infer/lib/pp_infer/ouster_adapter', runs[0])
        stack = runs[1]
        self.assertEqual(stack[-3:], ['pp-infer:jazzy-trt10', 'bash', '/ouster-stack.sh'])
        for value in ('--pull=never', '--rm', '--init', 'PP_OUSTER_INTENSITY_SOURCE=reflectivity',
                      'PP_OUSTER_INTENSITY_DIVISOR=255.0', 'RMW_IMPLEMENTATION=rmw_zenoh_cpp',
                      'OUSTER_POINT_CLOUD_TOPIC=/ouster1/points', 'POINT_CLOUD_TOPIC=/point_cloud',
                      'pp-engines:/var/lib/pp_infer'):
            self.assertIn(value, stack)
        mount = stack[stack.index('--mount') + 1]
        self.assertIn(str(SUPERVISOR), mount)  # Checkout path contains spaces.
        self.assertTrue(mount.endswith(',readonly'))
        self.assertNotIn('build', [call[0] for call in calls])

    def test_signal_and_custom_settings(self):
        result, calls = self.launch(('signal',), OUSTER_POINT_CLOUD_TOPIC='/ouster2/points',
                                    POINT_CLOUD_TOPIC='/adapted', RMW_IMPLEMENTATION='rmw_fastrtps_cpp',
                                    ROS_DOMAIN_ID='7', PP_GPU_INDEX='1', PP_CONTAINER_NAME='ouster-two')
        self.assertEqual(result.returncode, 0, result.stderr)
        for value in ('PP_OUSTER_INTENSITY_SOURCE=signal', 'PP_OUSTER_INTENSITY_DIVISOR=65535.0',
                      'OUSTER_POINT_CLOUD_TOPIC=/ouster2/points', 'POINT_CLOUD_TOPIC=/adapted',
                      'RMW_IMPLEMENTATION=rmw_fastrtps_cpp', 'ROS_DOMAIN_ID=7', 'PP_GPU_INDEX=1', 'ouster-two'):
            self.assertIn(value, calls[-1])
        result, calls = self.launch(PP_OUSTER_INTENSITY_SOURCE='signal', PP_OUSTER_INTENSITY_DIVISOR='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PP_OUSTER_INTENSITY_DIVISOR=1.0', calls[-1])

    def test_conflicts_and_old_image_do_not_start_stack(self):
        for setting in ('TEST_EXISTING', 'TEST_MISSING_IMAGE', 'TEST_MISSING_ADAPTER'):
            result, calls = self.launch(**{setting: '1'})
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(any('/ouster-stack.sh' in call for call in calls))
            self.assertFalse(any(call[0] in ('stop', 'rm', 'build', 'pull') for call in calls))
        self.assertIn('current checkout', self.launch(TEST_MISSING_ADAPTER='1')[0].stderr)

    def test_bag_profile_matches_player_without_extra_configuration(self):
        from test_start_ouster_bag import FreshBagLauncherTests
        result, calls = self.launch(('bag',))
        self.assertEqual(result.returncode, 0, result.stderr)
        player_result, player_calls = FreshBagLauncherTests().launch()
        self.assertEqual(player_result.returncode, 0, player_result.stderr)
        for value in ('ROS_DOMAIN_ID=99', 'RMW_IMPLEMENTATION=rmw_fastrtps_cpp',
                      'OUSTER_POINT_CLOUD_TOPIC=/sensing/lidar/points'):
            self.assertIn(value, calls[-1])
            if not value.startswith('OUSTER_'):
                self.assertIn(value, player_calls[-1])
        self.assertIn('pp-infer:jazzy-trt10', calls[-1])
        self.assertIn('pp-infer:jazzy-trt10', player_calls[-1])

    def test_invalid_settings_fail_before_docker(self):
        for settings in ({'PP_OUSTER_INTENSITY_SOURCE': 'auto'}, {'PP_OUSTER_INTENSITY_DIVISOR': '0'},
                         {'PP_OUSTER_INTENSITY_DIVISOR': 'nan'}, {'PP_OUSTER_INTENSITY_DIVISOR': '-1'},
                         {'OUSTER_POINT_CLOUD_TOPIC': '/point_cloud'}, {'ROS_DOMAIN_ID': '233'},
                         {'POINT_CLOUD_TOPIC': 'relative'}, {'OUSTER_POINT_CLOUD_TOPIC': '/a;touch /tmp/no'}):
            result, calls = self.launch(**settings)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(calls, [])
        result, calls = self.launch(('--help',))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls, [])


class OusterSupervisorTests(unittest.TestCase):
    def scenario(self, failing=None, status=7, interrupt=False):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            events = directory / 'events'
            trigger = directory / 'go'
            # Real child and grandchild processes: cleanup must reach both groups.
            script = '''#!/usr/bin/env python3
import os, signal, subprocess, sys, time
from pathlib import Path
tag = Path(sys.argv[0]).name + ('_worker' if '--worker' in sys.argv else '')
def event(text):
    with open(os.environ['STACK_EVENTS'], 'a') as stream:
        stream.write(text + '\\n')
def stop(sig, frame):
    event(tag + ':stop')
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
event(tag + ':ready')
if '--worker' not in sys.argv:
    subprocess.Popen([sys.executable, sys.argv[0], '--worker'])
while True:
    if tag == os.environ.get('STACK_FAIL') and Path(os.environ['STACK_TRIGGER']).exists():
        sys.exit(int(os.environ['STACK_STATUS']))
    time.sleep(0.02)
'''
            adapter = directory / 'adapter'
            detector = directory / 'detector'
            for path in (adapter, detector):
                path.write_text(script); path.chmod(0o755)
            env = dict(os.environ, STACK_EVENTS=str(events), STACK_TRIGGER=str(trigger),
                       STACK_STATUS=str(status), STACK_FAIL=failing or '')
            process = subprocess.Popen(['bash', str(SUPERVISOR), str(adapter), str(detector)],
                                       env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    lines = events.read_text().splitlines() if events.exists() else []
                    if len([line for line in lines if line.endswith(':ready')]) == 4:
                        break
                    time.sleep(0.02)
                else:
                    self.fail('Pipeline children failed to start')
                if interrupt:
                    process.send_signal(signal.SIGINT)
                else:
                    trigger.touch()
                _, errors = process.communicate(timeout=9)
                self.assertEqual(process.returncode, 130 if interrupt else (status or 1), errors)
                lines = events.read_text().splitlines()
                for tag in ('adapter', 'detector', 'adapter_worker', 'detector_worker'):
                    if tag != failing:
                        self.assertIn(tag + ':stop', lines)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=9)

    def test_adapter_failure_stops_detector_and_descendants(self):
        self.scenario(failing='adapter')

    def test_detector_failure_stops_adapter_and_descendants(self):
        self.scenario(failing='detector')

    def test_unexpected_clean_exit_is_reported_as_failure(self):
        self.scenario(failing='detector', status=0)

    def test_ctrl_c_stops_both_process_groups(self):
        self.scenario(interrupt=True)


if __name__ == '__main__':
    unittest.main()
