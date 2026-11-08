"""Controls against falsely identifying empty/failed output as stable detection."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from ouster_ab_metrics import match_rows, summarize, paired_bootstrap


def box(x=0, score=.8, yaw=0, cls=0):
    return [x, 0, 0, 4, 2, 1.5, yaw, cls, score]


def observation(variant, repeat, rows, status='ok', frame='a', condition='dry'):
    return dict(variant=variant, repeat=repeat, rows=rows, status=status,
                frame_id=frame, condition=condition)


class OusterABMetricsTests(unittest.TestCase):
    def test_augmenting_path_avoids_greedy_undercount_and_duplicate_reuse(self):
        # First left can use either right; second can use only right zero.
        self.assertEqual(match_rows([box(.1), box(-.1)], [box(0), box(.3)])['matched'], 2)
        self.assertEqual(match_rows([box(), box()], [box()])['match_fraction'], .5)

    def test_geometric_class_score_and_wrapped_yaw_limits(self):
        a = box(yaw=math.pi - .01)
        self.assertEqual(match_rows([a], [box(yaw=-math.pi + .01)])['matched'], 1)
        for b in (box(.251, yaw=a[6]), box(score=.86, yaw=a[6]),
                  box(cls=1, yaw=a[6]), box(yaw=a[6] + math.radians(5.1))):
            self.assertEqual(match_rows([a], [b])['matched'], 0)
        b = a.copy(); b[3] += .251
        self.assertEqual(match_rows([a], [b])['matched'], 0)
        b = box(.2); b[1] = .2  # Euclidean distance, not per-axis tolerance.
        self.assertEqual(match_rows([box()], [b])['matched'], 0)

    def test_empty_pairs_are_separate_and_one_empty_is_zero(self):
        data = {'observations': [observation('signal', 0, []), observation('signal', 1, []),
                                 observation('signal', 2, [box()])]}
        s = summarize(data)['variants']['signal']
        self.assertEqual(s['both_empty_pairs'], 1)
        self.assertEqual(s['one_empty_pairs'], 1)
        self.assertEqual(s['median_nonempty_match_fraction'], 0)
        self.assertIsNone(match_rows([], [])['match_fraction'])

    def test_failed_baseline_and_repeat_never_become_empties(self):
        data = {'observations': [observation('signal', 0, [], 'inference_error'),
                                 observation('signal', 1, []),
                                 observation('signal', 2, [], 'timeout')]}
        s = summarize(data)['variants']['signal']
        self.assertEqual(s['failed_observations'], 2)
        self.assertEqual(s['unavailable_pairs'], 2)
        self.assertEqual(s['both_empty_pairs'], 0)
        self.assertIsNone(s['median_nonempty_match_fraction'])

    def test_threshold_is_inclusive_and_precedes_matching(self):
        data = {'observations': [observation('signal', 0, [box(score=.4), box(10, .39)]),
                                 observation('signal', 1, [box(score=.4)])]}
        report = summarize(data)
        self.assertEqual(report['pairs'][0]['left_count'], 1)
        self.assertEqual(report['pairs'][0]['match_fraction'], 1)
        self.assertEqual(len(data['observations'][0]['rows']), 2)

    def test_paired_frames_use_common_repeats_and_keep_conditions_distinct(self):
        rows = []
        for condition in ('dry', 'rain'):
            rows.extend([observation('signal', 0, [box()], condition=condition),
                         observation('signal', 1, [box(2)], condition=condition),
                         observation('signal', 2, [box()], condition=condition),
                         observation('reflectivity', 0, [box()], condition=condition),
                         observation('reflectivity', 1, [box()], condition=condition),
                         observation('reflectivity', 2, [], 'timeout', condition=condition)])
        report = summarize({'observations': rows})
        comparison = report['comparisons'][0]
        # Names sort reflectivity then signal: negative means reflectivity better.
        self.assertEqual(comparison['left_variant'], 'reflectivity')
        self.assertEqual(comparison['bootstrap']['frames'], 2)
        self.assertEqual(comparison['bootstrap']['mean_difference'], -1)
        self.assertEqual(comparison['bootstrap']['ci95'], [-1, -1])
        self.assertEqual(comparison['per_frame'][0]['paired_repeats'], [1])
        self.assertIn('independent', comparison['bootstrap']['limitation'])

    def test_missing_baseline_and_duplicate_observations(self):
        item = observation('signal', 1, [box()])
        report = summarize({'observations': [item]})
        self.assertEqual(report['variants']['signal']['missing_baseline_frames'], 1)
        self.assertEqual(report['pairs'][0]['status'], 'unavailable')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            summarize({'observations': [item, item]})

    def test_invalid_rows_fail_even_when_below_threshold(self):
        for row in ([0] * 9, box(score=float('nan')), box(cls=.5), box(score=1.1)):
            with self.assertRaises(ValueError):
                summarize({'observations': [observation('signal', 0, [row])]})
        with self.assertRaises(ValueError):
            summarize({'observations': []}, threshold=float('nan'))

    def test_bootstrap_reproducible_and_no_pairs_is_unavailable(self):
        self.assertEqual(paired_bootstrap([.1, -.2, .3]), paired_bootstrap([.1, -.2, .3]))
        self.assertIsNone(paired_bootstrap([])['ci95'])


if __name__ == '__main__':
    unittest.main()
