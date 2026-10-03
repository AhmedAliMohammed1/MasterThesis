"""Known camera conversions and upstream-metric controls independent of the model."""
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import kitti_evaluation as evaluation
from kitti_geometry import Calibration
from test_kitti_validation import CALIB


class ConversionTests(unittest.TestCase):
    def prediction(self):
        return {'center_lidar':[10,0,0],'dimensions_lwh':[4,2,2],'yaw_lidar':-math.pi/2,'class_id':0,'score':.9}

    def test_known_prediction_in_camera_convention(self):
        box=evaluation.camera_prediction(self.prediction(),Calibration(CALIB),[100,80])
        self.assertEqual(box['type'],'Car')
        for actual,expected in zip(box['bottom_center'],[0,1,10]):self.assertAlmostEqual(actual,expected)
        self.assertAlmostEqual(box['rotation_y'],0)
        self.assertEqual(box['hwl'],[2,2,4])
        self.assertEqual(len(evaluation.prediction_line(box).split()),16)
        self.assertAlmostEqual(box['bbox'][0],50-200/9)
        self.assertAlmostEqual(box['bbox'][2],50+200/9)

    def test_outside_and_behind_camera_are_excluded(self):
        p=self.prediction();p['center_lidar']=[-10,0,0]
        self.assertIsNone(evaluation.camera_prediction(p,Calibration(CALIB),[100,80]))
        p['center_lidar']=[10,100,0]
        self.assertIsNone(evaluation.camera_prediction(p,Calibration(CALIB),[100,80]))

    def test_near_plane_crossing_is_clipped_to_image(self):
        p=self.prediction();p['center_lidar']=[.1,0,0]
        box=evaluation.camera_prediction(p,Calibration(CALIB),[100,80])
        self.assertIsNotNone(box)
        self.assertEqual(box['bbox'],[0,0,99,79])


class MetricControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Real cached publisher devkit is required only for these integration controls.
        cls.devkit=Path(__file__).resolve().parents[1]/'../datasets/kitti_object_diagnostic_v1/.cache/devkit_object.zip'
        if not cls.devkit.is_file():raise unittest.SkipTest('Prepare KITTI diagnostic data to run upstream metric controls')
        cls.workspace=tempfile.TemporaryDirectory(prefix='kitti-metric-controls-')
        cls.root=Path(cls.workspace.name)
        cls.binary,_=evaluation.build_evaluator(cls.devkit,cls.root/'build')

    @classmethod
    def tearDownClass(cls):cls.workspace.cleanup()

    def run_control(self,*,perfect=True,duplicate=False):
        # 41 independent labeled frames avoid sparse AP discretization ambiguity.
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            root=Path(directory);gt=root/'gt';det=root/'det';gt.mkdir();det.mkdir()
            ids=root/'ids.txt';ids.write_text('\n'.join(f'{i:06d}' for i in range(41)))
            for i in range(41):
                lines=[];detections=[]
                for j,name in enumerate(('Car','Pedestrian','Cyclist')):
                    line=f'{name} 0 0 0 10 10 100 100 2 2 4 {j*10} 1 20 0\n'
                    lines.append(line)
                    if perfect:
                        detections.append(line.rstrip()+' 0.9\n')
                        if duplicate:detections.append(line.rstrip()+' 0.8\n')
                (gt/f'{i:06d}.txt').write_text(''.join(lines))
                (det/f'{i:06d}.txt').write_text(''.join(detections))
            output=root/'metrics.json';evaluation.run_binary(self.binary,gt,det,ids,output)
            return json.loads(output.read_text())

    def test_exact_boxes_produce_perfect_3d_bev_and_ap(self):
        report=self.run_control()
        for cls in report['classes'].values():
            for metric in cls.values():
                for level in metric.values():
                    self.assertEqual((level['gt'],level['tp'],level['fp'],level['fn']),(41,41,0,0))
                    self.assertAlmostEqual(level['ap_r40'],1)
                    self.assertEqual((level['precision'],level['recall']),(1,1))

    def test_missing_predictions_count_all_false_negatives(self):
        report=self.run_control(perfect=False)
        for cls in report['classes'].values():
            for metric in cls.values():
                for level in metric.values():
                    self.assertEqual((level['tp'],level['fp'],level['fn']),(0,0,41))
                    self.assertEqual(level['ap_r40'],0)

    def test_duplicate_predictions_count_false_positives(self):
        report=self.run_control(duplicate=True)
        for cls in report['classes'].values():
            for metric in cls.values():
                level=metric['moderate']
                self.assertEqual((level['tp'],level['fp'],level['fn']),(41,41,0))
                self.assertEqual(level['precision'],.5)
                self.assertEqual(level['recall'],1)


if __name__=='__main__':unittest.main()
