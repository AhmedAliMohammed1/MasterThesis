#!/usr/bin/env python3
"""Describe post-NMS detection repeatability; no ground-truth accuracy claim."""
import argparse
from collections import defaultdict, deque
import json
import math
from pathlib import Path
import random
import statistics

LIMITATION = ('Bootstrap resamples paired frames as independent units. Adjacent scans '
              'and repeated recordings may be correlated; this interval does not establish '
              'recording-level generalization or ground-truth accuracy.')


def checked_rows(rows):
    result = []
    for row in rows:
        if len(row) != 9 or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                    and math.isfinite(v) for v in row):
            raise ValueError('Each detection must contain nine finite numbers')
        if min(row[3:6]) <= 0 or row[7] < 0 or row[7] != int(row[7]) or not 0 <= row[8] <= 1:
            raise ValueError('Invalid dimensions, class or score')
        result.append(tuple(row))
    return result


def match_rows(left, right):
    """Maximum-cardinality matching; duplicates cannot reuse a counterpart."""
    left, right = checked_rows(left), checked_rows(right)
    def compatible(a, b):
        return (a[7] == b[7] and math.dist(a[:3], b[:3]) <= .25
                and max(abs(a[i] - b[i]) for i in (3, 4, 5)) <= .25
                and abs((a[6] - b[6] + math.pi) % (2 * math.pi) - math.pi) <= math.radians(5)
                and abs(a[8] - b[8]) <= .05 + 1e-12)
    edges = [[j for j, b in enumerate(right) if compatible(a, b)] for a in left]
    owners, mates = {}, {}
    for start in range(len(left)):
        queue, seen_left, seen_right, parents = deque([start]), {start}, set(), {}
        free = None
        while queue and free is None:
            i = queue.popleft()
            for j in edges[i]:
                if j in seen_right:
                    continue
                seen_right.add(j)
                parents[j] = i
                if j not in owners:
                    free = j
                    break
                k = owners[j]
                if k not in seen_left:
                    seen_left.add(k)
                    queue.append(k)
        if free is not None:
            j = free
            while True:
                i = parents[j]
                old = mates.get(i)
                owners[j], mates[i] = i, j
                if old is None:
                    break
                j = old
    both_empty = not left and not right
    return {'left_count': len(left), 'right_count': len(right), 'matched': len(mates),
            'both_empty': both_empty, 'one_empty': bool(left) != bool(right),
            'match_fraction': len(mates) / max(len(left), len(right)) if not both_empty else None}


def paired_bootstrap(differences, seed=20261108, samples=10000):
    if not differences:
        return {'frames': 0, 'mean_difference': None, 'ci95': None, 'seed': seed,
                'samples': samples, 'limitation': LIMITATION}
    rng = random.Random(seed)
    draws = sorted(statistics.mean(rng.choices(differences, k=len(differences))) for _ in range(samples))
    return {'frames': len(differences), 'mean_difference': statistics.mean(differences),
            'ci95': [draws[int(.025 * (samples - 1))], draws[int(.975 * (samples - 1))]],
            'seed': seed, 'samples': samples, 'limitation': LIMITATION}


