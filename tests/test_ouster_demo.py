"""Input-contract and archive-boundary controls for the non-KITTI helper."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('ouster_demo', Path(__file__).resolve().parents[1] / 'tools/prepare_ouster_demo.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def cloud(width=2):
    return SimpleNamespace(fields=[SimpleNamespace(name=n, offset=i * 4, datatype=7, count=1)
                                   for i, n in enumerate(('x', 'y', 'z', 'intensity'))],
                           point_step=16, width=width, height=1, row_step=16 * width,
                           data=bytearray(16 * width), is_bigendian=False)


class OusterContractTests(unittest.TestCase):
    def test_native_xyzi_and_capacity_are_separate_checks(self):
        self.assertEqual(demo.inspect_cloud(cloud()), 2)
        # Audit must report excess capacity rather than silently changing the source.
        self.assertEqual(demo.inspect_cloud(cloud(demo.POINT_CAPACITY + 1)), demo.POINT_CAPACITY + 1)

    def test_integer_intensity_requires_explicit_adaptation(self):
        msg = cloud()
        msg.fields[-1].datatype = 4
        with self.assertRaisesRegex(ValueError, 'FLOAT32 intensity'):
            demo.inspect_cloud(msg)

    def test_bad_layout_and_overlapping_fields(self):
        msg = cloud()
        msg.data.pop()
        with self.assertRaisesRegex(ValueError, 'layout'):
            demo.inspect_cloud(msg)
        msg = cloud()
        msg.fields[-1].offset = 10
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            demo.inspect_cloud(msg)

    def test_archive_rejects_traversal_and_links(self):
        for name, kind in [('ouster/../escape', tarfile.REGTYPE), ('ouster/link', tarfile.SYMTYPE)]:
            payload = io.BytesIO()
            with tarfile.open(fileobj=payload, mode='w') as writer:
                member = tarfile.TarInfo(name)
                member.type = kind
                writer.addfile(member)
            payload.seek(0)
            with tarfile.open(fileobj=payload, mode='r') as reader:
                with self.assertRaisesRegex(ValueError, 'Unsafe'):
                    demo.safe_members(reader)

    def test_stop_refuses_unowned_container(self):
        with tempfile.TemporaryDirectory() as directory:
            docker = Path(directory) / 'docker'
            docker.write_text('#!/bin/sh\ncase "$1" in info) exit 0;; inspect) echo unowned;; stop) echo SHOULD_NOT_STOP; exit 3;; esac\n')
            docker.chmod(0o755)
            env = dict(os.environ, PATH=directory + ':' + os.environ['PATH'])
            launcher = Path(__file__).resolve().parents[1] / 'tools/rosbag_ouster.sh'
            result = subprocess.run(['bash', str(launcher), 'stop'], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('not owned by this helper', result.stderr)
            self.assertNotIn('SHOULD_NOT_STOP', result.stdout)


if __name__ == '__main__':
    unittest.main()
