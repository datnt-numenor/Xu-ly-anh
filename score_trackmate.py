"""Score TrackMate CSV against the supplied ground truth."""
import argparse
import csv
from pathlib import Path

from benchmark import score
from tracking import write_csv

FIELDS = ("matched", "missed", "false_positive", "id_switches", "track_ids", "rmse_px")


def read_rows(path, columns, types):
    with path.open(encoding="utf-8-sig", newline="") as source:
        return [tuple(convert(row[column]) for column, convert in zip(columns, types))
                for row in csv.DictReader(source)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("truth", type=Path)
    parser.add_argument("trackmate_csv", type=Path)
    parser.add_argument("--details", type=Path)
    args = parser.parse_args()
    truth = read_rows(args.truth, ("frame", "object_id", "x", "y", "visible"),
                      (int, int, float, float, int))
    tracks = read_rows(args.trackmate_csv, ("frame", "track_id", "x", "y"),
                       (int, int, float, float))
    metrics, matches = score(truth, tracks)
    for key, value in zip(FIELDS, metrics):
        print(f"{key}: {value}")
    if args.details:
        write_csv(args.details, ("frame", "object_id", "track_id", "error_px", "id_switch"), matches)


if __name__ == "__main__":
    main()
