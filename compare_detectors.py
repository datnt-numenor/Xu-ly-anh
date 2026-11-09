"""Compare Python centroids with a TrackMate CSV on identical PNG frames.

TrackMate detections are a reference, NOT biological ground truth. This checks
centroid agreement before interpreting tracker differences. Coordinates must be
pixels and frames zero-based; do not use TrackMate coordinates calibrated in um.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from evaluation import score
from score_trackmate import read_rows
from tracking import detect, write_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frames', type=Path)
    parser.add_argument('trackmate_csv', type=Path)
    parser.add_argument('--gate', type=float, default=2)
    parser.add_argument('--threshold', type=int, default=110)
    parser.add_argument('--output', type=Path, default=Path('results/detector_comparison'))
    args = parser.parse_args()
    paths = sorted(args.frames.glob('frame_*.png'))
    if not paths:
        parser.error('No frame PNGs found.')
    expected = [f'frame_{i:03d}.png' for i in range(len(paths))]
    if [p.name for p in paths] != expected:
        parser.error('Expected consecutive zero-based frame_000.png, frame_001.png, ...')
    reference = read_rows(args.trackmate_csv, ('frame', 'track_id', 'x', 'y'), (int, int, float, float))
    if any(f < 0 or f >= len(paths) for f, *_ in reference):
        parser.error('TrackMate frame lies outside the PNG sequence.')
    observations = []
    for frame, path in enumerate(paths):
        points = detect(np.asarray(Image.open(path).convert('L')), args.threshold, 35, 240)[1]
        observations.extend((frame, i, x, y) for i, (x, y) in enumerate(points))
    metrics, _ = score([(f, i, x, y, 1) for f, i, x, y in reference], observations, args.gate)
    summary = dict(matched=metrics[0], unmatched_trackmate=metrics[1], unmatched_python=metrics[2],
                   matched_centroid_rmse_px=metrics[5], gate_px=args.gate,
                   note='Agreement only; ignores track IDs and is not ground-truth accuracy.')
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    write_csv(args.output / 'python_detections.csv', ('frame', 'local_detection_id', 'x', 'y'), observations)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
