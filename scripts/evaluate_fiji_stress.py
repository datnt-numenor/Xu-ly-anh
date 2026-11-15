"""F4: score existing Fiji and Python seed0/fixed tracking against P3 GT.

Only reads source artifacts; writes a new F4 output directory. Metrics come
directly from evaluation.score_with_identity, not from this script.
"""
import argparse
import csv
import hashlib
import json
import math
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation import METRICS, score, score_with_identity  # noqa: E402
from score_trackmate import read_tracks, read_truth  # noqa: E402

SCENARIOS = ("separate", "occlusion", "overlap", "turn", "illumination")
PAIRS = (("nearest", "nearest"), ("lap", "hungarian"), ("kalman", "kalman"))
FRAMES = 80
GATE = 8.0
DETECTOR_GATE = 2.0


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def checked_truth(path):
    rows = read_truth(path)
    assert len(rows) == 240, (path, len(rows))
    assert Counter(frame for frame, *_ in rows) == Counter({i: 3 for i in range(FRAMES)})
    assert len({(r[0], r[1]) for r in rows}) == len(rows)
    assert all(r[4] in (0, 1) and 0 <= r[2] < 320 and 0 <= r[3] < 180 for r in rows)
    return rows


def checked_tracks(path):
    rows = read_tracks(path)
    assert rows, path
    assert all(0 <= f < FRAMES and math.isfinite(x) and math.isfinite(y)
               and 0 <= x < 320 and 0 <= y < 180 for f, _, x, y in rows)
    assert len({(f, tid) for f, tid, *_ in rows}) == len(rows)
    return rows


def xml_detections(path):
    """Extract filtered, visible TrackMate spots, independent of tracker IDs."""
    root = ET.parse(path).getroot()
    assert root.tag == "TrackMate" and root.get("version") == "8.1.6", path
    spots = root.find("./Model/AllSpots")
    assert spots is not None
    frames = spots.findall("SpotsInFrame")
    assert {int(node.get("frame")) for node in frames} == set(range(FRAMES))
    result = []
    for node in frames:
        frame = int(node.get("frame"))
        for local_id, spot in enumerate(node.findall("Spot")):
            if spot.get("VISIBILITY") != "1":
                continue
            x, y = float(spot.get("POSITION_X")), float(spot.get("POSITION_Y"))
            assert math.isfinite(x) and math.isfinite(y) and 0 <= x < 320 and 0 <= y < 180
            result.append((frame, local_id, x, y))
    return result


def python_detections(source):
    import numpy as np
    from PIL import Image
    from tracking import detect
    paths = sorted(source.glob("frame_*.png"))
    assert [p.name for p in paths] == [f"frame_{i:03d}.png" for i in range(FRAMES)]
    rows = []
    for frame, path in enumerate(paths):
        with Image.open(path) as image:
            assert image.mode == "L" and image.size == (320, 180)
            points = detect(np.asarray(image), 110, 35, 240)[1]
        rows.extend((frame, i, float(x), float(y)) for i, (x, y) in enumerate(points))
    return rows


def metric_row(scenario, method, truth, observations, path):
    values, matches = score_with_identity(truth, observations, GATE)
    assert len(values) == len(METRICS)
    visible = sum(r[4] for r in truth)
    # This equality proves empty observation frames contribute to misses.
    assert values[0] + values[1] == visible
    assert values[0] + values[2] == len(observations)
    return {"scenario": scenario, "method": method, "source": str(path.relative_to(ROOT)),
            "source_sha256": digest(path), "gt_visible": visible, "gt_frames": FRAMES,
            "observation_rows": len(observations),
            "observation_frames": len({r[0] for r in observations}),
            **dict(zip(METRICS, values))}, matches


