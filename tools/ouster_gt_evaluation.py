#!/usr/bin/env python3
"""Diagnostic LiDAR-box evaluation, not an official benchmark implementation."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import random
import statistics

ROI = (-50., -50., -1.4, 50., 50., 4.4)
CLASS_NAMES = {0: 'Vehicle', 1: 'Pedestrian', 2: 'Cyclist'}
IOU_THRESHOLDS = {0: .7, 1: .5, 2: .5}


def valid_box(row):
    if len(row) != 7 or not all(isinstance(x, (float, int)) and not isinstance(x, bool)
                                and math.isfinite(x) for x in row) or min(row[3:6]) <= 0:
        raise ValueError('Box requires finite x,y,z,length,width,height,yaw and positive dimensions')
    return tuple(row)


def inside(row):
    return all(ROI[i] <= row[i] < ROI[i + 3] for i in range(3))


def corners(row):
    x, y, _, length, width, _, yaw = valid_box(row)
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x + c * a - s * b, y + s * a + c * b)
            for a, b in ((-length / 2, -width / 2), (length / 2, -width / 2),
                         (length / 2, width / 2), (-length / 2, width / 2))]


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def intersection_area(a, b):
    """Clip convex, counterclockwise rectangles using Sutherland-Hodgman."""
    polygon = corners(a)
    clip = corners(b)
    for edge_index in range(4):
        origin, end = clip[edge_index], clip[(edge_index + 1) % 4]
        direction = (end[0] - origin[0], end[1] - origin[1])
        def side(point):
            return cross(direction, (point[0] - origin[0], point[1] - origin[1]))
        previous = polygon[-1] if polygon else None
        output = []
        for current in polygon:
            ds, de = side(previous), side(current)
            if (ds >= 0) != (de >= 0):
                t = ds / (ds - de)
                output.append((previous[0] + t * (current[0] - previous[0]),
                               previous[1] + t * (current[1] - previous[1])))
            if de >= 0:
                output.append(current)
            previous = current
        polygon = output
    if len(polygon) < 3:
        return 0.0
    # Translate before the shoelace sum to limit cancellation far from origin.
    origin = polygon[0]
    shifted = [(p[0] - origin[0], p[1] - origin[1]) for p in polygon]
    area = abs(sum(cross(shifted[i], shifted[(i + 1) % len(shifted)])
                   for i in range(len(shifted)))) / 2
    return min(area, a[3] * a[4], b[3] * b[4])


def box_iou(a, b):
    a, b = valid_box(a), valid_box(b)
    area = intersection_area(a, b)
    bev = area / (a[3] * a[4] + b[3] * b[4] - area)
    overlap_height = max(0., min(a[2] + a[5] / 2, b[2] + b[5] / 2)
                         - max(a[2] - a[5] / 2, b[2] - b[5] / 2))
    volume = area * overlap_height
    iou3d = volume / (a[3] * a[4] * a[5] + b[3] * b[4] * b[5] - volume)
    return {'bev': max(0., min(1., bev)), '3d': max(0., min(1., iou3d))}


def precision_envelope_ap(precision, recall, gt):
    """All-points interpolated AP, not KITTI AP_R40 or COCO AP."""
    if not gt:
        return None
    p = [0.] + list(precision) + [0.]
    r = [0.] + list(recall) + [1.]
    for i in range(len(p) - 2, -1, -1):
        p[i] = max(p[i], p[i + 1])
    return sum((r[i + 1] - r[i]) * p[i + 1] for i in range(len(r) - 1)
               if r[i + 1] != r[i])


def paired_accuracy(report, seed=20261108, samples=10000):
    """Paired frame bootstrap of count-derived precision/recall differences.

    Average counts across repeats within each frame before resampling frames.
    This preserves false positives on frames with no ground truth and avoids
    treating inference repetitions as additional independently annotated scenes.
    """
    if samples < 1:
        raise ValueError('Bootstrap samples must be positive')
    runs = report['runs']
    results = []
    for split in sorted({r['split'] for r in runs}):
        variants = sorted({r['variant'] for r in runs if r['split'] == split})
        for i, left in enumerate(variants):
            for right in variants[i + 1:]:
                a = [r for r in runs if r['split'] == split and r['variant'] == left]
                b = [r for r in runs if r['split'] == split and r['variant'] == right]
                repeat_ids = sorted({r['repeat'] for r in a} & {r['repeat'] for r in b})
                ar = {r['repeat']: r for r in a}
                br = {r['repeat']: r for r in b}
                classes = sorted(set(a[0]['classes']) & set(b[0]['classes']))
                for cls in classes:
                    for metric in ('bev', '3d'):
                        frame_ids = set()
                        for rep in repeat_ids:
                            x = ar[rep]['classes'][cls][metric]['per_frame']
                            y = br[rep]['classes'][cls][metric]['per_frame']
                            if set(x) != set(y):
                                raise ValueError('Paired accuracy requires identical frame sets')
                            if frame_ids and frame_ids != set(x):
                                raise ValueError('Repeat frame sets changed')
                            frame_ids = set(x)
                        averaged = []
                        for frame in sorted(frame_ids):
                            counts = {}
                            for name, lookup in ((left, ar), (right, br)):
                                counts[name] = {field: statistics.mean(
                                    lookup[rep]['classes'][cls][metric]['per_frame'][frame][field]
                                    for rep in repeat_ids) for field in ('tp', 'fp', 'fn')}
                            averaged.append({'frame_id': frame, 'counts': counts})
                        def aggregate(selected, variant):
                            sums = {field: sum(f['counts'][variant][field] for f in selected)
                                    for field in ('tp', 'fp', 'fn')}
                            return {'precision': sums['tp'] / (sums['tp'] + sums['fp'])
                                    if sums['tp'] + sums['fp'] else 0.,
                                    'recall': sums['tp'] / (sums['tp'] + sums['fn'])
                                    if sums['tp'] + sums['fn'] else None}
                        rng = random.Random(seed)
                        differences = {'precision': [], 'recall': []}
                        if averaged:
                            for _ in range(samples):
                                selected = rng.choices(averaged, k=len(averaged))
                                first, second = aggregate(selected, left), aggregate(selected, right)
                                for field in differences:
                                    if first[field] is not None and second[field] is not None:
                                        differences[field].append(second[field] - first[field])
                        first, second = aggregate(averaged, left), aggregate(averaged, right)
                        estimates = {}
                        for field, values in differences.items():
                            ordered = sorted(values)
                            delta = (second[field] - first[field] if averaged and first[field] is not None
                                     and second[field] is not None else None)
                            estimates[field] = {'left': first[field] if averaged else None,
                                'right': second[field] if averaged else None, 'difference_right_minus_left': delta,
                                'ci95': [ordered[int(.025 * (len(ordered) - 1))],
                                         ordered[int(.975 * (len(ordered) - 1))]] if ordered else None,
                                'valid_bootstrap_samples': len(ordered)}
                        results.append({'split': split, 'left_variant': left, 'right_variant': right,
                            'class': cls, 'metric': metric, 'paired_repeats': repeat_ids,
                            'frames': len(averaged), 'per_frame_mean_counts': averaged,
                            'estimates': estimates, 'seed': seed, 'bootstrap_samples': samples,
                            'method': 'Average paired-repeat counts per frame; bootstrap paired frames; ratios from aggregate counts',
                            'limitation': 'Frames are resampled as independent; scans in this single collection can be correlated. '
                                          'Intervals do not establish independent-drive or collection generalization. '
                                          'No-ground-truth bootstrap samples have undefined recall and are omitted only from recall intervals.'})
    return results


def class_metrics(frames, class_id, metric):
    truth = {f['frame_id']: [b['row'] for b in f['ground_truth'] if b['class_id'] == class_id
                            and inside(b['row'])] for f in frames}
    matched = {frame: set() for frame in truth}
    predictions = []
    for frame in frames:
        if frame['status'] == 'ok':
            predictions.extend((row[8], frame['frame_id'], i, row[:7])
                               for i, row in enumerate(frame['rows'])
                               if row[7] == class_id and inside(row))
    predictions.sort(key=lambda item: (-item[0], item[1], item[2]))
    gt = sum(len(boxes) for boxes in truth.values())
    tp = fp = 0
    precisions, recalls, observations = [], [], []
    per_frame = {f['frame_id']: {'tp': 0, 'fp': 0, 'fn': len(truth[f['frame_id']])} for f in frames}
    for score, frame, index, row in predictions:
        options = [(box_iou(row, target)[metric], j) for j, target in enumerate(truth[frame])
                   if j not in matched[frame]]
        overlap, j = max(options, default=(0., -1))
        accepted = j >= 0 and overlap >= IOU_THRESHOLDS[class_id]
        if accepted:
            tp += 1
            matched[frame].add(j)
            per_frame[frame]['tp'] += 1
            per_frame[frame]['fn'] -= 1
        else:
            fp += 1
            per_frame[frame]['fp'] += 1
        precisions.append(tp / (tp + fp))
        recalls.append(tp / gt if gt else 0.)
        observations.append({'frame_id': frame, 'prediction_index': index, 'score': score,
                             'tp': accepted, 'best_unmatched_iou': overlap})
    return {'gt': gt, 'tp': tp, 'fp': fp, 'fn': gt - tp,
            'precision': tp / (tp + fp) if tp + fp else 0.,
            'recall': tp / gt if gt else None,
            'ap_continuous': precision_envelope_ap(precisions, recalls, gt),
            'iou_threshold': IOU_THRESHOLDS[class_id], 'per_frame': per_frame,
            'ranked_predictions': observations}


def evaluate(records, threshold=.4):
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('Confidence threshold must be finite in [0,1]')
    groups, truth_identity, identities = defaultdict(list), {}, set()
    supported = {0, 1}
    for item in records:
        if isinstance(item['repeat'], bool) or not isinstance(item['repeat'], int) or item['repeat'] < 0:
            raise ValueError('Repeat must be a nonnegative integer')
        if not isinstance(item['status'], str) or not item['status']:
            raise ValueError('Every observation needs explicit status')
        key = (str(item['split']), str(item['variant']), item['repeat'])
        frame_id = str(item['frame_id'])
        identity = (*key, frame_id)
        if identity in identities:
            raise ValueError('Duplicate prediction observation')
        identities.add(identity)
        truth = []
        for target in item['ground_truth']:
            cls = target['class_id']
            if isinstance(cls, bool) or not isinstance(cls, int) or cls not in CLASS_NAMES:
                raise ValueError('Ground-truth class must be mapped Vehicle/Pedestrian/Cyclist')
            supported.add(cls)
            truth.append({'class_id': cls, 'row': valid_box(target['row'])})
        tid = (key[0], frame_id)
        if tid in truth_identity and truth_identity[tid] != truth:
            raise ValueError('Ground truth changed across variants or repeats')
        truth_identity[tid] = truth
        rows = []
        if item['status'] == 'ok':
            for row in item['rows']:
                if len(row) != 9:
                    raise ValueError('Prediction requires nine values')
                valid_box(row[:7])
                cls, score = row[7:]
                if (isinstance(cls, bool) or not isinstance(cls, (float, int)) or not math.isfinite(cls)
                        or cls != int(cls) or cls < 0 or not isinstance(score, (float, int))
                        or isinstance(score, bool) or not math.isfinite(score) or not 0 <= score <= 1):
                    raise ValueError('Invalid prediction class or score')
                if score >= threshold:
                    rows.append(tuple(row))
        groups[key].append(dict(frame_id=frame_id, status=item['status'], rows=rows, ground_truth=truth))
    expected_by_split = defaultdict(set)
    for split, frame in truth_identity:
        expected_by_split[split].add(frame)
    for (split, _, _), frames in groups.items():
        if {f['frame_id'] for f in frames} != expected_by_split[split]:
            raise ValueError('Incomplete frame set; represent missing predictions with an explicit failure status')
    results = []
    for (split, variant, repeat), frames in sorted(groups.items()):
        excluded_gt = sum(not inside(b['row']) for f in frames for b in f['ground_truth'])
        excluded_predictions = sum(not inside(row) for f in frames for row in f['rows'])
        unsupported = sum(inside(row) and row[7] not in supported for f in frames for row in f['rows'])
        result = {'split': split, 'variant': variant, 'repeat': repeat, 'frames': len(frames),
                  'failed_frames': sum(f['status'] != 'ok' for f in frames),
                  'excluded_gt_center_outside_roi': excluded_gt,
                  'excluded_predictions_center_outside_roi': excluded_predictions,
                  'excluded_predictions_unsupported_class': unsupported,
                  'classes': {}}
        for cls in sorted(supported):
            result['classes'][CLASS_NAMES[cls]] = {metric: class_metrics(frames, cls, metric)
                                                  for metric in ('bev', '3d')}
        results.append(result)
    aggregate = []
    by_variant = defaultdict(list)
    for result in results:
        by_variant[(result['split'], result['variant'])].append(result)
    for (split, variant), runs in sorted(by_variant.items()):
        entry = {'split': split, 'variant': variant, 'repeats': len(runs), 'classes': {}}
        for cls in sorted(supported):
            name = CLASS_NAMES[cls]
            entry['classes'][name] = {}
            for metric in ('bev', '3d'):
                values = [r['classes'][name][metric] for r in runs]
                entry['classes'][name][metric] = {}
                for field in ('tp', 'fp', 'fn', 'precision', 'recall', 'ap_continuous'):
                    selected = [v[field] for v in values if v[field] is not None]
                    entry['classes'][name][metric][field] = ({'mean': statistics.mean(selected),
                        'min': min(selected), 'max': max(selected)} if selected else None)
        aggregate.append(entry)
    report = {'policy': {'confidence_threshold': threshold, 'iou_thresholds': IOU_THRESHOLDS,
                      'roi': ROI, 'roi_rule': 'Box center min-inclusive max-exclusive, same for GT and predictions',
                      'roi_reason': 'Publisher annotation coverage is 100m x 100m; vertical limits remain the model range',
                      'box_convention': 'LiDAR geometric center, length/width/height, yaw radians; no z shift',
                      'matching': 'Same class, confidence-ranked greedy highest-IoU unmatched GT per frame',
                      'ap': 'Continuous precision-envelope area, diagnostic; NOT official KITTI or COCO AP',
                      'ap_scope': 'Only predictions at or above the stated confidence threshold are available',
                      'unsupported_classes': 'Cyclist evaluated only if supplied ground truth contains Cyclist',
                      'failure_policy': 'Failed frames retain all in-ROI GT as false negatives',
                      'repeat_aggregation': 'Mean/min/max of run metrics; repetitions are not pooled as independent scenes'},
            'runs': results, 'across_repeats': aggregate}
    report['paired_comparisons'] = paired_accuracy(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--threshold', type=float, default=.4)
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    report = evaluate(data['observations'] if isinstance(data, dict) else data, args.threshold)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
