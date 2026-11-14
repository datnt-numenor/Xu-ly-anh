"""Unit tests for benchmark helpers; mocked fixtures are never benchmark results."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import benchmark_real_runtime as benchmark


class BenchmarkRealRuntimeTests(unittest.TestCase):
    def test_summary_statistics_use_measured_samples_and_frame_count(self):
        result = benchmark.summarize([1, 2, 3, 4, 5], 10)
        self.assertEqual(result["median_seconds"], 3)
        self.assertEqual(result["p25_seconds"], 2)
        self.assertEqual(result["p75_seconds"], 4)
        self.assertAlmostEqual(result["median_fps"], 10 / 3)
        self.assertAlmostEqual(result["p25_fps"], 2.5)
        self.assertAlmostEqual(result["p75_fps"], 5)
        with self.assertRaises(ValueError):
            benchmark.summarize([1, 2, 3, 4], 10)

    def test_configuration_runs_warmup_and_keeps_it_out_of_samples(self):
        times = iter([0, 10, 20, 30, 40, 50])
        frames = []

        class FakeTracker:
            def __init__(self, *args):
                pass

            def update(self, index, points):
                pass

        def frame_source(*args):
            frames.append(1)
            return [object(), object()]

        count, samples = benchmark.run_configuration(
            "mock-video", 2, 1, "nearest", "fixed_110", 2, 1,
            clock=lambda: next(times), frame_source=frame_source,
            detector_function=lambda *args: (None, []), tracker_class=FakeTracker)
        self.assertEqual(count, 2)
        self.assertEqual(samples, [10, 10])
        self.assertEqual(len(frames), 3)

    def test_execute_writes_csv_and_metadata_from_mocked_video_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "fixture.mp4"
            source.write_bytes(b"unit-test fixture; not a video measurement")
            per_run_output = root / "runtime_per_run.csv"
            summary_output = root / "runtime_summary.csv"
            fake_process = type("Process", (), {"stdout": "ffmpeg mock version"})()
            with patch.object(benchmark, "video_info", return_value=(320, 180, "15/1")), \
                 patch.object(benchmark.platform, "platform", return_value="mock platform"), \
                 patch.object(benchmark.platform, "machine", return_value="mock machine"), \
                 patch.object(benchmark.platform, "processor", return_value="mock processor"), \
                 patch.object(benchmark.subprocess, "run", side_effect=[fake_process,
                     type("Process", (), {"stdout": "unit-test-commit"})()]), \
                 patch.object(benchmark, "run_configuration", return_value=(3, [1, 2, 3, 4, 5])):
                # execute's production guard requires >=5; this mock test exercises row
                # generation with the same five measured observations as the real default.
                result = benchmark.execute(source, per_run_output, summary_output,
                                           repeats=5, warmups=1, solver="scipy")
            with per_run_output.open(newline="", encoding="utf-8") as handle:
                run_rows = list(csv.DictReader(handle))
            with summary_output.open(newline="", encoding="utf-8") as handle:
                summaries = list(csv.DictReader(handle))
            self.assertEqual(result, (per_run_output, summary_output))
            self.assertEqual(len(summaries), 6)
            meta = json.loads(summaries[0]["metadata_json"])
            self.assertEqual(meta["commit"], "unit-test-commit")
            self.assertEqual(meta["hardware"]["logical_cpus"] is not None, True)
            self.assertTrue(meta["hardware"]["python_version"])
            self.assertEqual(meta["parameters"]["solver"], "scipy")
            self.assertEqual(len(run_rows), 30)
            self.assertTrue(all(row["elapsed_seconds"] and row["throughput_fps"]
                                and row["frame_count"] and row["metadata_json"]
                                for row in run_rows))
            with self.assertRaises(FileExistsError):
                benchmark.execute(source, per_run_output, summary_output)


if __name__ == "__main__":
    unittest.main()
