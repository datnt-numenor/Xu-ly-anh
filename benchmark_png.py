"""Compare trackers on identical PNG input and time detection and association."""
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np
from PIL import Image

from benchmark import ROOT
from evaluation import FIELDS, score
from tracking import METHODS, Tracker, detect, write_csv

def main():
    rows, timing, sweep = [], [], []
    for scenario in ("separate", "crossing"):
        output = ROOT / "results" / scenario
        output.mkdir(parents=True, exist_ok=True)
        frames = [np.asarray(Image.open(p).convert("L")) for p in sorted((ROOT / "data" / scenario).glob("frame_*.png"))]
        truth = np.loadtxt(ROOT / "data" / f"{scenario}_truth.csv", delimiter=",", skiprows=1, dtype=int)
        def detect_all(threshold):
            return [detect(frame, threshold, 35, 240)[1] for frame in frames]
        def track_all(spots, method, gate=24, gap=5):
            tracker = Tracker(method, gate, gap)
            return [(i, track.id, *track.points[-1][1:])
                    for i, points in enumerate(spots)
                    for track in tracker.update(i, points)]
        def timed(run):
            run()
            samples = []
            for _ in range(9):
                start = perf_counter()
                run()
                samples.append((perf_counter() - start) * 1000 / len(frames))
            return round(median(samples), 4)
        spots = detect_all(110)
        timing.append((scenario, "detection", timed(lambda: detect_all(110))))
        for method in METHODS:
            result = track_all(spots, method)
            metrics, matches = score(truth, result)
            rows.append((scenario, method, *metrics))
            timing.append((scenario, method, timed(lambda: track_all(spots, method))))
            write_csv(output / f"png_{method}.csv", ("frame", "track_id", "x", "y"), result)
            write_csv(output / f"png_{method}_evaluation.csv",
                      ("frame", "object_id", "track_id", "error_px", "id_switch"), matches)
        if scenario == "crossing":
            cached = {110: spots}
            for key, options in (("threshold", (15, 50, 110, 210, 218, 230)),
                                 ("gate", (4, 6, 8, 12, 24, 36)),
                                 ("max_missing", (0, 2, 3, 4, 5, 8))):
                for value in options:
                    config = dict(threshold=110, gate=24, max_missing=5)
                    config[key] = value
                    threshold = config["threshold"]
                    if threshold not in cached:
                        cached[threshold] = detect_all(threshold)
                    for method in METHODS:
                        result = track_all(cached[threshold], method,
                                           config["gate"], config["max_missing"])
                        sweep.append((key, value, method, *score(truth, result)[0]))
    fields = FIELDS
    write_csv(ROOT / "results/summary_png.csv", ("scenario", "method", *fields), rows)
    write_csv(ROOT / "results/timing_png.csv", ("scenario", "stage", "median_ms_per_frame"), timing)
    write_csv(ROOT / "results/sweep_png.csv", ("parameter", "value", "method", *fields), sweep)

if __name__ == "__main__":
    main()
