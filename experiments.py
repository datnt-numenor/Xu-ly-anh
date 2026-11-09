"""Reproducible synthetic stress tests; all data are synthetic, not real video.

python experiments.py --seeds 0 1 2 3 4
python experiments.py --export-data data/stress --seeds 0
"""
import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from time import perf_counter

import numpy as np
import scipy
import PIL
from PIL import Image

from evaluation import FIELDS, score
from tracking import METHODS, Tracker, associate, detect, write_csv

SCENARIOS = ("separate", "occlusion", "overlap", "turn", "illumination")
FRAMES = 80
SIZE = (180, 320)


def generate(scenario, seed, count=FRAMES):
    """Three radius-7 disks, with deterministic trajectories and seeded image noise."""
    if scenario not in SCENARIOS or count < 2:
        raise ValueError("Unknown scenario or insufficient frames.")
    rng = np.random.default_rng(seed)
    yy, xx = np.ogrid[:SIZE[0], :SIZE[1]]
    images, truth = [], []
    for frame in range(count):
        u = frame / (count - 1)
        background = 25 if scenario != "illumination" else 25 + 110 * u
        foreground = 218 if scenario != "illumination" else 95 + 110 * u
        image = np.clip(background + rng.normal(0, 8, SIZE), 0, 255).astype(np.uint8)
        x1 = 35 + 240 * u
        if scenario == "turn":
            x1 = 35 + 240 * u if u < 0.5 else 275 - 240 * u
        positions = [(x1, 60), (275 - 240 * u, 60 if scenario == "overlap" else 103),
                     (75 + 90 * u, 145 - 15 * u)]
        for identity, (x, y) in enumerate(positions, 1):
            visible = not (scenario == "occlusion" and identity == 1 and 36 <= frame <= 39)
            truth.append((frame, identity, x, y, int(visible)))
            if visible:
                image[(xx - x) ** 2 + (yy - y) ** 2 <= 49] = int(foreground)
        for x, y in rng.integers((1, 1), (319, 179), (25, 2)):
            image[y, x] = 205
        images.append(image)
    return images, truth


def track_sequence(detections, method, solver="scipy"):
    tracker = Tracker(method, 24, 5, solver)
    observations, states = [], []
    for frame, points in enumerate(detections):
        visible = tracker.update(frame, points)
        observations.extend((frame, t.id, *t.points[-1][1:]) for t in visible)
        states.extend((frame, t.id, *t.state[:2], int(t.misses == 0)) for t in tracker.active)
    return observations, states


def state_metrics(truth, states, matches):
    """Observed state error uses detection-established matches, never re-matches states.

    Hidden prediction evaluation freezes each object's last visible match; only
    unobserved states count, so a track stolen by another visible object reduces
    coverage. Conditional RMSE must always be read with coverage.
    """
    by_frame = defaultdict(list)
    for row in truth:
        by_frame[row[0]].append(row)
    states = {(f, i): (x, y, seen) for f, i, x, y, seen in states}
    match_map = {(f, obj): tid for f, obj, tid, _, _ in matches}
    last, observed_errors, hidden_errors = {}, [], []
    hidden_total = 0
    for frame in sorted(by_frame):
        for _, obj, x, y, visible in by_frame[frame]:
            if visible:
                tid = match_map.get((frame, obj))
                if tid is not None:
                    last[obj] = tid
                    sx, sy, _ = states[(frame, tid)]
                    observed_errors.append((sx - x) ** 2 + (sy - y) ** 2)
                else:
                    last.pop(obj, None)  # No reliable binding entering an occlusion.
            else:
                hidden_total += 1
                state = states.get((frame, last.get(obj)))
                if state is not None and state[2] == 0:
                    hidden_errors.append((state[0] - x) ** 2 + (state[1] - y) ** 2)
    rmse = lambda errors: round(float(np.sqrt(np.mean(errors))), 6) if errors else ""
    return (rmse(observed_errors), hidden_total, len(hidden_errors), rmse(hidden_errors))


