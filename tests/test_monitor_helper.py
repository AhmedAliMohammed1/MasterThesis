"""Read-only monitor routing and failure handling without touching real containers."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/monitor_detections.sh'


class MonitorHelperTests(unittest.TestCase):
    def run_helper(self, mode, **settings):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            capture = directory / 'calls.jsonl'
            docker = directory / 'docker'
            docker.write_text('''#!/usr/bin/env python3
import json,os,sys,time
with open(os.environ['MONITOR_CALLS'], 'a') as output:
    output.write(json.dumps(sys.argv[1:])+'\\n')
if sys.argv[1] == 'inspect':
    print(os.environ.get('MONITOR_RUNNING','true'))
elif sys.argv[1] == 'exec':
    if os.environ.get('MONITOR_HANG') == '1':
        limit=sys.argv[sys.argv.index('timeout')+2]
        time.sleep(float(limit[:-1]))
        raise SystemExit(124)
    print('published_count: 7')
else:
    raise SystemExit('Unexpected mutation or command')
''')
            docker.chmod(0o755)
            env = dict(os.environ)
            for key in ['ROS_DOMAIN_ID', 'DETECTIONS_TOPIC', 'PP_CONTAINER_NAME', 'PP_NODE_NAME',
                        'PP_MONITOR_BACKEND', 'PP_MONITOR_TIMEOUT']:
                env.pop(key, None)
            env.update(PATH=str(directory) + ':' + env['PATH'], MONITOR_CALLS=str(capture),
                       PP_MONITOR_BACKEND='docker', **settings)
            result = subprocess.run(['bash', str(SCRIPT), mode], env=env,
                                    capture_output=True, text=True, timeout=8)
            calls = [json.loads(line) for line in capture.read_text().splitlines()] if capture.exists() else []
            return result, calls

    def test_snapshot_reads_retained_statistics_without_mutation(self):
        result, calls = self.run_helper('once')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('published_count: 7', result.stdout)
        self.assertEqual([call[0] for call in calls], ['inspect', 'exec'])
        self.assertEqual(calls[1], ['exec', 'pointpillars', '/entrypoint.sh', 'timeout', '--foreground', '10s', 'ros2', 'topic', 'echo',
                                   '/bbox/stats', 'diagnostic_msgs/msg/DiagnosticArray',
                                   '--qos-durability', 'transient_local', '--once'])

    def test_custom_topic_domain_and_container(self):
        result, calls = self.run_helper('watch', ROS_DOMAIN_ID='42', DETECTIONS_TOPIC='/kitti/predictions',
                                        PP_CONTAINER_NAME='pointpillars-validation')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[1][:4], ['exec', '-e', 'ROS_DOMAIN_ID=42', 'pointpillars-validation'])
        self.assertIn('/kitti/predictions/stats', calls[1])
        self.assertNotIn('--once', calls[1])

    def test_threshold_is_a_read_not_a_parameter_change(self):
        result, calls = self.run_helper('threshold', PP_NODE_NAME='/minimal_publisher')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[1][-4:], ['param', 'get', '/minimal_publisher', 'confidence_threshold'])

    def test_stopped_container_is_not_started_or_read_as_zero(self):
        result, calls = self.run_helper('once', MONITOR_RUNNING='false')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn('not running', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_missing_response_is_bounded_and_explained(self):
        result, calls = self.run_helper('once', MONITOR_HANG='1', PP_MONITOR_TIMEOUT='0.1')
        self.assertEqual(result.returncode, 124)
        self.assertIn('No counters are assumed to be zero', result.stderr)

    def test_invalid_settings_refused_before_container_access(self):
        for settings in [{'DETECTIONS_TOPIC': 'bbox'}, {'PP_MONITOR_TIMEOUT': '0'},
                         {'PP_MONITOR_TIMEOUT': '-1'}]:
            result, calls = self.run_helper('once', **settings)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
