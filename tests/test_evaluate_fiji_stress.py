"""Focused F4 checks for full-frame scoring and exported comparison integrity."""
import csv
import unittest
from pathlib import Path

from evaluation import score_with_identity

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/person1/f4"


class F4EvaluationTests(unittest.TestCase):
    def test_empty_prediction_frames_count_as_misses(self):
        truth = [(frame, 1, 10.0, 10.0, 1) for frame in range(80)]
        pred = [(frame, 9, 10.0, 10.0) for frame in range(12, 65)]
        metrics, _ = score_with_identity(truth, pred, gate=8)
        self.assertEqual(metrics[:5], (53, 27, 0, 0, 1))
        self.assertEqual(metrics[6], round(53 / 80, 4))

    def test_exported_comparison_matches_metric_csvs(self):
        def rows(name):
            with (OUT / name).open(newline="", encoding="utf-8") as stream:
                return list(csv.DictReader(stream))

        fiji = {(r["scenario"], r["method"]): r for r in rows("fiji_metrics.csv")}
        python = {(r["scenario"], r["method"]): r for r in rows("python_seed0_fixed_metrics.csv")}
        compare = rows("comparison.csv")
        self.assertEqual((len(fiji), len(python), len(compare)), (15, 15, 15))
        for row in compare:
            fr = fiji[row["scenario"], row["fiji_method"]]
            pr = python[row["scenario"], row["python_method"]]
            self.assertEqual(fr["gt_frames"], "80")
            self.assertEqual(pr["gt_frames"], "80")
            for metric in ("matched", "missed", "false_positive", "id_switches",
                           "track_ids", "matched_detection_rmse_px", "mota", "idf1"):
                self.assertEqual(row[f"fiji_{metric}"], fr[metric])
                self.assertEqual(row[f"python_{metric}"], pr[metric])
                if fr[metric] and pr[metric]:
                    self.assertAlmostEqual(float(row[f"delta_{metric}"]),
                                           round(float(fr[metric]) - float(pr[metric]), 4))
            self.assertEqual(int(fr["matched"]) + int(fr["missed"]), int(fr["gt_visible"]))
            self.assertEqual(int(pr["matched"]) + int(pr["missed"]), int(pr["gt_visible"]))
        for name in ("mota", "idf1", "missed", "id_switches"):
            self.assertGreater((OUT / "figures" / f"{name}.png").stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
