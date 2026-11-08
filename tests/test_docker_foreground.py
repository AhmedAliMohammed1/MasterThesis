"""One terminal SIGINT must stop the owned container even if CLI ignores it."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

HELPER = Path(__file__).resolve().parents[1] / 'tools/docker_foreground.sh'


class DockerShutdownTests(unittest.TestCase):
    def test_single_ctrl_c_stops_only_own_container_id(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fake = root / 'docker'
            calls = root / 'calls'
            ready = root / 'ready'
            fake.write_text('''#!/usr/bin/env python3
import json,os,signal,sys,time
from pathlib import Path
a=sys.argv[1:]
with open(os.environ['SHUTDOWN_CALLS'],'a') as f:f.write(json.dumps(a)+'\\n')
if a[0]=='run':
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    Path(a[a.index('--cidfile')+1]).write_text('a'*64+'\\n')
    Path(os.environ['SHUTDOWN_READY']).touch()
    end=time.monotonic()+12
    while not Path(os.environ['SHUTDOWN_STOP']).exists() and time.monotonic()<end:time.sleep(.02)
elif a[0]=='stop':
    assert a[-1]=='a'*64
    Path(os.environ['SHUTDOWN_STOP']).touch()
else:sys.exit('Unexpected Docker command')
''')
            fake.chmod(0o755)
            env = dict(os.environ, PATH=str(root) + ':' + os.environ['PATH'],
                       SHUTDOWN_CALLS=str(calls), SHUTDOWN_READY=str(ready),
                       SHUTDOWN_STOP=str(root / 'stopped'))
            process = subprocess.Popen(['bash', '-c', 'source "$1"; pp_run_container --name unrelated-name image',
                                        'test-shell', str(HELPER)], env=env, start_new_session=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(ready.exists(), 'Fake container failed to start')
                start = time.monotonic()
                os.killpg(process.pid, signal.SIGINT)
                _, errors = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 130, errors)
                self.assertLess(time.monotonic() - start, 3)
                observed = [json.loads(line) for line in calls.read_text().splitlines()]
                stops = [call for call in observed if call[0] == 'stop']
                self.assertEqual(stops, [['stop', '--time', '8', 'a' * 64]])
                launched = next(call for call in observed if call[0] == 'run')
                cidfile = Path(launched[launched.index('--cidfile') + 1])
                self.assertFalse(cidfile.parent.exists(), 'Temporary cidfile directory leaked')
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.communicate(timeout=5)
