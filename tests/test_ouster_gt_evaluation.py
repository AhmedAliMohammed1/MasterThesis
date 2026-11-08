"""Analytic rotated geometry and benchmark failure/matching controls."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from ouster_gt_evaluation import box_iou, evaluate, precision_envelope_ap, paired_accuracy


def box(x=0, y=0, z=0, length=2, width=2, height=2, yaw=0):
    return [x, y, z, length, width, height, yaw]


def gt(row=None, cls=0):
    return {'class_id': cls, 'row': row if row is not None else box()}


def pred(row=None, score=.8, cls=0):
    return (row if row is not None else box()) + [cls, score]


def record(rows=None, truth=None, status='ok', frame='a', variant='signal', repeat=0):
    return dict(frame_id=frame, split='test', variant=variant, repeat=repeat,
                status=status, rows=rows if rows is not None else [pred()],
                ground_truth=truth if truth is not None else [gt()])


def metrics(records, metric='3d', cls='Vehicle', threshold=.4):
    return evaluate(records, threshold)['runs'][0]['classes'][cls][metric]


class OusterGroundTruthTests(unittest.TestCase):
    def test_identical_nested_touching_disjoint(self):
        self.assertEqual(box_iou(box(), box()), {'bev': 1., '3d': 1.})
        self.assertAlmostEqual(box_iou(box(length=4, width=4, height=4), box())['bev'], .25)
        self.assertAlmostEqual(box_iou(box(length=4, width=4, height=4), box())['3d'], .125)
        for other in (box(x=2), box(y=2), box(x=10)):
            self.assertEqual(box_iou(box(), other), {'bev': 0., '3d': 0.})

    def test_rotation_symmetry_periodicity_and_axis_swap(self):
        a = box(x=1.7, y=-.2, yaw=.37, length=3)
        b = box(x=1, y=.7, yaw=-.6, width=3)
        forward, backward = box_iou(a, b), box_iou(b, a)
        for metric in ('bev', '3d'):
            self.assertAlmostEqual(forward[metric], backward[metric], places=12)
        same = a.copy(); same[6] += math.pi
        self.assertAlmostEqual(box_iou(a, same)['bev'], 1)
        swapped = a.copy(); swapped[3], swapped[4] = a[4], a[3]; swapped[6] += math.pi / 2
        self.assertAlmostEqual(box_iou(a, swapped)['bev'], 1)
        # Analytic equal squares at 45 degrees: intersection 8(sqrt(2)-1).
        expected_area = 8 * (math.sqrt(2) - 1)
        self.assertAlmostEqual(box_iou(box(), box(yaw=math.pi / 4))['bev'], expected_area / (8 - expected_area))

    def test_vertical_center_overlap_not_bottom_center(self):
        overlap = box_iou(box(), box(z=1))
        self.assertEqual(overlap['bev'], 1)
        self.assertAlmostEqual(overlap['3d'], 1 / 3)
        self.assertEqual(box_iou(box(), box(z=2))['3d'], 0)

    def test_exact_predictions_missing_and_duplicates(self):
        perfect = metrics([record()])
        self.assertEqual((perfect['tp'], perfect['fp'], perfect['fn']), (1, 0, 0))
        self.assertEqual(perfect['ap_continuous'], 1)
        empty = metrics([record(rows=[])])
        self.assertEqual((empty['tp'], empty['fp'], empty['fn']), (0, 0, 1))
        self.assertEqual(empty['ap_continuous'], 0)
        duplicate = metrics([record(rows=[pred(score=.9), pred(score=.8)])])
        self.assertEqual((duplicate['tp'], duplicate['fp'], duplicate['fn']), (1, 1, 0))
        self.assertEqual(duplicate['precision'], .5)

    def test_score_ranking_controls_ap_and_threshold_truncation(self):
        false_first = metrics([record(rows=[pred(box(x=10), .9), pred(score=.8)])])
        true_first = metrics([record(rows=[pred(box(x=10), .8), pred(score=.9)])])
        self.assertEqual(false_first['ap_continuous'], .5)
        self.assertEqual(true_first['ap_continuous'], 1)
        removed = metrics([record(rows=[pred(score=.4)])], threshold=.41)
        kept = metrics([record(rows=[pred(score=.4)])], threshold=.4)
        self.assertEqual(removed['fn'], 1)
        self.assertEqual(kept['tp'], 1)
        self.assertAlmostEqual(precision_envelope_ap([1, .5, 2/3], [.5, .5, 1], 2), 5/6)

    def test_class_aware_matching_and_no_unlabeled_cyclist_ranking(self):
        report = evaluate([record(rows=[pred(cls=1), pred(cls=2)])])
        run = report['runs'][0]
        self.assertEqual(run['classes']['Vehicle']['3d']['fn'], 1)
        self.assertEqual(run['classes']['Pedestrian']['3d']['fp'], 1)
        self.assertIsNone(run['classes']['Pedestrian']['3d']['ap_continuous'])
        self.assertNotIn('Cyclist', run['classes'])
        self.assertEqual(run['excluded_predictions_unsupported_class'], 1)
        supported = evaluate([record(rows=[pred(cls=2)], truth=[gt(cls=2)])])
        self.assertEqual(supported['runs'][0]['classes']['Cyclist']['3d']['tp'], 1)

    def test_failure_retains_gt_as_misses_and_is_not_successful_empty(self):
        # Bogus cached detections in a failed frame must never become true positives.
        report = evaluate([record(status='timeout')])
        run = report['runs'][0]
        self.assertEqual(run['failed_frames'], 1)
        result = run['classes']['Vehicle']['3d']
        self.assertEqual((result['tp'], result['fp'], result['fn']), (0, 0, 1))

    def test_roi_center_exclusions_and_min_inclusive_max_exclusive(self):
        report = evaluate([record(rows=[pred(box(x=-50)), pred(box(x=50))],
                                  truth=[gt(box(x=-50)), gt(box(x=50))])])
        run = report['runs'][0]
        self.assertEqual(run['excluded_gt_center_outside_roi'], 1)
        self.assertEqual(run['excluded_predictions_center_outside_roi'], 1)
        self.assertEqual(run['classes']['Vehicle']['3d']['tp'], 1)

    def test_repeat_summary_does_not_pool_scenes(self):
        report = evaluate([record(repeat=0), record(rows=[], repeat=1)])
        self.assertEqual(len(report['runs']), 2)
        total = report['across_repeats'][0]['classes']['Vehicle']['3d']
        self.assertEqual(total['tp'], {'mean': .5, 'min': 0, 'max': 1})
        self.assertEqual(total['recall']['mean'], .5)

    def test_paired_accuracy_clear_winner_and_identical(self):
        records = []
        for frame in ('a', 'b'):
            for repeat in range(2):
                records.extend([record(rows=[], frame=frame, variant='signal', repeat=repeat),
                                record(frame=frame, variant='reflectivity', repeat=repeat)])
        report = evaluate(records)
        comparison = next(c for c in report['paired_comparisons']
                          if c['class'] == 'Vehicle' and c['metric'] == '3d')
        self.assertEqual(comparison['frames'], 2)  # Not four independent repeat scenes.
        self.assertEqual(comparison['estimates']['recall']['difference_right_minus_left'], -1)
        self.assertEqual(comparison['estimates']['recall']['ci95'], [-1, -1])
        identical = evaluate([record(variant='signal'), record(variant='reflectivity')])
        c = next(c for c in identical['paired_comparisons'] if c['class'] == 'Vehicle' and c['metric'] == '3d')
        self.assertEqual(c['estimates']['precision']['ci95'], [0, 0])

    def test_paired_ratios_use_aggregate_counts_and_retain_negative_scene_fp(self):
        records = [record(frame='positive', variant='signal'),
                   record(frame='positive', variant='reflectivity'),
                   record(frame='negative', variant='signal', truth=[], rows=[pred()]),
                   record(frame='negative', variant='reflectivity', truth=[], rows=[])]
        report = evaluate(records)
        c = next(c for c in report['paired_comparisons'] if c['class'] == 'Vehicle' and c['metric'] == '3d')
        self.assertEqual(c['estimates']['precision']['left'], 1)
        self.assertEqual(c['estimates']['precision']['right'], .5)
        self.assertEqual(c['estimates']['precision']['difference_right_minus_left'], -.5)
        self.assertLess(c['estimates']['recall']['valid_bootstrap_samples'], c['bootstrap_samples'])
        self.assertIn('single collection', c['limitation'])

    def test_incomplete_sets_duplicates_changed_truth_and_bad_boxes_rejected(self):
        cases = [[record(), record()],
                 [record(), record(variant='reflectivity', truth=[gt(box(x=1))])],
                 [record(), record(frame='b'), record(variant='reflectivity')],
                 [record(rows=[pred(box(length=0))])],
                 [record(rows=[pred(score=float('nan'))])]]
        for records in cases:
            with self.assertRaises(ValueError):
                evaluate(records)


if __name__ == '__main__':
    unittest.main()
