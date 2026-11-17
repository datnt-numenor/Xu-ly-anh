"""Comprehensive Phase F validator for real-video Ground Truth (`output/ground_truth_real/`).

Checks both:
1. Structural validity:
   - Exact CSV schema `frame,object_id,x,y,visible`
   - Frame range `0..149`
   - Finite in-bounds coordinates `0 <= x < 320`, `0 <= y < 180`
   - No duplicate `(frame, object_id)` pairs
   - P4 dataset and manifest SHA256 checksums
2. Scientific & Provenance validity:
   - No fabricated coordinates or auto-promoted `VERIFIED` labels without human review timestamp
   - No unresolved `UNCERTAIN` or `ID_SWITCH_RISK` cases silently included in `reviewed_gt.csv`
   - Full cross-reconciliation between `provisional_gt.csv`, `reviewed_gt.csv`,
     `annotation_status.csv`, `uncertain_cases.csv`, and `annotation_manifest.json`
   - Explicit gate check before allowing promotion to `data/real/ground_truth_manual.csv`
   - Explicit warning on `evaluation.py` full-frame False Positive (FP) behavior when GT covers only a subset/ROI.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

try:
    from .auto_preannotate_real_gt import (
        DEFAULT_OUTPUT_DIR,
        PILOT_END,
        PILOT_START,
        STATUS_FIELDS,
        UNCERTAIN_FIELDS,
    )
    from .ground_truth_annotator import (
        CSV_FIELDS,
        DEFAULT_FRAMES,
        DEFAULT_LABELS,
        DEFAULT_MANIFEST,
        HEIGHT,
        WIDTH,
        load_labels,
        validate_p4_dataset,
    )
    from .validate_ground_truth_pilot import audit_pilot
except ImportError:
    from auto_preannotate_real_gt import (
        DEFAULT_OUTPUT_DIR,
        PILOT_END,
        PILOT_START,
        STATUS_FIELDS,
        UNCERTAIN_FIELDS,
    )
    from ground_truth_annotator import (
        CSV_FIELDS,
        DEFAULT_FRAMES,
        DEFAULT_LABELS,
        DEFAULT_MANIFEST,
        HEIGHT,
        WIDTH,
        load_labels,
        validate_p4_dataset,
    )
    from validate_ground_truth_pilot import audit_pilot


def validate_ground_truth_bundle(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    frames_dir: Path = DEFAULT_FRAMES,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict:
    output_dir = Path(output_dir)
    frame_paths, p4_manifest = validate_p4_dataset(frames_dir, manifest_path)
    frame_count = len(frame_paths)

    structural_errors: list[str] = []
    scientific_blockers: list[str] = []
    warnings: list[str] = []

    provisional_path = output_dir / "provisional_gt.csv"
    reviewed_path = output_dir / "reviewed_gt.csv"
    status_path = output_dir / "annotation_status.csv"
    uncertain_path = output_dir / "uncertain_cases.csv"
    manifest_json_path = output_dir / "annotation_manifest.json"

    for req in (provisional_path, reviewed_path, status_path, uncertain_path, manifest_json_path):
        if not req.is_file():
            structural_errors.append(f"Missing required artifact: {req}")

    if structural_errors:
        return {
            "structural_pass": False,
            "auto_draft_pass": False,
            "pilot_verified_pass": False,
            "full_gt_pass": False,
            "acceptance_state": "FAILED_MISSING_ARTIFACTS",
            "structural_errors": structural_errors,
            "scientific_blockers": scientific_blockers,
            "warnings": warnings,
        }

    manifest_info = json.loads(manifest_json_path.read_text(encoding="utf-8"))
    pilot_range = manifest_info.get("statistics", {}).get("pilot_frame_range", [PILOT_START, PILOT_END])
    p_start, p_end = int(pilot_range[0]), int(pilot_range[1])
    pilot_path = output_dir / f"provisional_pilot_{p_start}_{p_end}.csv"
    if not pilot_path.is_file():
        pilot_path = output_dir / "provisional_pilot_70_89.csv"

    # 1. Validate schema & bounds on provisional_gt.csv and reviewed_gt.csv
    try:
        provisional_rows = load_labels(provisional_path, frame_count)
    except ValueError as err:
        structural_errors.append(f"provisional_gt.csv failed schema validation: {err}")
        provisional_rows = []

    try:
        reviewed_rows = load_labels(reviewed_path, frame_count)
    except ValueError as err:
        structural_errors.append(f"reviewed_gt.csv failed schema validation: {err}")
        reviewed_rows = []

    try:
        pilot_rows = load_labels(pilot_path, frame_count) if pilot_path.is_file() else [
            r for r in provisional_rows if p_start <= r["frame"] <= p_end
        ]
    except ValueError as err:
        structural_errors.append(f"{pilot_path.name} failed schema validation: {err}")
        pilot_rows = []

    # 2. Validate annotation_status.csv and provenance
    with status_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != STATUS_FIELDS:
            structural_errors.append("annotation_status.csv header does not match STATUS_FIELDS.")
        status_rows = list(reader)

    with uncertain_path.open(newline="", encoding="utf-8") as stream:
        u_reader = csv.DictReader(stream)
        if tuple(u_reader.fieldnames or ()) != UNCERTAIN_FIELDS:
            structural_errors.append("uncertain_cases.csv header does not match UNCERTAIN_FIELDS.")
        uncertain_rows = list(u_reader)

    status_by_key = {}
    verified_in_status = []
    uncertain_in_status = []
    unreviewed_in_status = []

    for idx, r in enumerate(status_rows, start=2):
        key = (int(r["frame"]), int(r["object_id"]))
        if key in status_by_key:
            structural_errors.append(f"Duplicate (frame, object_id) {key} in annotation_status.csv at line {idx}")
        status_by_key[key] = r
        st = r["status"]
        if st not in ("UNREVIEWED", "UNCERTAIN", "VERIFIED", "REJECTED"):
            structural_errors.append(f"Invalid status '{st}' at line {idx} of annotation_status.csv")
        if st == "VERIFIED":
            verified_in_status.append(r)
            if not r.get("review_timestamp", "").strip():
                structural_errors.append(
                    f"Row {key} claims VERIFIED without human review_timestamp evidence."
                )
            if r.get("source_method", "").startswith("auto_") and not r.get("review_timestamp", "").strip():
                structural_errors.append(
                    f"Auto-generated row {key} was marked VERIFIED without human review evidence."
                )
        elif st == "UNCERTAIN":
            uncertain_in_status.append(r)
        elif st == "UNREVIEWED":
            unreviewed_in_status.append(r)

    # 3. Verify that reviewed_gt.csv contains ONLY rows marked VERIFIED in annotation_status.csv
    reviewed_keys = {(r["frame"], r["object_id"]) for r in reviewed_rows}
    verified_status_keys = {(int(r["frame"]), int(r["object_id"])) for r in verified_in_status}
    if reviewed_keys != verified_status_keys:
        structural_errors.append(
            f"Mismatch between reviewed_gt.csv ({len(reviewed_keys)} rows) and VERIFIED status rows ({len(verified_status_keys)} rows)."
        )

    # 4. Check that no unresolved uncertain case is silently accepted as VERIFIED without resolution
    open_uncertain = [
        c for c in uncertain_rows if c["resolution_status"] == "OPEN_HUMAN_REVIEW_REQUIRED"
    ]
    open_pilot_uncertain = [
        c for c in open_uncertain if p_start <= int(c["frame"]) <= p_end
    ]
    for c in open_uncertain:
        key = (int(c["frame"]), int(c["object_id"]))
        if key in reviewed_keys:
            structural_errors.append(
                f"Uncertain case {c['case_id']} at {key} is still OPEN_HUMAN_REVIEW_REQUIRED but appears in reviewed_gt.csv!"
            )

    # 5. Check official ground_truth_manual.csv safety rule
    if DEFAULT_LABELS.exists():
        # If it exists, it must only exist when FULL GT PASS is achieved
        if open_uncertain or unreviewed_in_status or len(reviewed_rows) == 0:
            structural_errors.append(
                f"Official {DEFAULT_LABELS} exists prematurely while unreviewed/uncertain rows remain!"
            )

    # 6. Evaluate Pilot (p_start..p_end) and Full sequence verification completeness
    pilot_status_rows = [r for r in status_rows if p_start <= int(r["frame"]) <= p_end]
    pilot_verified = [r for r in pilot_status_rows if r["status"] == "VERIFIED"]
    pilot_unreviewed = [r for r in pilot_status_rows if r["status"] == "UNREVIEWED"]
    pilot_uncertain = [r for r in pilot_status_rows if r["status"] == "UNCERTAIN"]

    pilot_audit = audit_pilot(pilot_rows, frame_count, p_start, p_end)

    if len(pilot_verified) == 0:
        scientific_blockers.append(
            f"Pilot ({p_start}\u2013{p_end}) has 0 human-verified labels (`VERIFIED=0`). Human inspection via `scripts/gt_review_gui.py` is required."
        )
    if len(pilot_unreviewed) > 0 or len(pilot_uncertain) > 0:
        scientific_blockers.append(
            f"Pilot ({p_start}\u2013{p_end}) still has {len(pilot_unreviewed)} UNREVIEWED and {len(pilot_uncertain)} UNCERTAIN labels ({len(open_pilot_uncertain)} open risk cases)."
        )
    if len(unreviewed_in_status) > 0 or len(uncertain_in_status) > 0:
        scientific_blockers.append(
            f"Full sequence (0–149) has {len(unreviewed_in_status)} UNREVIEWED and {len(uncertain_in_status)} UNCERTAIN labels ({len(open_uncertain)} open risk cases)."
        )

    warnings.append(
        "evaluation.py has no ROI or ignore-region filter: every unmatched detector point in an evaluated frame is counted as a False Positive (FP). Do not use subset/anchor-only GT for full-scene FP or MOTA claims."
    )

    observed_status_frames = {int(r["frame"]) for r in status_rows}
    covers_all_video_frames = observed_status_frames == set(range(frame_count))

    structural_pass = len(structural_errors) == 0 and pilot_audit["structural_pass"]
    auto_draft_pass = structural_pass and len(provisional_rows) > 0 and len(uncertain_rows) > 0
    pilot_verified_pass = (
        structural_pass
        and len(pilot_verified) > 0
        and len(pilot_unreviewed) == 0
        and len(pilot_uncertain) == 0
        and len(open_pilot_uncertain) == 0
    )
    exported_scope_pass = (
        pilot_verified_pass
        and len(verified_in_status) > 0
        and len(unreviewed_in_status) == 0
        and len(uncertain_in_status) == 0
        and len(open_uncertain) == 0
    )
    full_gt_pass = exported_scope_pass and covers_all_video_frames

    if not covers_all_video_frames:
        warnings.append(
            f"Exported Ground Truth covers {len(observed_status_frames)}/{frame_count} frames (pilot {p_start}-{p_end}); "
            "full-video GT across all frames is not complete. Filter tracker predictions to the pilot frame range before calling evaluation.py."
        )

    if full_gt_pass:
        acceptance_state = "FULL_GT_PASS"
    elif exported_scope_pass:
        acceptance_state = "PILOT_VERIFIED_PASS__EXPORTED_SCOPE_PASS"
    elif pilot_verified_pass:
        acceptance_state = "PILOT_VERIFIED_PASS"
    elif auto_draft_pass:
        acceptance_state = "AUTO_DRAFT_PASS__REVIEW_REQUIRED"
    else:
        acceptance_state = "BLOCKED_OR_FAILED"

    return {
        "structural_pass": structural_pass,
        "auto_draft_pass": auto_draft_pass,
        "pilot_verified_pass": pilot_verified_pass,
        "exported_scope_pass": exported_scope_pass,
        "full_gt_pass": full_gt_pass,
        "acceptance_state": acceptance_state,
        "counts": {
            "frames_total": frame_count,
            "frames_annotated": len(observed_status_frames),
            "provisional_rows_total": len(provisional_rows),
            "provisional_tracks_total": len({r["object_id"] for r in provisional_rows}),
            "pilot_provisional_rows": len(pilot_rows),
            "pilot_provisional_tracks": len({r["object_id"] for r in pilot_rows}),
            "verified_rows_total": len(verified_in_status),
            "unreviewed_rows_total": len(unreviewed_in_status),
            "uncertain_rows_total": len(uncertain_in_status),
            "open_uncertain_cases_total": len(open_uncertain),
            "open_uncertain_cases_pilot": len(open_pilot_uncertain),
        },
        "structural_errors": structural_errors,
        "scientific_blockers": scientific_blockers,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--frames", type=Path, default=DEFAULT_FRAMES)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    result = validate_ground_truth_bundle(args.output_dir, args.frames, args.manifest)
    print(json.dumps(result, indent=2))
    if not result["structural_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

