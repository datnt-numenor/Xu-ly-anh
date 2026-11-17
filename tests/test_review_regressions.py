"""Small hand-computed or independent-reference regression cases."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import contextmanager
import io

import numpy as np
from scipy import ndimage
from evaluation import score_with_identity
from tracking import detect, run_video
from scripts.ground_truth_annotator import representative_indices


class ReviewRegressions(unittest.TestCase):
    def test_distance_matching_is_not_clear_continuity(self):
        gt = [(f, i, x, 0, 1) for f in (0, 1) for i, x in ((1, 0), (2, 6))]
        pred = [(0, 1, 0, 0), (0, 2, 6, 0), (1, 1, 4, 0), (1, 2, 2, 0)]
        metrics, _ = score_with_identity(gt, pred, 8)
        self.assertEqual(metrics[3], 2)
        self.assertEqual(metrics[-2], 0.5)
        # All four observations of the optimal global identity pairing are in gate.
        self.assertEqual(metrics[-1], 1.0)

    def test_idf1_fragmentation_and_prediction_only_frame(self):
        gt = [(f, 1, 0, 0, 1) for f in range(4)]
        pred = [(f, 10 if f < 2 else 20, 0, 0) for f in range(4)]
        metrics, _ = score_with_identity(gt, pred)
        self.assertEqual(metrics[-2:], (0.75, 0.5))
        metrics, _ = score_with_identity(gt, pred + [(4, 30, 100, 100)])
        self.assertEqual(metrics[-2:], (0.5, 0.4444))
        self.assertEqual(score_with_identity([], [])[0][-2:], ("", ""))

    def test_otsu_on_smoothed_image_against_bruteforce(self):
        rng = np.random.default_rng(7)
        frame = rng.integers(0, 256, size=(23, 29), dtype=np.uint8)
        processed = np.rint(ndimage.gaussian_filter(frame.astype(float), 1.5)).astype(np.uint8)
        variances = []
        for threshold in range(256):
            low, high = processed[processed <= threshold], processed[processed > threshold]
            variances.append(len(low) * len(high) * (float(low.mean()) - float(high.mean())) ** 2
                             if len(low) and len(high) else 0)
        expected = processed > int(np.argmax(variances))
        actual, _ = detect(frame, "otsu", 1, frame.size, blur=1.5, opening=False)
        np.testing.assert_array_equal(actual, expected)

    def test_noise_sweep_keeps_seed_rows_and_missing_rmse(self):
        import csv
        import benchmark_png
        metrics = (0, 1, 0, 0, 0, "", 0.0, 0.0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with patch.object(benchmark_png, "NOISE_LEVELS", (0,)), \
                 patch.object(benchmark_png, "BLURS", (0.0,)), \
                 patch.object(benchmark_png, "METHODS", ("nearest",)), \
                 patch.object(benchmark_png, "render", return_value=[]), \
                 patch.object(benchmark_png, "score", return_value=(metrics, [])):
                rows = benchmark_png.noise_sweep(output)
            self.assertEqual(rows[0][3 + 5], "")
            with (output / "noise_sweep_per_run.csv").open() as stream:
                runs = list(csv.DictReader(stream))
            with (output / "noise_sweep_std.csv").open() as stream:
                summary = next(csv.DictReader(stream))
            self.assertEqual({r["seed"] for r in runs}, {"1", "2", "3"})
            self.assertEqual(summary["matched_detection_rmse_px_n"], "0")
            self.assertEqual(summary["matched_detection_rmse_px_std"], "")
            self.assertEqual(summary["missed_std"], "0.0")

    def test_short_preview_indices(self):
        for count in (1, 2, 3, 48, 90, 91, 150):
            indices = representative_indices(count)
            self.assertEqual(indices, sorted(set(indices)))
            self.assertTrue(all(0 <= i < count for i in indices))
            self.assertIn(count - 1, indices)
        with self.assertRaises(ValueError):
            representative_indices(0)

    def test_detection_files_survive_blur_variant(self):
        @contextmanager
        def fake_encoder(*args):
            yield SimpleNamespace(stdin=io.BytesIO(), wait=lambda: 0)
        frame = np.zeros((24, 24), dtype=np.uint8)
        frame[5:12, 5:12] = 220
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(video=Path("fake.mp4"), output=Path(directory),
                                   method="kalman", gate=24, max_missing=5,
                                   threshold=110, min_area=1, max_area=500, blur=0)
            with patch("tracking.video_info", return_value=(24, 24, "15/1")), \
                 patch("tracking.video_frames", side_effect=lambda *a: iter([frame])), \
                 patch("tracking.encoder", fake_encoder):
                run_video(args)
                original = (args.output / "kalman_detections.csv").read_bytes()
                args.blur = 1.5
                run_video(args)
            self.assertEqual((args.output / "kalman_detections.csv").read_bytes(), original)
            self.assertTrue((args.output / "kalman_blur_detections.csv").is_file())


if __name__ == "__main__":
    unittest.main()
