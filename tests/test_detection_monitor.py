"""Protect frozen accuracy collection against live confidence filtering."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from kitti_inference import validate_publication_stats


class BaselineGateTests(unittest.TestCase):
    def values(self):
        return {'frame_status': 'ok', 'confidence_threshold': '0',
                'post_nms_count': '3', 'published_count': '3', 'filtered_count': '0'}

    def test_unfiltered_and_empty_frames_accepted(self):
        validate_publication_stats(self.values(), 3)
        values = self.values()
        values.update(post_nms_count='0', published_count='0')
        validate_publication_stats(values, 0)

    def test_live_gate_change_and_nonfinite_threshold_refused(self):
        for value in ['0.5', 'nan', 'inf', '-0.1']:
            values = self.values(); values['confidence_threshold'] = value
            with self.assertRaises(ValueError):
                validate_publication_stats(values, 3)

    def test_drops_missing_fields_and_count_mismatch_refused(self):
        for key, value in [('frame_status', 'inference_error'), ('published_count', '2'),
                           ('filtered_count', '1'), ('post_nms_count', '-1')]:
            values = self.values(); values[key] = value
            with self.assertRaises(ValueError):
                validate_publication_stats(values, 3)
        with self.assertRaises(ValueError):
            validate_publication_stats({}, 3)
        values = self.values(); values.update(post_nms_count='4', filtered_count='1')
        with self.assertRaises(ValueError):
            validate_publication_stats(values, 3)
