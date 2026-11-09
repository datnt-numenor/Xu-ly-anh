"""Compare trackers on identical PNG input, time each stage, and run parameter and noise sweeps."""
from statistics import median
from time import perf_counter

import numpy as np
from PIL import Image

from benchmark import METRICS, ROOT, SCENARIOS, label, render, score, variants
from tracking import METHODS, Tracker, detect, write_csv

NOISE_LEVELS = (0, 20, 40, 60, 80, 100, 120, 140)
NOISE_SEEDS = (1, 2, 3)
BLURS = (0.0, 1.5)


def detect_all(frames, threshold=110, blur=0.0):
    return [detect(frame, threshold, 35, 240, blur)[1] for frame in frames]


def track_all(spots, method, gate=24, gap=5):
    tracker = Tracker(method, gate, gap)
    return [(i, track.id, *track.points[-1][1:])
            for i, points in enumerate(spots)
            for track in tracker.update(i, points)]


def timed(run, frame_count):
    run()
    samples = []
    for _ in range(9):
        start = perf_counter()
        run()
        samples.append((perf_counter() - start) * 1000 / frame_count)
    return round(median(samples), 4)


def noise_sweep():
    """Add Gaussian sensor noise to the whole crossing video, with and without
    Gaussian smoothing before thresholding. Each value is the mean of 3 seeds."""
    clean, truth = [], []
    for image, frame_truth in render("crossing"):
        clean.append(image.astype(float))
        truth.extend(frame_truth)
    rows = []
    for sigma in NOISE_LEVELS:
        for blur in BLURS:
            runs = {method: [] for method in METHODS}
            for seed in NOISE_SEEDS:
                rng = np.random.default_rng(seed)
                frames = [np.clip(f + rng.normal(0, sigma, f.shape), 0, 255).astype(np.uint8)
                          for f in clean]
                spots = detect_all(frames, blur=blur)
                for method in METHODS:
                    runs[method].append(score(truth, track_all(spots, method))[0])
            for method, results in runs.items():
                mean = [round(float(np.mean([r[k] for r in results])), 4) for k in range(len(METRICS))]
                rows.append((sigma, blur, method, *mean))
    return rows


DETECTOR_VARIANTS = (
    ("threshold_open8", dict()),
    ("threshold_4conn", dict(opening=False, connectivity=4)),
    ("gauss_threshold_open8", dict(blur=1.5)),
)


def detector_variants():
    """Kalman tracking on crossing and noisy with three detector variants."""
    rows = []
    for scenario in ("crossing", "noisy"):
        frames = [np.asarray(Image.open(p).convert("L"))
                  for p in sorted((ROOT / "data" / scenario).glob("frame_*.png"))]
        truth = np.loadtxt(ROOT / "data" / f"{scenario}_truth.csv", delimiter=",", skiprows=1, dtype=int)
        for name, options in DETECTOR_VARIANTS:
            spots = [detect(frame, 110, 35, 240, **options)[1] for frame in frames]
            rows.append((scenario, name, *score(truth, track_all(spots, "kalman"))[0]))
    return rows


def main():
    rows, timing, sweep = [], [], []
    for scenario in SCENARIOS:
        output = ROOT / "results" / scenario
        frames = [np.asarray(Image.open(p).convert("L"))
                  for p in sorted((ROOT / "data" / scenario).glob("frame_*.png"))]
        truth = np.loadtxt(ROOT / "data" / f"{scenario}_truth.csv", delimiter=",", skiprows=1, dtype=int)
        spots = {0.0: detect_all(frames)}
        timing.append((scenario, "detection", timed(lambda: detect_all(frames), len(frames))))
        for method, blur in variants(scenario):
            if blur not in spots:
                spots[blur] = detect_all(frames, blur=blur)
                timing.append((scenario, "detection_blur",
                               timed(lambda: detect_all(frames, blur=blur), len(frames))))
            name = label(method, blur)
            result = track_all(spots[blur], method)
            metrics, matches = score(truth, result)
            rows.append((scenario, name, *metrics))
            timing.append((scenario, name, timed(lambda: track_all(spots[blur], method), len(frames))))
            write_csv(output / f"png_{name}.csv", ("frame", "track_id", "x", "y"), result)
            write_csv(output / f"png_{name}_evaluation.csv",
                      ("frame", "object_id", "track_id", "error_px", "id_switch"), matches)
        if scenario == "crossing":
            for key, options in (("threshold", (15, 50, 110, 210, 218, 230)),
                                 ("gate", (4, 6, 8, 12, 24, 36)),
                                 ("max_missing", (0, 2, 3, 4, 5, 8))):
                for value in options:
                    config = dict(threshold=110, gate=24, max_missing=5)
                    config[key] = value
                    for method in METHODS:
                        result = track_all(detect_all(frames, config["threshold"]), method,
                                           config["gate"], config["max_missing"])
                        sweep.append((key, value, method, *score(truth, result)[0]))
    write_csv(ROOT / "results/summary_png.csv", ("scenario", "method", *METRICS), rows)
    write_csv(ROOT / "results/timing_png.csv", ("scenario", "stage", "median_ms_per_frame"), timing)
    write_csv(ROOT / "results/sweep_png.csv", ("parameter", "value", "method", *METRICS), sweep)
    write_csv(ROOT / "results/detector_variants.csv", ("scenario", "detector", *METRICS), detector_variants())
    write_csv(ROOT / "results/noise_sweep.csv", ("noise_sigma", "blur", "method", *METRICS), noise_sweep())


if __name__ == "__main__":
    main()
