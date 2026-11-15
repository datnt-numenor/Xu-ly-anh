"""Structural and continuity audit for a manually annotated GT pilot.

This tool validates human-entered rows and surfaces gaps for human review. It
does not infer identities, coordinates, visibility, or whether an ID is correct.
"""
import argparse
from collections import defaultdict
from pathlib import Path

try:  # Support both `python scripts/...` and package imports from tests.
    from .ground_truth_annotator import DEFAULT_FRAMES, load_labels, validate_p4_dataset
except ImportError:
    from ground_truth_annotator import DEFAULT_FRAMES, load_labels, validate_p4_dataset


def audit_pilot(rows, frame_count, pilot_start, pilot_end):
    """Return a report; continuity gaps are review flags, never auto-corrections."""
    errors, review = [], []
    span = pilot_end - pilot_start + 1
    if span < 20 or span > 30:
        errors.append("Pilot span must be 20 to 30 consecutive frames inclusive.")
    if pilot_start < 0 or pilot_end >= frame_count or pilot_start > pilot_end:
        errors.append("Pilot frame range is outside the available frame sequence.")
    if not rows:
        errors.append("CSV contains no labels; annotate the pilot before validation.")

    outside = sorted({row["frame"] for row in rows
                      if not pilot_start <= row["frame"] <= pilot_end})
    if outside:
        errors.append(f"Labels outside requested pilot interval: {outside}.")

    frames_to_ids = defaultdict(list)
    by_id = defaultdict(list)
    for row in rows:
        frame, object_id = row["frame"], row["object_id"]
        frames_to_ids[frame].append(object_id)
        by_id[object_id].append(row)
    expected = set(range(pilot_start, pilot_end + 1))
    observed = {frame for frame in frames_to_ids if frame in expected}
    missing_frames = sorted(expected - observed)
    if missing_frames:
        review.append(f"No label rows in pilot frame(s): {missing_frames}.")

    continuity = []
    for object_id, id_rows in sorted(by_id.items()):
        seen_frames = sorted({row["frame"] for row in id_rows
                              if pilot_start <= row["frame"] <= pilot_end})
        gaps = [list(range(left + 1, right))
                for left, right in zip(seen_frames, seen_frames[1:])
                if right - left > 1]
        gaps = [frame for gap in gaps for frame in gap]
        visible_zero = sorted(row["frame"] for row in id_rows
                              if row["visible"] == 0 and pilot_start <= row["frame"] <= pilot_end)
        if gaps:
            review.append(f"ID {object_id} has unlabeled gap frame(s): {gaps}; review continuity.")
        if len(seen_frames) < 2:
            review.append(f"ID {object_id} appears in fewer than two pilot frames; continuity cannot be assessed.")
        continuity.append({"object_id": object_id, "frames": seen_frames,
                           "unlabeled_gaps": gaps, "visible_zero_frames": visible_zero})

    return {
        "pilot_start": pilot_start,
        "pilot_end": pilot_end,
        "pilot_frame_count": span,
        "label_rows": len(rows),
        "annotated_frames": sorted(observed),
        "missing_label_frames": missing_frames,
        "object_ids": sorted(by_id),
        "visible_zero_rows": sum(row["visible"] == 0 for row in rows),
        "continuity": continuity,
        "errors": errors,
        "review_flags": review,
        "structural_pass": not errors,
        "human_identity_review_required": True,
        "official_ground_truth": False,
    }


def markdown_report(report, csv_path):
    lines = ["# Ground-truth pilot validation", "",
             f"- Pilot CSV: `{csv_path}`",
             f"- Frames: {report['pilot_start']}–{report['pilot_end']} ({report['pilot_frame_count']})",
             f"- Label rows: {report['label_rows']}",
             f"- IDs: {report['object_ids']}",
             f"- Rows with visible=0: {report['visible_zero_rows']}",
             f"- Structural validation: {'PASS' if report['structural_pass'] else 'FAIL'}",
             "- Human identity review: required; this report does not certify ID correctness.",
             "- Official ground truth: no.", "", "## Errors", ""]
    lines.extend([f"- {item}" for item in report["errors"]] or ["- None"])
    lines.extend(["", "## Review flags", ""])
    lines.extend([f"- {item}" for item in report["review_flags"]] or ["- None"])
    lines.extend(["", "## ID continuity summary", ""])
    for item in report["continuity"]:
        lines.append(f"- ID {item['object_id']}: frames {item['frames']}; "
                     f"unlabeled gaps {item['unlabeled_gaps']}; "
                     f"visible=0 at {item['visible_zero_frames']}.")
    lines.extend(["", "A structural PASS validates schema and range only. A human must inspect "
                  "all uncertain boundaries and confirm whether each object ID remains "
                  "the same physical object before any official use."])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="manual pilot CSV")
    parser.add_argument("--start", type=int, required=True, help="first zero-based frame")
    parser.add_argument("--end", type=int, required=True, help="last zero-based frame")
    parser.add_argument("--frames", type=Path, default=DEFAULT_FRAMES)
    parser.add_argument("--manifest", type=Path, default=Path("data/real/scene01_manifest.json"))
    parser.add_argument("--report", type=Path, default=Path("output/person1/ground_truth/pilot_validation.md"))
    args = parser.parse_args()
    try:
        frame_paths, _ = validate_p4_dataset(args.frames, args.manifest)
        rows = load_labels(args.csv, len(frame_paths))
        report = audit_pilot(rows, len(frame_paths), args.start, args.end)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(markdown_report(report, args.csv), encoding="utf-8")
        print(f"{'PASS' if report['structural_pass'] else 'FAIL'}: {len(rows)} labels; "
              f"{len(report['review_flags'])} review flags; report={args.report}")
        if not report["structural_pass"]:
            raise SystemExit(1)
    except (OSError, ValueError) as error:
        parser.exit(2, f"FAILED: {error}\n")


if __name__ == "__main__":
    main()
