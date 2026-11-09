"""Score TrackMate CSV files against the ground truth.

One file:  python score_trackmate.py data/crossing_truth.csv results/fiji/crossing_kalman.csv
Folder:    python score_trackmate.py --folder results/fiji
           scores every <scenario>_<tracker>.csv, writes *_evaluation.csv and summary.csv.
"""
import argparse
import csv
from pathlib import Path

from benchmark import METRICS, ROOT, SCENARIOS, score
from tracking import write_csv

DETAIL_FIELDS = ("frame", "object_id", "track_id", "error_px", "id_switch")
TRACKER_ORDER = ("nearest", "lap", "kalman")


def read_rows(path, columns, types):
    with path.open(encoding="utf-8-sig", newline="") as source:
        return [tuple(convert(row[column]) for column, convert in zip(columns, types))
                for row in csv.DictReader(source)]


def read_truth(path):
    return read_rows(path, ("frame", "object_id", "x", "y", "visible"), (int, int, float, float, int))


def read_tracks(path):
    return read_rows(path, ("frame", "track_id", "x", "y"), (int, int, float, float))


def score_folder(folder):
    summary = []
    for scenario in SCENARIOS:
        truth_path = ROOT / "data" / f"{scenario}_truth.csv"
        paths = [p for p in folder.glob(f"{scenario}_*.csv") if not p.stem.endswith("evaluation")]
        rank = {name: i for i, name in enumerate(TRACKER_ORDER)}
        for path in sorted(paths, key=lambda p: rank.get(p.stem[len(scenario) + 1:], len(rank))):
            tracker = path.stem[len(scenario) + 1:]
            metrics, matches = score(read_truth(truth_path), read_tracks(path))
            summary.append((scenario, tracker, *metrics))
            write_csv(folder / f"{path.stem}_evaluation.csv", DETAIL_FIELDS, matches)
    write_csv(folder / "summary.csv", ("scenario", "method", *METRICS), summary)
    print((folder / "summary.csv").read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("truth", type=Path, nargs="?")
    parser.add_argument("trackmate_csv", type=Path, nargs="?")
    parser.add_argument("--details", type=Path, help="write per-frame matches to this CSV")
    parser.add_argument("--folder", type=Path, help="score every TrackMate CSV in this folder")
    args = parser.parse_args()
    if args.folder:
        score_folder(args.folder)
        return
    if not (args.truth and args.trackmate_csv):
        parser.error("Give truth and TrackMate CSV, or --folder.")
    metrics, matches = score(read_truth(args.truth), read_tracks(args.trackmate_csv))
    for key, value in zip(METRICS, metrics):
        print(f"{key}: {value}")
    if args.details:
        write_csv(args.details, DETAIL_FIELDS, matches)


if __name__ == "__main__":
    main()