def figure(rows, path, metric, ylabel):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)
    for ax, (fiji_method, python_method) in zip(axes, PAIRS):
        subset = [r for r in rows if r["fiji_method"] == fiji_method]
        assert [r["scenario"] for r in subset] == list(SCENARIOS)
        x = list(range(len(SCENARIOS)))
        ax.bar([i - 0.18 for i in x], [float(r[f"fiji_{metric}"]) for r in subset],
               width=0.36, label="Fiji")
        ax.bar([i + 0.18 for i in x], [float(r[f"python_{metric}"]) for r in subset],
               width=0.36, label="Python")
        ax.set_xticks(x, SCENARIOS, rotation=35, ha="right")
        ax.set_title(f"Fiji {fiji_method} / Python {python_method}")
        ax.grid(axis="y", alpha=0.2)
    axes[0].set_ylabel(ylabel)
    axes[0].legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/person1/f4")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"F4 output is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "detector_comparison").mkdir()
    (out / "figures").mkdir()
    fiji_rows, python_rows, comparison, agreement_rows = [], [], [], []
    inputs = {}
    source_manifest = ROOT / "output/person1/stress_manifest.csv"
    # Reuse the P3 manifest checker; no synthetic frames or GT are generated.
    from run_fiji_stress import verify_source_manifest, validate_scenario
    for scenario in SCENARIOS:
        seed_name = f"{scenario}_seed0"
        verify_source_manifest(source_manifest, seed_name)
        fiji_dir = ROOT / "output/person1/fiji_stress" / seed_name
        validate_scenario(fiji_dir, seed_name, "8.1.6")
        truth_path = ROOT / "data/stress" / f"{seed_name}_truth.csv"
        truth = checked_truth(truth_path)
        inputs[str(truth_path.relative_to(ROOT))] = digest(truth_path)
        for fiji_method, python_method in PAIRS:
            fiji_path = fiji_dir / f"{seed_name}_{fiji_method}.csv"
            fiji_xml_path = fiji_dir / f"{seed_name}_{fiji_method}.xml"
            python_path = (ROOT / "output/person1/stress_seed0/details" /
                           f"{scenario}_fixed_{python_method}.csv")
            fiji, python = checked_tracks(fiji_path), checked_tracks(python_path)
            fr, _ = metric_row(scenario, fiji_method, truth, fiji, fiji_path)
            pr, _ = metric_row(scenario, python_method, truth, python, python_path)
            fiji_rows.append(fr)
            python_rows.append(pr)
            inputs[fr["source"]], inputs[pr["source"]] = fr["source_sha256"], pr["source_sha256"]
            inputs[str(fiji_xml_path.relative_to(ROOT))] = digest(fiji_xml_path)
            row = {"scenario": scenario, "fiji_method": fiji_method,
                   "python_method": python_method, "gt_visible": fr["gt_visible"]}
            for key in METRICS:
                row[f"fiji_{key}"] = fr[key]
                row[f"python_{key}"] = pr[key]
                if isinstance(fr[key], (int, float)) and isinstance(pr[key], (int, float)):
                    row[f"delta_{key}"] = round(fr[key] - pr[key], 4)
                else:
                    row[f"delta_{key}"] = ""
            comparison.append(row)
        # TrackMate XML spots supply detector positions, without track IDs.
        xml_path = fiji_dir / f"{seed_name}_nearest.xml"
        fj_spots = xml_detections(xml_path)
        py_spots = python_detections(ROOT / "data/stress" / seed_name)
        agreement, _ = score([(f, i, x, y, 1) for f, i, x, y in fj_spots],
                             py_spots, DETECTOR_GATE)
        assert agreement[0] + agreement[1] == len(fj_spots)
        assert agreement[0] + agreement[2] == len(py_spots)
        agreement_rows.append({"scenario": scenario, "gate_px": DETECTOR_GATE,
            "fiji_spots": len(fj_spots), "python_spots": len(py_spots),
            "matched": agreement[0], "unmatched_fiji": agreement[1],
            "unmatched_python": agreement[2],
            "matched_centroid_rmse_px": agreement[5]})
        inputs[str(xml_path.relative_to(ROOT))] = digest(xml_path)
    fields = ("scenario", "method", "source", "source_sha256", "gt_visible", "gt_frames",
              "observation_rows", "observation_frames", *METRICS)
    write_csv(out / "fiji_metrics.csv", fields, fiji_rows)
    write_csv(out / "python_seed0_fixed_metrics.csv", fields, python_rows)
    compare_fields = ("scenario", "fiji_method", "python_method", "gt_visible",
                      *(name for key in METRICS for name in
                        (f"fiji_{key}", f"python_{key}", f"delta_{key}")))
    write_csv(out / "comparison.csv", compare_fields, comparison)
    write_csv(out / "detector_comparison/summary.csv", tuple(agreement_rows[0]), agreement_rows)
    with (ROOT / "output/person1/stress_seed0/per_run.csv").open(
            newline="", encoding="utf-8") as stream:
        p2_legacy = {(row["scenario"], row["method"]): row
                     for row in csv.DictReader(stream)
                     if row["seed"] == "0" and row["detector"] == "fixed"}
    assert len(p2_legacy) == 15
    for row in python_rows:
        prior = p2_legacy[row["scenario"], row["method"]]
        for key in METRICS[:6]:
            assert str(row[key]) == prior[key], (row["scenario"], row["method"], key)
    for metric, label in (("mota", "MOTA (repo definition)"),
                          ("idf1", "IDF1 (repo definition)"),
                          ("missed", "Missed visible GT observations"),
                          ("id_switches", "ID switches (repo definition)")):
        figure(comparison, out / "figures" / f"{metric}.png", metric, label)
    for source in ("evaluation.py", "score_trackmate.py", "TrackMate_Nhom9.groovy",
                   "output/person1/stress_seed0/per_run.csv", "output/person1/stress_manifest.csv"):
        inputs[source] = digest(ROOT / source)
    validation = {"status": "PASS", "gate_px": GATE, "detector_agreement_gate_px": DETECTOR_GATE,
                  "scenarios": list(SCENARIOS), "frames_per_scenario": FRAMES,
                  "fiji_rows": len(fiji_rows), "python_rows": len(python_rows),
                  "comparison_rows": len(comparison), "agreement_rows": len(agreement_rows),
                  "source_sha256": inputs,
                  "checks": ["P3 manifest SHA256", "F3 CSV/XML settings and bounds",
                             "GT 80-frame coverage", "metric count identities",
                             "P2 legacy metrics agree 15/15", "CSV/figure source consistency"]}
    (out / "validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    report(comparison, agreement_rows, out)
    print(f"F4 PASS: {len(fiji_rows)} Fiji + {len(python_rows)} Python rows; {out}")


def report(rows, agreement, out):
    lines = ["# F4 — Fiji versus Python on P3 seed0", "",
             "**PASS: 15 Fiji outputs and 15 Python fixed=110 outputs scored on the complete 80-frame GT per scenario, with gate 8 px.**", "",
             "All numbers below come from `evaluation.score_with_identity` and the original CSVs. These are repository metric definitions, not a claim of MOTChallenge compliance. `visible=0` GT is excluded from matching. Empty prediction frames remain in the GT domain.", "",
             "| Scenario | Fiji / Python | Fiji matched/missed/FP/switch | Python matched/missed/FP/switch | Fiji MOTA/IDF1 | Python MOTA/IDF1 |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        def quartet(prefix):
            return "/".join(str(r[f"{prefix}_{k}"]) for k in
                            ("matched", "missed", "false_positive", "id_switches"))
        lines.append(f"| {r['scenario']} | {r['fiji_method']} / {r['python_method']} | {quartet('fiji')} | {quartet('python')} | {r['fiji_mota']}/{r['fiji_idf1']} | {r['python_mota']}/{r['python_idf1']} |")
    lines += ["", "## Detector agreement", "",
              "Fiji filtered visible XML spots were compared to Python fixed=110 detector centroids on the same 400 PNGs at 2 px. Track IDs are ignored. This is detector agreement, not accuracy against GT.", "",
              "| Scenario | Fiji / Python spots | Matched | Unmatched Fiji / Python | Matched centroid RMSE px |",
              "|---|---:|---:|---:|---:|"]
    for r in agreement:
        lines.append(f"| {r['scenario']} | {r['fiji_spots']} / {r['python_spots']} | {r['matched']} | {r['unmatched_fiji']} / {r['unmatched_python']} | {r['matched_centroid_rmse_px'] or 'N/A'} |")
    lines += ["", "## Interpretation and traceability", "",
              "- Nearest is compared with nearest and Kalman with Kalman. Fiji Simple LAP and Python Hungarian are different tracking algorithms; their rows are contextual comparisons, not algorithm equivalence.",
              "- Occlusion contains GT object 1 with `visible=0` at frames 36–39; these four rows are excluded from visible GT. Fiji nearest has one ID switch after occlusion while Python nearest has zero. Overlap contains two GT centers even when image regions merge; both systems miss six centers at frames 38–41. Fiji nearest has three ID switches versus Python nearest's two.",
              "- Illumination under threshold 110 has no Fiji observations in frames 0–11 or 65–79; those frames still contribute visible GT misses. Fiji has 147 matches, 93 misses and 382 false positives per tracker; Python has 160, 80 and 337. High FP counts reflect extra threshold blobs as lighting changes. Neither pipeline performs well on this scenario under the fixed threshold.",
              "- Fiji and Python differ in detector processing and tracker linking. Detector agreement helps identify centroid differences but does not isolate tracker behavior because shared detection inputs were not enforced.",
              "- RMSE is defined only for matched pairs. Empty values in CSV mean N/A; they are not zero. Full metric definitions and input hashes are in `evaluation.py` and `validation.json`.",
              "- The six P2 legacy metrics were independently cross-checked against `output/person1/stress_seed0/per_run.csv` for all 15 Python rows. Figures in `figures/` plot the exact `comparison.csv` values for MOTA, IDF1, missed and ID switches. CSVs and XMLs under F3 and P2 were read only.", "",
              "## Reproduce", "",
              "From the repo root, run `python scripts/evaluate_fiji_stress.py --output output/person1/f4_rerun` to avoid replacing these artifacts. No P7 was run and no commit was made.", ""]
    (out / "f4_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
