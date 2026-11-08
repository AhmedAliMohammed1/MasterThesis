"""Geometric selection controls, independent of sensor feature values."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from ouster_point_policy import bounded_indices


class OusterPointPolicyTests(unittest.TestCase):
    def choose(self, points, **kwargs):
        return bounded_indices(points, [-10, -10, -2], [10, 10, 2], [1, 1], **kwargs)

    def test_first_encountered_pillars_not_coordinate_sort_and_stable_order(self):
        xyz = np.array([[8, 8, 1], [-8, -8, 1], [0, 5, 1],
                        [8.1, 8, 1], [-7.9, -8, 1]], dtype=np.float32)
        before = xyz.tobytes()
        indices, audit = self.choose(xyz, max_pillars=2)
        self.assertEqual(indices.tolist(), [0, 1, 3, 4])
        self.assertEqual(audit['occupied_pillars_before'], 3)
        self.assertEqual(audit['retained_pillars'], 2)
        self.assertEqual(audit['pillar_limit_removed_points'], 1)
        self.assertEqual(xyz.tobytes(), before)
        np.testing.assert_array_equal(xyz[indices], xyz[[0, 1, 3, 4]])

    def test_first_32_points_per_pillar_without_blocking_other_pillars(self):
        xyz = np.tile([1.1, 1.1, 1], (34, 1)).astype(np.float32)
        xyz = np.vstack((xyz, [-1, -1, 1]))
        indices, audit = self.choose(xyz)
        self.assertEqual(indices.tolist(), list(range(32)) + [34])
        self.assertEqual(audit['per_pillar_limit_removed_points'], 2)

    def test_finite_zero_and_exclusive_upper_inclusive_lower(self):
        xyz = np.array([[0, 0, 0], [np.nan, 1, 1], [1, np.inf, 1],
                        [-10, -10, -2], [10, 1, 1], [1, 1, 2],
                        [1, 1, np.nextafter(np.float32(2), np.float32(0))]], dtype=np.float32)
        indices, audit = self.choose(xyz)
        self.assertEqual(indices.tolist(), [3, 6])
        self.assertEqual(audit['nonfinite_points'], 2)
        self.assertEqual(audit['zero_xyz_points'], 1)
        self.assertEqual(audit['out_of_range_points'], 2)

    def test_float32_boundary_arithmetic_is_explicit(self):
        # Float32 subtraction rounds this just-below cell boundary to exactly 10.
        x = np.nextafter(np.float32(0), np.float32(-1))
        xyz = np.array([[x, 1, 1], [.1, 1, 1]], dtype=np.float32)
        indices, audit = self.choose(xyz, max_per_pillar=1)
        self.assertEqual(indices.tolist(), [0])
        self.assertEqual(audit['occupied_pillars_before'], 1)

    def test_empty_and_invalid_configuration(self):
        indices, audit = self.choose(np.empty((0, 3)))
        self.assertEqual(indices.dtype, np.dtype('int64'))
        self.assertEqual(audit['selected_points'], 0)
        for kwargs in ({'max_pillars': 0}, {'max_per_pillar': True}, {'max_pillars': 1.5}):
            with self.assertRaises(ValueError):
                self.choose([[1, 1, 1]], **kwargs)
        with self.assertRaises(ValueError):
            bounded_indices([[1, 1, 1]], [0, 0, 0], [1, 1, 1], [0, 1])


if __name__ == '__main__':
    unittest.main()
