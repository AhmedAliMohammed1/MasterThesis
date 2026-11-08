"""Dependency reuse, source selection and host GPU preflight with fake Docker."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='deploy checkout ')
        self.root = Path(self.tmp.name)
        for name in ('Dockerfile', '.dockerignore', 'CMakeLists.txt', 'package.xml', 'LICENSE',
                     'docker/node.yaml', 'docker/entrypoint.sh', 'tools/deploy.sh', 'tools/docker_foreground.sh'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        for name in ('src', 'include', 'launch', 'tests/core', 'tests/runtime', 'tests/ros'):
            shutil.copytree(ROOT / name, self.root / name, ignore=shutil.ignore_patterns('__pycache__'))
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.capture = self.root / 'calls'
        self.state = self.root / 'image-label'
        docker = self.bin / 'docker'
        docker.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
a=sys.argv[1:]
with open(os.environ['DEPLOY_CALLS'],'a') as f:f.write(json.dumps(a)+'\\n')
state=Path(os.environ['DEPLOY_STATE'])
if a[:2]==['container','inspect']:sys.exit(0 if os.environ.get('DEPLOY_EXISTS')=='1' else 1)
if a[:2]==['image','inspect']:
    if not state.exists():sys.exit(1)
    print(state.read_text());sys.exit(0)
if a[0]=='build':state.write_text(a[a.index('--label')+1].split('=',1)[1])
elif a[0] not in ('info','run'):sys.exit('Unexpected mutation')
''')
        docker.chmod(0o755)
        gpu = self.bin / 'nvidia-smi'
        gpu.write_text('#!/bin/sh\n[ "${DEPLOY_GPU_BAD:-0}" != 1 ] || exit 3\necho "Test GPU, test driver"\n')
        gpu.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def run_deploy(self, args=(), **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith('PP_')}
        env.update(PATH=str(self.bin) + ':' + env['PATH'], PP_BUILD_ONLY='1',
                   DEPLOY_CALLS=str(self.capture), DEPLOY_STATE=str(self.state), **extra)
        result = subprocess.run(['bash', str(self.root / 'tools/deploy.sh'), *args], env=env,
                                capture_output=True, text=True, timeout=10)
        calls = [json.loads(line) for line in self.capture.read_text().splitlines()] if self.capture.exists() else []
        self.capture.unlink(missing_ok=True)
        return result, calls

    def test_reuses_image_for_unchanged_code_and_documentation_edits(self):
        result, calls = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        build = next(c for c in calls if c[0] == 'build')
        self.assertIn('--pull=false', build)
        self.assertIn('SOURCE_MODE=local', build)
        self.assertFalse(any(c[0] == 'run' for c in calls))
        for edit in (False, True):
            if edit:
                (self.root / 'README.md').write_text('Documentation changed')
            result, calls = self.run_deploy()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Runtime build inputs unchanged', result.stdout)
            self.assertFalse(any(c[0] == 'build' for c in calls))
        with (self.root / 'src/pp_inference_node.cpp').open('a') as stream:
            stream.write('\n// Runtime input changed\n')
        result, calls = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum(c[0] == 'build' for c in calls), 1)

    def test_refresh_and_remote_source_are_explicit(self):
        self.run_deploy()
        result, calls = self.run_deploy(PP_PULL_BASE='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--pull=true', next(c for c in calls if c[0] == 'build'))
        result, calls = self.run_deploy(PP_GIT_REF='fixed-ref')
        self.assertEqual(result.returncode, 0, result.stderr)
        build = next(c for c in calls if c[0] == 'build')
        self.assertIn('SOURCE_MODE=remote', build)
        self.assertIn('GIT_REF=fixed-ref', build)

    def test_gpu_failure_prevents_any_docker_build_or_install(self):
        result, calls = self.run_deploy(DEPLOY_GPU_BAD='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Host NVIDIA driver check failed', result.stderr)
        self.assertEqual(calls, [])

    def test_custom_build_options_do_not_poison_default_image_reuse(self):
        result, _ = self.run_deploy(args=('--build-arg', 'MODEL_SHA256=custom'))
        self.assertEqual(result.returncode, 0, result.stderr)
        result, calls = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum(c[0] == 'build' for c in calls), 1)
