"""Benchmark the existing decode + detect + track pipeline on a real video.

Run from the repository root, for example:
    python scripts/benchmark_real_runtime.py data/real/scene01_lossless.mkv \
        --per-run-output output/person1/timing/runtime_per_run.csv \
        --summary-output output/person1/timing/runtime_summary.csv --repeats 5 --warmups 1

Every configuration receives the same input file. The per-run CSV stores
measured samples only; warm-ups are executed but excluded from both CSVs.
The summary CSV stores measured-run percentiles.
No output is replaced.
"""
import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tracking import METHODS, Tracker, detect, video_frames, video_info


DETECTORS = {"fixed_110": 110, "otsu": "otsu"}
PER_RUN_FIELDS = (
    "method", "detector", "run_index", "frame_count", "elapsed_seconds",
    "throughput_fps", "metadata_json",
)
SUMMARY_FIELDS = (
    "method", "detector", "frame_count", "median_seconds", "p25_seconds",
    "p75_seconds", "median_fps", "p25_fps", "p75_fps", "metadata_json",
)


def summarize(samples, frame_count):
    """Return wall-clock and throughput quartiles for measured runs only."""
    if len(samples) < 5 or frame_count <= 0 or any(value <= 0 for value in samples):
        raise ValueError("Need at least five positive-duration samples and a positive frame count.")
    rates = [frame_count / value for value in samples]
    q_seconds = np.percentile(samples, [25, 50, 75])
    q_rates = np.percentile(rates, [25, 50, 75])
    return {
        "median_seconds": float(q_seconds[1]),
        "p25_seconds": float(q_seconds[0]),
        "p75_seconds": float(q_seconds[2]),
        "median_fps": float(q_rates[1]),
        "p25_fps": float(q_rates[0]),
        "p75_fps": float(q_rates[2]),
    }


def run_configuration(video, width, height, method, detector, repeats, warmups=1,
                      clock=perf_counter, frame_source=video_frames,
                      detector_function=detect, tracker_class=Tracker, solver="scipy"):
    """Run warm-ups and measured end-to-end frame loops for one configuration."""
    threshold = DETECTORS[detector]
    durations = []
    frame_count = None
    for run_index in range(warmups + repeats):
        tracker = tracker_class(method, 24, 5, solver)
        count = 0
        start = clock()
        for index, frame in enumerate(frame_source(video, width, height)):
            _, points = detector_function(frame, threshold, 35, 240)
            tracker.update(index, points)
            count += 1
        elapsed = clock() - start
        if count == 0:
            raise RuntimeError("Input video produced no decodable frames.")
        if frame_count is not None and count != frame_count:
            raise RuntimeError("Frame count changed between repetitions; benchmark input is not stable.")
        frame_count = count
        if run_index >= warmups:
            durations.append(elapsed)
    return frame_count, durations


def runtime_metadata(video, video_rate, repeats, warmups, ffmpeg_version, commit,
                     solver="scipy"):
    return {
        "video_path": str(video), "video_sha256": sha256(video),
        "video_fps_reported": video_rate, "commit": commit,
        "hardware": {
            "platform": platform.platform(), "machine": platform.machine(),
            "processor": platform.processor(), "logical_cpus": os.cpu_count(),
            "python_version": platform.python_version(),
        },
        "ffmpeg_version": ffmpeg_version,
        "parameters": {
            "trackers": list(METHODS), "detectors": DETECTORS,
            "warmups_per_configuration": warmups, "measured_repeats": repeats,
            "gate_px": 24, "max_missing": 5, "min_area": 35,
            "max_area": 240, "solver": solver,
            "timed_stages": "FFmpeg video decode + detect + track update; excludes output rendering/encoding",
        },
    }


def sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def execute(video, per_run_output, summary_output, repeats=5, warmups=1,
            solver="scipy"):
    video, per_run_output, summary_output = map(Path,
        (video, per_run_output, summary_output))
    if repeats < 5 or warmups < 1:
        raise ValueError("Use at least five measured repeats and one warm-up per configuration.")
    if not video.is_file():
        raise FileNotFoundError(f"Real video not found: {video}")
    for output in (per_run_output, summary_output):
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite benchmark output: {output}")
    width, height, video_rate = video_info(video)
    ffmpeg_version = subprocess.run(["ffmpeg", "-version"], check=True,
                                    capture_output=True, text=True).stdout.splitlines()[0]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], check=True,
                            capture_output=True, text=True).stdout.strip()
    metadata = runtime_metadata(video, video_rate, repeats, warmups, ffmpeg_version,
                                commit, solver)
    per_run_rows, summary_rows = [], []
    for method in METHODS:
        for detector in DETECTORS:
            frame_count, samples = run_configuration(
                video, width, height, method, detector, repeats, warmups,
                solver=solver)
            for index, elapsed in enumerate(samples, 1):
                per_run_rows.append({"method": method,
                             "detector": detector, "run_index": index,
                             "frame_count": frame_count, "elapsed_seconds": elapsed,
                             "throughput_fps": frame_count / elapsed,
                             "metadata_json": json.dumps(metadata, sort_keys=True)})
            summary = summarize(samples, frame_count)
            summary_rows.append({"method": method, "detector": detector,
                         "frame_count": frame_count, **summary,
                         "metadata_json": json.dumps(metadata, sort_keys=True)})

    for output in (per_run_output, summary_output):
        output.parent.mkdir(parents=True, exist_ok=True)
    temporary_names = []
    try:
        for output, rows, fields in (
                (per_run_output, per_run_rows, PER_RUN_FIELDS),
                (summary_output, summary_rows, SUMMARY_FIELDS)):
            with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8",
                                             dir=output.parent, prefix=output.name + ".",
                                             suffix=".tmp", delete=False) as handle:
                temporary_names.append(handle.name)
                writer = csv.DictWriter(handle, fieldnames=fields,
                                        lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
        for output in (per_run_output, summary_output):
            if output.exists():
                raise FileExistsError(f"Refusing to overwrite benchmark output: {output}")
        os.rename(temporary_names[0], per_run_output)
        os.rename(temporary_names[1], summary_output)
    finally:
        for temporary_name in temporary_names:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
    return per_run_output, summary_output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", nargs="?", type=Path,
                        default=Path("data/real/scene01_lossless.mkv"))
    parser.add_argument("--per-run-output", type=Path,
                        default=Path("output/person1/timing/runtime_per_run.csv"))
    parser.add_argument("--summary-output", type=Path,
                        default=Path("output/person1/timing/runtime_summary.csv"))
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--solver", choices=("educational", "scipy"), default="scipy")
    args = parser.parse_args()
    try:
        per_run, summary = execute(args.video, args.per_run_output,
                                   args.summary_output, args.repeats,
                                   args.warmups, args.solver)
        print(f"Wrote runtime benchmark: {per_run} and {summary}")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"BLOCKED/FAILED: {error}\n")


if __name__ == "__main__":
    main()