def summarize(data, threshold=.4):
    """Compare repeat 0 against later repeats, then pair variants within frames.

    Successful observation status must be ``ok``. Other nonempty status strings
    represent failures and never become empty detections. Missing repeat 0 is
    reported instead of silently choosing another reference.
    """
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('Threshold must be finite and in [0,1]')
    groups = defaultdict(dict)
    for item in data['observations']:
        condition, frame, variant = (str(item[k]) for k in ('condition', 'frame_id', 'variant'))
        repeat = item['repeat']
        if isinstance(repeat, bool) or not isinstance(repeat, int) or repeat < 0:
            raise ValueError('Repeat must be a nonnegative integer')
        if not isinstance(item['status'], str) or not item['status']:
            raise ValueError('Observation requires an explicit status')
        key = (condition, frame, variant)
        if repeat in groups[key]:
            raise ValueError('Duplicate observation identity')
        record = dict(item)
        if item['status'] == 'ok':
            record['rows'] = [r for r in checked_rows(item['rows']) if r[8] >= threshold]
        groups[key][repeat] = record
    pairs, frame_scores, summaries = [], {}, {}
    variant_names = sorted({key[2] for key in groups})
    for variant in variant_names:
        selected = [(key, value) for key, value in sorted(groups.items()) if key[2] == variant]
        summary = {'observations': 0, 'failed_observations': 0, 'failure_statuses': {},
                   'missing_baseline_frames': 0, 'unavailable_pairs': 0, 'both_empty_pairs': 0,
                   'one_empty_pairs': 0, 'nonempty_pairs': 0}
        scores = []
        for (condition, frame, _), repeats in selected:
            summary['observations'] += len(repeats)
            for item in repeats.values():
                if item['status'] != 'ok':
                    summary['failed_observations'] += 1
                    status = item['status']
                    summary['failure_statuses'][status] = summary['failure_statuses'].get(status, 0) + 1
            baseline = repeats.get(0)
            if baseline is None:
                summary['missing_baseline_frames'] += 1
            per_frame = {}
            for repeat, item in sorted(repeats.items()):
                if repeat == 0:
                    continue
                pair = {'condition': condition, 'frame_id': frame, 'variant': variant, 'repeat': repeat}
                if baseline is None or baseline['status'] != 'ok' or item['status'] != 'ok':
                    pair.update(status='unavailable', match_fraction=None)
                    summary['unavailable_pairs'] += 1
                else:
                    pair.update(status='ok', **match_rows(baseline['rows'], item['rows']))
                    if pair['both_empty']:
                        summary['both_empty_pairs'] += 1
                    else:
                        summary['nonempty_pairs'] += 1
                        summary['one_empty_pairs'] += int(pair['one_empty'])
                        scores.append(pair['match_fraction'])
                        per_frame[repeat] = pair['match_fraction']
                pairs.append(pair)
            frame_scores[(condition, frame, variant)] = per_frame
        summary['median_nonempty_match_fraction'] = statistics.median(scores) if scores else None
        summaries[variant] = summary
    comparisons = []
    identities = sorted({(key[0], key[1]) for key in groups})
    for i, left in enumerate(variant_names):
        for right in variant_names[i + 1:]:
            differences = []
            for condition, frame in identities:
                a = frame_scores.get((condition, frame, left), {})
                b = frame_scores.get((condition, frame, right), {})
                common = sorted(a.keys() & b.keys())
                if common:
                    differences.append({'condition': condition, 'frame_id': frame,
                                        'paired_repeats': common,
                                        'difference_right_minus_left': statistics.mean(b[r] - a[r] for r in common)})
            comparisons.append({'left_variant': left, 'right_variant': right,
                                'difference_definition': 'right minus left, mean of common repeat-pair fractions per frame',
                                'frames_without_comparable_nonempty_pairs': len(identities) - len(differences),
                                'per_frame': differences,
                                'bootstrap': paired_bootstrap([d['difference_right_minus_left'] for d in differences])})
    return {'threshold': threshold, 'metric': 'post-NMS, post-confidence-gate repeatability',
            'matching': {'center_distance_m': .25, 'maximum_dimension_error_m': .25,
                         'wrapped_yaw_degrees': 5, 'score_error': .05, 'class': 'same',
                         'method': 'maximum-cardinality one-to-one'},
            'baseline_repeat': 0, 'variants': summaries, 'pairs': pairs, 'comparisons': comparisons,
            'limitation': 'Repeatability is not detection accuracy. Both-empty pairs are excluded; failures are unavailable. ' + LIMITATION}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--threshold', type=float, default=.4)
    args = parser.parse_args()
    report = summarize(json.loads(args.input.read_text()), args.threshold)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pending = args.output.with_suffix(args.output.suffix + '.pending')
    pending.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    pending.replace(args.output)


if __name__ == '__main__':
    main()
