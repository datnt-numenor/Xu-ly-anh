import csv
import itertools
import unittest
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from evaluation import score
from experiments import generate, state_metrics
from tracking import Tracker, associate, detect, hungarian, otsu_threshold


class EvaluationTests(unittest.TestCase):
    def test_all_frames_and_prediction_only_frames(self):
        metrics, _ = score([(0, 1, 0, 0, 1), (43, 1, 0, 0, 1), (100, 1, 0, 0, 1)],
                           [(0, 1, 0, 0), (43, 1, 0, 0), (101, 1, 0, 0)])
        self.assertEqual(metrics[:5], (2, 1, 1, 0, 1))

    def test_empty_and_invisible(self):
        self.assertEqual(score([], [])[0], (0, 0, 0, 0, 0, ""))
        self.assertEqual(score([(50, 1, 0, 0, 0)], [(50, 1, 0, 0)])[0][:3], (0, 0, 1))

    def test_switch_across_gap(self):
        gt = [(0, 1, 0, 0, 1), (1, 1, 0, 0, 0), (2, 1, 0, 0, 1)]
        self.assertEqual(score(gt, [(0, 7, 0, 0), (2, 8, 0, 0)])[0][3], 1)

    def test_validation(self):
        for rows in [[(0, 1, 0, 0), (0, 1, 1, 1)], [(0, 1, np.nan, 0)], [(-1, 1, 0, 0)], [(1.5, 1, 0, 0)]]:
            with self.assertRaises(ValueError):
                score([], rows)
        with self.assertRaises(ValueError):
            score([(0, 1, 0, 0, 2)], [])

    def test_maximum_cardinality_before_distance(self):
        truth = [(0, 1, 0, 0, 1), (0, 2, 6, 0, 1)]
        predictions = [(0, 1, 2, 0), (0, 2, -3, 0)]
        self.assertEqual(score(truth, predictions, gate=5)[0][:3], (2, 0, 0))

    def test_gate_boundary(self):
        self.assertEqual(score([(0, 1, 0, 0, 1)], [(0, 1, 8, 0)])[0][0], 1)
        self.assertEqual(score([(0, 1, 0, 0, 1)], [(0, 1, 8.01, 0)])[0][:3], (0, 1, 1))

    def test_stored_fiji_and_python_metrics(self):
        root = Path(__file__).resolve().parents[1]
        for summary in ("summary.csv", "summary_png.csv", "fiji/summary.csv"):
            with (root / "results" / summary).open() as handle:
                summaries = list(csv.DictReader(handle))
            for expected in summaries:
                scenario, method = expected['scenario'], expected['method']
                suffix = f"fiji/{scenario}_{method}.csv" if summary.startswith('fiji') else f"{scenario}/{'png_' if 'png' in summary else ''}{method}.csv"
                with (root / 'data' / f'{scenario}_truth.csv').open() as handle:
                    truth = [tuple(map(float, row)) for row in list(csv.reader(handle))[1:]]
                with (root / 'results' / suffix).open() as handle:
                    pred = [tuple(map(float, row)) for row in list(csv.reader(handle))[1:]]
                actual = score(truth, pred)[0]
                keys = ('matched', 'missed', 'false_positive', 'id_switches', 'track_ids')
                self.assertEqual(actual[:5], tuple(int(expected[k]) for k in keys))
                self.assertEqual(actual[5], float(expected.get('matched_detection_rmse_px', expected.get('rmse_px'))))


class AssignmentTests(unittest.TestCase):
    def test_hungarian_reference(self):
        rng = np.random.default_rng(19)
        for size in range(1, 13):
            for _ in range(20):
                costs = rng.integers(-10, 80, (size, size))
                self.assertEqual(sum(costs[i, j] for i, j in hungarian(costs)), costs[linear_sum_assignment(costs)].sum())

    def test_rectangular_gated_bruteforce(self):
        rng = np.random.default_rng(18)
        for n in range(5):
            for m in range(5):
                for _ in range(5):
                    distances = rng.uniform(0, 20, (n, m))
                    options = [[]]
                    for k in range(1, min(n, m) + 1):
                        options.extend(list(zip(ii, jj)) for ii in itertools.combinations(range(n), k)
                                       for jj in itertools.permutations(range(m), k)
                                       if all(distances[i, j] <= 8 for i, j in zip(ii, jj)))
                    best = min(options, key=lambda pairs: (-len(pairs), sum(distances[i, j] for i, j in pairs)))
                    for solver in ('educational', 'scipy'):
                        pairs = associate(distances, 8, 'hungarian', solver)
                        self.assertEqual(len(pairs), len(best))
                        self.assertAlmostEqual(sum(distances[i, j] for i, j in pairs), sum(distances[i, j] for i, j in best))


class TrackingTests(unittest.TestCase):
    def test_gap_lifecycle(self):
        tracker = Tracker('kalman', 24, 2)
        identity = tracker.update(0, [[10, 10]])[0].id
        tracker.update(1, [])
        tracker.update(2, [])
        self.assertEqual(tracker.update(3, [[10, 10]])[0].id, identity)
        for frame in (4, 5, 6):
            tracker.update(frame, [])
        self.assertNotEqual(tracker.update(7, [[10, 10]])[0].id, identity)

    def test_frame_contract_and_bounded_history(self):
        tracker = Tracker('kalman', 24, 5)
        for frame in range(100):
            tracker.update(frame, [[frame, 0]])
        self.assertEqual(len(tracker.active[0].points), 30)
        with self.assertRaises(ValueError):
            tracker.update(101, [])

    def test_state_and_observation_are_distinct(self):
        tracker = Tracker('kalman', 24, 5)
        tracker.update(0, [[0, 0]])
        track = tracker.update(1, [[10, 0]])[0]
        self.assertEqual(track.points[-1][1], 10)
        self.assertNotEqual(track.state[0], 10)
        self.assertTrue(np.all(np.linalg.eigvalsh(track.covariance) >= -1e-10))
        tracker.update(2, [])
        self.assertEqual(track.misses, 1)
        self.assertGreater(track.state[0], 10)

    def test_hidden_state_coverage(self):
        truth = [(0, 1, 0, 0, 1), (1, 1, 10, 0, 0), (2, 1, 20, 0, 0)]
        result = state_metrics(truth, [(0, 7, 0, 0, 1), (1, 7, 11, 0, 0)], [(0, 1, 7, 0, 0)])
        self.assertEqual(result, (0, 2, 1, 1))

    def test_otsu_and_overlap_limit(self):
        frame = np.full((40, 40), 25, dtype=np.uint8)
        frame[10:20, 10:20] = 95
        self.assertLess(otsu_threshold(frame), 95)
        self.assertEqual(len(detect(frame, 'otsu', 35, 240)[1]), 1)
        self.assertEqual(len(detect(frame, 110, 35, 240)[1]), 0)
        self.assertEqual(len(detect(np.zeros((20, 20), dtype=np.uint8), 'otsu', 1, 240)[1]), 0)
        frames, truth = generate('overlap', 0)
        self.assertEqual(len(detect(frames[39], 110, 35, 240)[1]), 2)  # 3 GT objects, 2 blobs.
        self.assertTrue(all(row[-1] == 1 for row in truth))


if __name__ == '__main__':
    unittest.main()
