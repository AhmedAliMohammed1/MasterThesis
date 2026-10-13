"""Calibration and safe player ownership controls for the frontal KITTI demo."""
from pathlib import Path
import os
import sys
import subprocess
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from prepare_kitti_front import camera_projection


class FrontDemoTests(unittest.TestCase):
    def test_preserves_official_projection_coefficients(self):
        values=[721.,0.,609.,45.,0.,721.,172.,0.,0.,0.,1.,0.]
        self.assertEqual(camera_projection('P_rect_02: '+' '.join(map(str,values))),values)
        with self.assertRaises(ValueError):camera_projection('P_rect_02: 1 2')
        with self.assertRaises(ValueError):camera_projection('P_rect_02: '+' '.join(['nan']*12))

    def test_stop_refuses_unowned_container(self):
        with tempfile.TemporaryDirectory() as directory:
            executable=Path(directory)/'docker'
            executable.write_text('#!/bin/sh\ncase "$1" in info) exit 0;; inspect) echo unowned;; stop) echo SHOULD_NOT_STOP;exit 3;;esac\n')
            executable.chmod(0o755)
            env=dict(os.environ,PATH=directory+':'+os.environ['PATH'])
            player=Path(__file__).resolve().parents[1]/'tools/rosbag_kitti_front.sh'
            result=subprocess.run(['bash',str(player),'stop'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,1)
            self.assertIn('unowned',result.stderr)
            self.assertNotIn('SHOULD_NOT_STOP',result.stdout)


if __name__=='__main__':unittest.main()
