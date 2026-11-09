"""Visible-detection evaluation, independent of the educational tracking solver.

Not a full MOTChallenge evaluator. IDs persist across unmatched/invisible frames.
Coordinates are pixels; frame numbers are zero-based nonnegative integers.
"""
from collections import defaultdict

import numpy as np
from scipy.optimize import linear_sum_assignment

FIELDS = ("matched", "missed", "false_positive", "id_switches", "track_ids",
          "matched_detection_rmse_px")
# FIELDS followed by the two summary metrics returned by score_with_identity.
METRICS = FIELDS + ("mota", "idf1")


def _index(rows, ground_truth):
    indexed, seen = defaultdict(list), set()
    for row in rows:
        if len(row) != (5 if ground_truth else 4):
            raise ValueError("Expected frame,id,x,y[,visible].")
        frame, identity, x, y = row[:4]
        if not np.isfinite(frame) or frame < 0 or int(frame) != frame:
            raise ValueError("Frame must be a nonnegative integer.")
        if not np.isfinite(identity) or int(identity) != identity:
            raise ValueError("Identity must be an integer (negative singleton IDs are allowed).")
        if not np.isfinite([x, y]).all():
            raise ValueError("Coordinates must be finite.")
        key = (int(frame), int(identity))
        if key in seen:
            raise ValueError(f"Duplicate frame/identity: {key}")
        seen.add(key)
        indexed[int(frame)]  # Keep invisible-only frames in the evaluation domain.
        if ground_truth and row[4] not in (0, 1):
            raise ValueError("visible must be 0 or 1.")
        if not ground_truth or row[4]:
            indexed[int(frame)].append((int(identity), float(x), float(y)))
    return indexed


def score(truth, observations, gate=8.0):
    """Return six legacy-order metrics plus matched-pair details.

    Evaluate the union of input frames (including prediction-only frames).
    Maximize the number of matches within gate, then minimize total distance.
    Invisible truth is excluded; predictions there are false positives unless
    matched to another visible object. No matches => RMSE is undefined ('').
    """
    if not np.isfinite(gate) or gate <= 0:
        raise ValueError("Evaluation gate must be positive and finite.")
    truth_by_frame = _index(truth, True)
    pred_by_frame = _index(observations, False)
    last_id, rows, errors = {}, [], []
    switches = missed = false_positive = 0
    track_ids = set()
    for frame in sorted(truth_by_frame.keys() | pred_by_frame.keys()):
        gt, pred = truth_by_frame[frame], pred_by_frame[frame]
        track_ids.update(p[0] for p in pred)
        n, m = len(gt), len(pred)
        pairs = []
        distances = np.empty((n, m))
        if n and m:
            a, b = np.asarray(gt)[:, 1:], np.asarray(pred)[:, 1:]
            distances = np.linalg.norm(a[:, None] - b[None, :], axis=2)
            penalty = (min(n, m) + 1) * (gate + 1)
            cost = np.zeros((n + m, n + m))
            cost[:n, :m] = np.where(distances <= gate, distances, penalty * (n + m + 1))
            cost[:n, m:] = penalty
            cost[n:, :m] = penalty
            rr, cc = linear_sum_assignment(cost)
            pairs = [(i, j) for i, j in zip(rr, cc) if i < n and j < m and distances[i, j] <= gate]
        missed += n - len(pairs)
        false_positive += m - len(pairs)
        for i, j in pairs:
            object_id, track_id = gt[i][0], pred[j][0]
            switched = object_id in last_id and last_id[object_id] != track_id
            switches += int(switched)
            last_id[object_id] = track_id
            errors.append(distances[i, j])
            rows.append((frame, object_id, track_id, round(distances[i, j], 4), int(switched)))
    rmse = round(float(np.sqrt(np.mean(np.square(errors)))), 4) if errors else ""
    return (len(errors), missed, false_positive, switches, len(track_ids), rmse), rows


def score_with_identity(truth, observations, gate=8.0):
    """score() plus MOTA and IDF1, in METRICS order.

    MOTA = 1 - (missed + false positives + ID switches) / visible truth objects
    (Bernardin & Stiefelhagen 2008). IDF1 = 2 IDTP / (visible truth + predictions),
    where IDTP comes from the best one-to-one pairing of true objects and track
    IDs over the whole video, counting frames where the pair is within gate
    (Ristani et al. 2016).
    """
    metrics, rows = score(truth, observations, gate)
    matched, missed, false_positive, switches = metrics[:4]
    truth_by_frame = _index(truth, True)
    pred_by_frame = _index(observations, False)
    gt_ids = sorted({i for objects in truth_by_frame.values() for i, _, _ in objects})
    track_ids = sorted({i for objects in pred_by_frame.values() for i, _, _ in objects})
    overlap = np.zeros((len(gt_ids), len(track_ids)))
    for frame, gt in truth_by_frame.items():
        pred = pred_by_frame.get(frame, [])
        if not gt or not pred:
            continue
        distances = np.linalg.norm(np.asarray(gt)[:, None, 1:] - np.asarray(pred)[None, :, 1:], axis=2)
        for i, j in zip(*np.nonzero(distances <= gate)):
            overlap[gt_ids.index(gt[i][0]), track_ids.index(pred[j][0])] += 1
    id_true_positive = overlap[linear_sum_assignment(-overlap)].sum() if overlap.size else 0.0
    total_truth = matched + missed
    total = total_truth + sum(len(p) for p in pred_by_frame.values())
    mota = round(1 - (missed + false_positive + switches) / total_truth, 4) if total_truth else ""
    idf1 = round(2 * float(id_true_positive) / total, 4) if total else ""
    return metrics + (mota, idf1), rows