def timings(output):
    rows = []
    rng = np.random.default_rng(123)
    for count in (3, 10, 30, 100):
        points = rng.uniform(0, 320, (count, 2))
        targets = points + rng.normal(0, 3, (count, 2))
        distances = np.linalg.norm(points[:, None] - targets[None, :], axis=2)
        costs = []
        for solver in ("educational", "scipy"):
            result = associate(distances, 24, "hungarian", solver)
            costs.append((len(result), sum(distances[i, j] for i, j in result)))
            samples = []
            for _ in range(9):
                start = perf_counter()
                associate(distances, 24, "hungarian", solver)
                samples.append(1000 * (perf_counter() - start))
            rows.append((count, solver, 9, *[round(float(v), 6) for v in
                        (np.median(samples), np.percentile(samples, 25), np.percentile(samples, 75))]))
        assert costs[0][0] == costs[1][0] and np.isclose(costs[0][1], costs[1][1])
    write_csv(output / "solver_timing.csv", ("objects", "solver", "repeats", "median_ms", "p25_ms", "p75_ms"), rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=list(range(5)))
    parser.add_argument("--output", type=Path, default=Path("results/stress"))
    parser.add_argument("--export-data", type=Path, help="Optional lossless PNGs and truth for Fiji")
    args = parser.parse_args()
    if len(set(args.seeds)) != len(args.seeds) or any(seed < 0 for seed in args.seeds):
        parser.error("Seeds must be distinct nonnegative integers.")
    args.output.mkdir(parents=True, exist_ok=True)
    rows, groups = [], defaultdict(list)
    extra = ("observed_state_rmse_px", "hidden_truth", "hidden_predicted", "hidden_state_rmse_px")
    for scenario in SCENARIOS:
        for seed in args.seeds:
            frames, truth = generate(scenario, seed)
            if args.export_data:
                dest = args.export_data / f"{scenario}_seed{seed}"
                dest.mkdir(parents=True, exist_ok=True)
                for i, frame in enumerate(frames):
                    Image.fromarray(frame).save(dest / f"frame_{i:03d}.png")
                write_csv(args.export_data / f"{dest.name}_truth.csv",
                          ("frame", "object_id", "x", "y", "visible"), truth)
            for detector in ("fixed", "otsu"):
                detections = [detect(frame, 110 if detector == "fixed" else "otsu", 35, 240)[1]
                              for frame in frames]
                for method in METHODS:
                    observations, states = track_sequence(detections, method)
                    metrics, matches = score(truth, observations)
                    state_result = state_metrics(truth, states, matches)
                    rows.append((scenario, seed, detector, method, *metrics, *state_result))
                    groups[scenario, detector, method].append(metrics)
                    # A representative seed retains raw outputs for auditing metrics.
                    if seed == args.seeds[0]:
                        prefix = args.output / "details" / f"{scenario}_{detector}_{method}"
                        write_csv(prefix.with_suffix(".csv"), ("frame", "track_id", "x", "y"), observations)
                        write_csv(prefix.with_name(prefix.name + "_states.csv"),
                                  ("frame", "track_id", "state_x", "state_y", "observed"), states)
                        write_csv(prefix.with_name(prefix.name + "_evaluation.csv"),
                                  ("frame", "object_id", "track_id", "error_px", "id_switch"), matches)
            print(f"Completed {scenario}, seed {seed}", flush=True)
    write_csv(args.output / "per_run.csv", ("scenario", "seed", "detector", "method", *FIELDS, *extra), rows)
    aggregated = []
    for key, values in groups.items():
        for index, metric in enumerate(FIELDS):
            numbers = [float(row[index]) for row in values if row[index] != ""]
            aggregated.append((*key, metric, len(numbers),
                               float(np.mean(numbers)) if numbers else "",
                               float(np.std(numbers, ddof=1)) if len(numbers) > 1 else ""))
    write_csv(args.output / "aggregate.csv", ("scenario", "detector", "method", "metric", "n", "mean", "sample_std"), aggregated)
    timings(args.output)
    metadata = dict(python=sys.version, platform=platform.platform(), machine=platform.machine(),
                    processor=platform.processor(), logical_cpus=os.cpu_count(), numpy=np.__version__,
                    scipy=scipy.__version__, pillow=PIL.__version__, seeds=args.seeds, frames=FRAMES,
                    image_size=list(SIZE), solver="scipy", gate=24, evaluation_gate=8, max_missing=5,
                    detector_area=[35, 240], timing="assignment only, warmup + 9 repeats; excludes I/O",
                    thread_env={key: os.environ.get(key) for key in
                                ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
                    source_sha256={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                   for name in ("tracking.py", "evaluation.py", "experiments.py")})
    try:
        metadata["base_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        metadata["base_commit"] = None
    if Path("/proc/cpuinfo").exists():
        metadata["cpu_model"] = next((line.split(":", 1)[1].strip() for line in
                                      Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name")), "")
    (args.output / "environment.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
