"""Explicit point-capacity sensitivity control; not a production calibration.

Selection uses geometry only. Indices retain original scan order so callers can
apply the identical selection to every feature without modifying source files.
"""
import numpy as np


def bounded_indices(xyz, lo, hi, voxel_xy, max_pillars=10000, max_per_pillar=32):
    """Return stable indices and an audit for bounded, first-encountered pillars.

    Geometry comparisons and ``floor((xy - lo_xy) / voxel_xy)`` use float32,
    matching the model's input arithmetic. This deterministic CPU policy is a
    sensitivity control; it does not reproduce CUDA thread encounter order.
    All-zero returns are excluded, along with nonfinite and out-of-range XYZ.
    """
    points = np.asarray(xyz, dtype=np.float32)
    lower = np.asarray(lo, dtype=np.float32)
    upper = np.asarray(hi, dtype=np.float32)
    voxel = np.asarray(voxel_xy, dtype=np.float32)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError('xyz must have shape (N, 3)')
    if lower.shape != (3,) or upper.shape != (3,) or voxel.shape != (2,):
        raise ValueError('Expected three ROI bounds and two XY voxel sizes')
    if not (np.isfinite(lower).all() and np.isfinite(upper).all() and
            np.isfinite(voxel).all() and np.all(upper > lower) and np.all(voxel > 0)):
        raise ValueError('Bounds and positive voxel sizes must be finite')
    for value in (max_pillars, max_per_pillar):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value <= 0:
            raise ValueError('Capacity limits must be positive integers')
    finite = np.isfinite(points).all(axis=1)
    zero = finite & np.all(points == np.float32(0), axis=1)
    inside = finite & ~zero & np.all((points >= lower) & (points < upper), axis=1)
    eligible = np.flatnonzero(inside)
    # Both ufunc operations receive float32 arrays and therefore round as float32.
    cells = np.floor((points[eligible, :2] - lower[:2]) / voxel)
    if not np.isfinite(cells).all():
        raise ValueError('Voxel index arithmetic overflow')
    retained = {}
    encountered = set()
    selected = []
    pillar_limit_points = 0
    per_pillar_limit_points = 0
    for index, cell in zip(eligible, cells):
        key = (int(cell[0]), int(cell[1]))
        encountered.add(key)
        if key not in retained:
            if len(retained) == max_pillars:
                pillar_limit_points += 1
                continue
            retained[key] = 0
        if retained[key] == max_per_pillar:
            per_pillar_limit_points += 1
            continue
        retained[key] += 1
        selected.append(int(index))
    indices = np.asarray(selected, dtype=np.int64)
    audit = {
        'policy': 'first-encountered XY pillars, first points per retained pillar, stable scan order',
        'arithmetic': 'float32 floor((xy - lo_xy) / voxel_xy)',
        'input_points': len(points),
        'nonfinite_points': int((~finite).sum()),
        'zero_xyz_points': int(zero.sum()),
        'out_of_range_points': int((finite & ~zero & ~inside).sum()),
        'eligible_points': len(eligible),
        'occupied_pillars_before': len(encountered),
        'retained_pillars': len(retained),
        'pillar_limit_removed_points': pillar_limit_points,
        'per_pillar_limit_removed_points': per_pillar_limit_points,
        'selected_points': len(indices),
        'max_pillars': int(max_pillars),
        'max_per_pillar': int(max_per_pillar),
    }
    return indices, audit
