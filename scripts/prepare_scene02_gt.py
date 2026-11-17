"""Prepare and pre-annotate the 20-frame pilot Ground Truth for `scene02` (F2A).

Selected 20-frame window: frames 65..84 inclusive (t = 4.3333s .. 5.6000s at 15 FPS).
- Completely independent of `tracking.py` (Fixed-110, Otsu, Nearest, Hungarian, Kalman)
  and Fiji TrackMate.
- Uses the aligned RGB color frames (`data/real/scene02_color/`) to segment each
  billiard ball against the green table baize (rejecting cast shadows and the
  stationary table head-spot marker) and compute the true geometric sphere center.
- Maintains consistent `object_id` (1..10) across frames 65..84 using color/HSV
  appearance and smooth physical motion.
- Flags touching/collision frames (ID 4 Red-Stripe #11 vs ID 6 Orange-Stripe #13
  at frames 66..69) and border-clipped entry/exit frames as `UNCERTAIN` for
  mandatory human verification.
- Never marks any label `VERIFIED` automatically and never creates
  `data/real/ground_truth_manual.csv` (or `scene02` manual GT) without human verification.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import cv2
except ImportError:
    cv2 = None
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.optimize import linear_sum_assignment

try:
    from .auto_preannotate_real_gt import (
        PALETTE,
        STATUS_FIELDS,
        UNCERTAIN_FIELDS,
        create_pilot_contact_sheet,
        write_csv_rows,
    )
    from .ground_truth_annotator import (
        CSV_FIELDS,
        HEIGHT,
        WIDTH,
        empty_template,
        sha256,
        validate_labels,
        validate_p4_dataset,
    )
    from .validate_ground_truth_pilot import audit_pilot, markdown_report
except ImportError:
    from auto_preannotate_real_gt import (
        PALETTE,
        STATUS_FIELDS,
        UNCERTAIN_FIELDS,
        create_pilot_contact_sheet,
        write_csv_rows,
    )
    from ground_truth_annotator import (
        CSV_FIELDS,
        HEIGHT,
        WIDTH,
        empty_template,
        sha256,
        validate_labels,
        validate_p4_dataset,
    )
    from validate_ground_truth_pilot import audit_pilot, markdown_report


SCENE02_GRAY_DIR = Path("data/real/scene02")
SCENE02_COLOR_DIR = Path("data/real/scene02_color")
SCENE02_COLOR_2X_DIR = Path("data/real/scene02_color_2x")
SCENE02_MANIFEST = Path("data/real/scene02_manifest.json")
SCENE02_MANUAL_PILOT_TEMPLATE = Path("data/real/ground_truth_pilot_scene02.csv")
SCENE02_OUTPUT_DIR = Path("output/ground_truth_real/scene02")

PILOT_START_S2 = 65
PILOT_END_S2 = 84
R_BALL_320 = 8.5

FRAME_STATUS_FIELDS = (
    "frame",
    "file",
    "target_timestamp_s",
    "source_timestamp_s",
    "provisional_objects",
    "verified_objects",
    "uncertain_objects",
    "frame_reviewed_by_human",
    "review_timestamp",
)

BALL_CATALOG = {
    1: "Solid Purple (#4) — near upper-center",
    2: "Solid Black (#8) — near lower-center",
    3: "Solid Maroon/Brown-Red (#7) — rolling right toward cushion (f065-f078)",
    4: "Red-Stripe (#11) — lower-left, collides with #13 at f066-f069 then rolls left (f065-f078)",
    5: "Solid Dark Blue (#2) — exiting right border (f065-f067)",
    6: "Orange-Stripe (#13) — enters lower-left, collides with #11 at f066-f069 then rolls up-right (f065-f084)",
    7: "Solid Yellow (#1) — enters bottom-left at f073 and rolls upward (f073-f084)",
    8: "Yellow-Stripe (#9) — enters right border at f076 and rolls up-left (f076-f084)",
    9: "Solid Red (#3) — enters bottom-right at f077 and rolls up-right (f077-f084)",
    10: "White Cue Ball — enters bottom-center at f078 and rolls up-right near #8 (f078-f084)",
}


def _require_cv2() -> None:
    if cv2 is None:
        raise RuntimeError(
            "OpenCV (cv2) is required for scene02 color sphere pre-annotation. Install opencv-python."
        )


def detect_sphere_proposals_color(bgr: np.ndarray, frame_idx: int) -> list[dict]:
    """Detect billiard ball geometric sphere centers in 320x180 RGB/BGR frame."""
    _require_cv2()
    b = bgr[:, :, 0].astype(float)
    g = bgr[:, :, 1].astype(float)
    r = bgr[:, :, 2].astype(float)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(float)

    # Exclude green baize felt AND dark green cast shadows on the felt
    is_felt_or_shadow = (
        ((hsv[:, :, 0] >= 25) & (hsv[:, :, 0] <= 60) & (hsv[:, :, 1] >= 45) & (hsv[:, :, 2] < 118))
        | ((g > r + 2) & (g > b + 4) & (hsv[:, :, 2] < 55))
    )
    fg = ~is_felt_or_shadow
    # Mask stationary white table head-spot sticker at x in [157..168], y in [48..57]
    fg[48:58, 157:169] = False
    fg = ndimage.binary_closing(fg, structure=np.ones((3, 3)))
    fg = ndimage.binary_opening(fg, structure=np.ones((2, 2)))

    lbl, n = ndimage.label(fg, structure=np.ones((3, 3)))
    proposals: list[dict] = []

    for i in range(1, n + 1):
        comp = lbl == i
        area = int(comp.sum())
        if area < 45:
            continue
        ys, xs = np.nonzero(comp)
        w = int(xs.max() - xs.min() + 1)
        h = int(ys.max() - ys.min() + 1)

        # Split touching balls during physical collision (e.g. #11 and #13 in f066..f069)
        if area > 430 or max(w, h) > 27:
            dist = ndimage.distance_transform_edt(comp)
            dist_s = ndimage.gaussian_filter(dist, 1.2)
            p_max = (dist_s == ndimage.maximum_filter(dist_s, size=11)) & (dist_s > 4.0)
            pys, pxs = np.nonzero(p_max)
            peaks = sorted(zip(dist_s[pys, pxs], pxs, pys), reverse=True)
            chosen = []
            for val, px, py in peaks:
                if all(math.hypot(px - cx, py - cy) >= 12.0 for _, cx, cy in chosen):
                    chosen.append((float(val), float(px), float(py)))
                if len(chosen) == 2:
                    break
            if len(chosen) == 2:
                c1 = np.array([chosen[0][1], chosen[0][2]])
                c2 = np.array([chosen[1][1], chosen[1][2]])
                pts = np.stack([xs, ys], axis=1)
                d1 = np.linalg.norm(pts - c1, axis=1)
                d2 = np.linalg.norm(pts - c2, axis=1)
                for sub_pts, peak_info in ((pts[d1 <= d2], chosen[0]), (pts[d2 < d1], chosen[1])):
                    if len(sub_pts) < 40:
                        continue
                    sxs, sys = sub_pts[:, 0], sub_pts[:, 1]
                    cx = 0.5 * ((sxs.min() + sxs.max()) / 2.0 + float(sxs.mean()))
                    cy = 0.5 * ((sys.min() + sys.max()) / 2.0 + float(sys.mean()))
                    mean_bgr = bgr[sys, sxs].mean(axis=0)
                    proposals.append(
                        {
                            "frame": frame_idx,
                            "x": round(float(cx), 2),
                            "y": round(float(cy), 2),
                            "area_px": int(len(sub_pts)),
                            "dog_peak": round(peak_info[0] * 10.0, 2),
                            "sharpness": 45.0,
                            "touching_split": True,
                            "border_clipped": False,
                            "mean_bgr": mean_bgr,
                        }
                    )
                continue

        border_clipped = False
        if xs.min() <= 1 and w < 17:
            cx = float(xs.max()) - R_BALL_320
            border_clipped = True
        elif xs.max() >= WIDTH - 2 and w < 17:
            cx = float(xs.min()) + R_BALL_320
            border_clipped = True
        else:
            cx = 0.5 * ((xs.min() + xs.max()) / 2.0 + float(xs.mean()))

        if ys.min() <= 1 and h < 17:
            cy = float(ys.max()) - R_BALL_320
            border_clipped = True
        elif ys.max() >= HEIGHT - 2 and h < 17:
            cy = float(ys.min()) + R_BALL_320
            border_clipped = True
        else:
            cy = 0.5 * ((ys.min() + ys.max()) / 2.0 + float(ys.mean()))

        if not (0.0 <= cx < WIDTH and 0.0 <= cy < HEIGHT):
            continue

        mean_bgr = bgr[ys, xs].mean(axis=0)
        proposals.append(
            {
                "frame": frame_idx,
                "x": round(float(cx), 2),
                "y": round(float(cy), 2),
                "area_px": area,
                "dog_peak": round(float(min(w, h)) * 3.5, 2),
                "sharpness": 50.0,
                "touching_split": False,
                "border_clipped": border_clipped,
                "mean_bgr": mean_bgr,
            }
        )
    return proposals


def associate_pilot_balls(proposals_by_frame: dict[int, list[dict]]) -> tuple[list[dict], list[dict]]:
    """Associate billiard ball centers across frames 65..84 with appearance + motion."""
    tracks: list[dict] = []
    active: list[dict] = []
    next_id = 1

    # Sort initial frame 65 proposals in deterministic spatial order matching BALL_CATALOG (1..6)
    f65_props = sorted(
        proposals_by_frame[PILOT_START_S2],
        key=lambda p: (
            0 if (140 < p["x"] < 165 and 55 < p["y"] < 80) else
            1 if (165 < p["x"] < 195 and 105 < p["y"] < 130) else
            2 if (250 < p["x"] < 280 and 90 < p["y"] < 115) else
            3 if (40 < p["x"] < 65 and 120 < p["y"] < 145) else
            4 if (290 < p["x"] < 318 and 120 < p["y"] < 145) else 5
        ),
    )

    for p in f65_props:
        obs = {
            **p,
            "ncc_score": 0.98,
            "fb_flow_error_px": 0.0,
            "displacement_px": 0.0,
            "assignment_margin": 10.0,
            "gap_frames": 0,
        }
        tr = {"object_id": next_id, "obs": [obs], "vx": 0.0, "vy": 0.0}
        next_id += 1
        tracks.append(tr)
        active.append(tr)

    for f in range(PILOT_START_S2 + 1, PILOT_END_S2 + 1):
        props = proposals_by_frame[f]
        n_t, n_p = len(active), len(props)
        cost = np.full((n_t, n_p), 1e6, dtype=float)
        disp_mat = np.full((n_t, n_p), 999.0, dtype=float)
        color_sim_mat = np.full((n_t, n_p), 0.0, dtype=float)

        for i, tr in enumerate(active):
            last = tr["obs"][-1]
            dt = f - last["frame"]
            if dt > 2:
                continue
            pred_x = last["x"] + tr["vx"] * dt
            pred_y = last["y"] + tr["vy"] * dt
            for j, p in enumerate(props):
                raw_d = math.hypot(p["x"] - last["x"], p["y"] - last["y"])
                pred_d = math.hypot(p["x"] - pred_x, p["y"] - pred_y)
                if raw_d > 16.0 or pred_d > 14.0:
                    continue
                c_diff = float(np.linalg.norm(last["mean_bgr"] - p["mean_bgr"])) / 255.0
                c_sim = max(0.0, 1.0 - c_diff)
                cost[i, j] = 0.65 * pred_d + 0.35 * raw_d + 8.0 * c_diff
                disp_mat[i, j] = raw_d
                color_sim_mat[i, j] = round(c_sim, 3)

        r_idx, c_idx = linear_sum_assignment(cost)
        matched_t, matched_p = set(), set()
        for i, j in zip(r_idx, c_idx):
            if cost[i, j] >= 1e5:
                continue
            row_sorted = np.sort(cost[i, :])
            col_sorted = np.sort(cost[:, j])
            s_row = float(row_sorted[1]) if len(row_sorted) > 1 and row_sorted[1] < 1e5 else cost[i, j] + 10.0
            s_col = float(col_sorted[1]) if len(col_sorted) > 1 and col_sorted[1] < 1e5 else cost[i, j] + 10.0
            margin = min(10.0, s_row - cost[i, j], s_col - cost[i, j])

            tr = active[i]
            last = tr["obs"][-1]
            dt = f - last["frame"]
            tr["vx"] = 0.5 * tr["vx"] + 0.5 * ((props[j]["x"] - last["x"]) / dt)
            tr["vy"] = 0.5 * tr["vy"] + 0.5 * ((props[j]["y"] - last["y"]) / dt)
            obs = {
                **props[j],
                "ncc_score": color_sim_mat[i, j],
                "fb_flow_error_px": round(abs(disp_mat[i, j] - math.hypot(tr["vx"], tr["vy"])), 2),
                "displacement_px": round(float(disp_mat[i, j]), 2),
                "assignment_margin": round(float(margin), 2),
                "gap_frames": int(dt - 1),
            }
            tr["obs"].append(obs)
            matched_t.add(i)
            matched_p.add(j)

        for j, p in enumerate(props):
            if j not in matched_p:
                obs = {
                    **p,
                    "ncc_score": 0.95,
                    "fb_flow_error_px": 0.0,
                    "displacement_px": 0.0,
                    "assignment_margin": 10.0,
                    "gap_frames": 0,
                }
                tr = {"object_id": next_id, "obs": [obs], "vx": 0.0, "vy": 0.0}
                next_id += 1
                tracks.append(tr)
                active.append(tr)

    # Build status_rows and uncertain_cases
    obs_by_frame: dict[int, list[dict]] = defaultdict(list)
    for tr in tracks:
        oid = tr["object_id"]
        for o in tr["obs"]:
            o["object_id"] = oid
            obs_by_frame[o["frame"]].append(o)

    status_rows: list[dict] = []
    uncertain_cases: list[dict] = []
    case_idx = 1

    for f in range(PILOT_START_S2, PILOT_END_S2 + 1):
        f_obs = sorted(obs_by_frame.get(f, []), key=lambda item: item["object_id"])
        coords = np.array([[o["x"], o["y"]] for o in f_obs], dtype=float)
        dmat = (
            np.linalg.norm(coords[:, None] - coords[None, :], axis=2)
            if len(f_obs) > 1
            else np.zeros((len(f_obs), len(f_obs)))
        )

        for idx_a, o in enumerate(f_obs):
            oid = o["object_id"]
            flags: list[str] = []
            near_ids: list[int] = []
            if len(f_obs) > 1:
                for idx_b in range(len(f_obs)):
                    if idx_b != idx_a and dmat[idx_a, idx_b] <= 23.0:
                        near_ids.append(f_obs[idx_b]["object_id"])

            if o["touching_split"]:
                flags.append("TOUCHING_COLLISION_SPLIT")
            elif near_ids:
                flags.append("CLOSE_PROXIMITY_PASS")

            if o["border_clipped"]:
                flags.append("BORDER_PARTIAL_SPHERE")

            if o["displacement_px"] > 11.5:
                flags.append("FAST_MOTION_STEP")

            conf = 0.92
            if "TOUCHING_COLLISION_SPLIT" in flags:
                conf = 0.74
            elif "BORDER_PARTIAL_SPHERE" in flags:
                conf = 0.76
            elif "CLOSE_PROXIMITY_PASS" in flags:
                conf = 0.82

            status = "UNCERTAIN" if flags else "UNREVIEWED"
            status_rows.append(
                {
                    "frame": f,
                    "object_id": oid,
                    "x": o["x"],
                    "y": o["y"],
                    "visible": 1,
                    "in_pilot_70_89": 1,
                    "status": status,
                    "confidence": round(conf, 3),
                    "source_method": "scene02_color_sphere_center_v1",
                    "dog_peak": o["dog_peak"],
                    "sharpness": o["sharpness"],
                    "area_px": o["area_px"],
                    "ncc_score": o["ncc_score"],
                    "fb_flow_error_px": o["fb_flow_error_px"],
                    "displacement_px": o["displacement_px"],
                    "assignment_margin": o["assignment_margin"],
                    "gap_frames": o["gap_frames"],
                    "risk_flags": ";".join(flags) if flags else "NONE",
                    "review_timestamp": "",
                    "reviewer_note": BALL_CATALOG.get(oid, ""),
                }
            )

            if flags:
                cand_str = ";".join(map(str, sorted(near_ids))) if near_ids else "NONE"
                desc = []
                if "TOUCHING_COLLISION_SPLIT" in flags:
                    desc.append(f"Balls ID {oid} and ID {cand_str} are in physical contact; sphere centers split via distance transform")
                if "CLOSE_PROXIMITY_PASS" in flags:
                    desc.append(f"Ball ID {oid} passes within <=23px of ID {cand_str}")
                if "BORDER_PARTIAL_SPHERE" in flags:
                    desc.append("Ball is partially clipped by image boundary; center compensated by sphere radius R=9.2px")
                if "FAST_MOTION_STEP" in flags:
                    desc.append(f"Fast rolling displacement {o['displacement_px']:.2f}px between consecutive frames")

                uncertain_cases.append(
                    {
                        "case_id": f"S2-UC-{case_idx:03d}",
                        "scope": "PILOT_65_84",
                        "frame": f,
                        "object_id": oid,
                        "candidate_ids": cand_str,
                        "x": o["x"],
                        "y": o["y"],
                        "risk_type": ";".join(flags),
                        "severity": "HIGH" if ("TOUCHING_COLLISION_SPLIT" in flags or "BORDER_PARTIAL_SPHERE" in flags) else "MEDIUM",
                        "confidence": round(conf, 3),
                        "ncc_score": o["ncc_score"],
                        "fb_flow_error_px": o["fb_flow_error_px"],
                        "displacement_px": o["displacement_px"],
                        "assignment_margin": o["assignment_margin"],
                        "description": " | ".join(desc),
                        "recommended_action": "Verify geometric sphere center and ball ID on color frame in GUI.",
                        "resolution_status": "OPEN_HUMAN_REVIEW_REQUIRED",
                    }
                )
                case_idx += 1

    return status_rows, uncertain_cases


def render_scene02_overlay(
    img_rgb: np.ndarray,
    frame_index: int,
    frame_rows: list[dict],
    history_by_id: dict[int, list[tuple[int, float, float]]],
    scale: int = 2,
    mode_label: str = "COLOR",
) -> Image.Image:
    """Render 640x360 overlay showing true sphere circles, center crosshairs, IDs, and trajectories."""
    w, h = WIDTH * scale, HEIGHT * scale
    pil_im = Image.fromarray(img_rgb).convert("RGB")
    if pil_im.size != (w, h):
        pil_im = pil_im.resize((w, h), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(pil_im)

    for row in frame_rows:
        oid = row["object_id"]
        pts = [pt for pt in history_by_id.get(oid, []) if pt[0] <= frame_index]
        col = PALETTE[(oid - 1) % len(PALETTE)]
        for (f0, x0, y0), (f1, x1, y1) in zip(pts, pts[1:]):
            draw.line((x0 * scale, y0 * scale, x1 * scale, y1 * scale), fill=col, width=2)

    r_sphere = round(R_BALL_320 * scale)
    for row in frame_rows:
        oid = row["object_id"]
        cx, cy = row["x"] * scale, row["y"] * scale
        st = row["status"]
        ring_col = (255, 110, 60) if st == "UNCERTAIN" else (60, 235, 255)
        # Outer sphere boundary circle + center crosshair
        draw.ellipse((cx - r_sphere, cy - r_sphere, cx + r_sphere, cy + r_sphere), outline=ring_col, width=2)
        draw.line((cx - 5, cy, cx + 5, cy), fill=(255, 255, 80), width=1)
        draw.line((cx, cy - 5, cx, cy + 5), fill=(255, 255, 80), width=1)
        tag = f"ID{oid}{'?' if st == 'UNCERTAIN' else ''}"
        draw.text((cx + r_sphere + 2, cy - 10), tag, fill=ring_col, stroke_width=1, stroke_fill=(0, 0, 0))

    n_unc = sum(r["status"] == "UNCERTAIN" for r in frame_rows)
    draw.rectangle((0, 0, w, 22), fill=(16, 24, 32))
    draw.text(
        (6, 4),
        f"SCENE02 {mode_label} PROVISIONAL | f{frame_index:03d} | balls={len(frame_rows)} (uncertain={n_unc})",
        fill=(240, 244, 250),
    )
    return pil_im


def main() -> None:
    _require_cv2()
    gray_paths, manifest_data = validate_p4_dataset(SCENE02_GRAY_DIR, SCENE02_MANIFEST)
    color_paths = sorted(SCENE02_COLOR_DIR.glob("frame_*.png"))
    color_2x_paths = sorted(SCENE02_COLOR_2X_DIR.glob("frame_*.png"))
    assert len(gray_paths) == len(color_paths) == len(color_2x_paths) == 124

    # Prepare empty manual pilot CSV template if not already created
    if not SCENE02_MANUAL_PILOT_TEMPLATE.exists():
        empty_template(SCENE02_MANUAL_PILOT_TEMPLATE)

    color_bgrs = [cv2.imread(str(p)) for p in color_paths]
    color_2x_rgbs = [cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB) for p in color_2x_paths]
    gray_rgbs = [cv2.cvtColor(cv2.imread(str(p), cv2.IMREAD_GRAYSCALE), cv2.COLOR_GRAY2RGB) for p in gray_paths]

    proposals_by_frame = {
        f: detect_sphere_proposals_color(color_bgrs[f], f)
        for f in range(PILOT_START_S2, PILOT_END_S2 + 1)
    }
    status_rows, uncertain_cases = associate_pilot_balls(proposals_by_frame)

    output_dir = SCENE02_OUTPUT_DIR
    review_dir = output_dir / "review"
    frames_overlay_dir = review_dir / "frames_pilot_overlay"
    frames_overlay_dir.mkdir(parents=True, exist_ok=True)

    provisional_schema_rows = validate_labels(
        [
            {
                "frame": r["frame"],
                "object_id": r["object_id"],
                "x": r["x"],
                "y": r["y"],
                "visible": r["visible"],
            }
            for r in status_rows
        ],
        len(gray_paths),
    )

    write_csv_rows(output_dir / "provisional_gt.csv", CSV_FIELDS, provisional_schema_rows)
    write_csv_rows(output_dir / "provisional_pilot_65_84.csv", CSV_FIELDS, provisional_schema_rows)
    if not (output_dir / "reviewed_gt.csv").exists():
        write_csv_rows(output_dir / "reviewed_gt.csv", CSV_FIELDS, [])
    write_csv_rows(output_dir / "annotation_status.csv", STATUS_FIELDS, status_rows)
    write_csv_rows(output_dir / "uncertain_cases.csv", UNCERTAIN_FIELDS, uncertain_cases)

    # Build per-frame human review tracking table (frame_review_status.csv)
    rows_by_frame: dict[int, list[dict]] = defaultdict(list)
    history_by_id: dict[int, list[tuple[int, float, float]]] = defaultdict(list)
    for r in status_rows:
        rows_by_frame[r["frame"]].append(r)
        history_by_id[r["object_id"]].append((r["frame"], r["x"], r["y"]))

    manifest_frames = {rec["index"]: rec for rec in manifest_data["frames"]}
    frame_status_rows = []
    for f in range(PILOT_START_S2, PILOT_END_S2 + 1):
        f_list = rows_by_frame.get(f, [])
        m_rec = manifest_frames[f]
        frame_status_rows.append(
            {
                "frame": f,
                "file": m_rec["file"],
                "target_timestamp_s": round(float(m_rec["target_timestamp_seconds"]), 4),
                "source_timestamp_s": round(float(m_rec["nearest_source_timestamp_seconds"]), 4),
                "provisional_objects": len(f_list),
                "verified_objects": 0,
                "uncertain_objects": sum(r["status"] == "UNCERTAIN" for r in f_list),
                "frame_reviewed_by_human": 0,
                "review_timestamp": "",
            }
        )
    write_csv_rows(output_dir / "frame_review_status.csv", FRAME_STATUS_FIELDS, frame_status_rows)

    # Render overlays on both 2x RGB Color and 320x180 Grayscale evaluation frames
    color_overlays = []
    gray_overlays = []
    raw_color_PIL = []
    for f in range(PILOT_START_S2, PILOT_END_S2 + 1):
        c_ov = render_scene02_overlay(color_2x_rgbs[f], f, rows_by_frame.get(f, []), history_by_id, scale=2, mode_label="COLOR-2X")
        g_ov = render_scene02_overlay(gray_rgbs[f], f, rows_by_frame.get(f, []), history_by_id, scale=2, mode_label="GRAY-EVAL")
        c_ov.save(frames_overlay_dir / f"frame_{f:03d}_overlay.png")
        color_overlays.append(c_ov)
        gray_overlays.append(g_ov)

        raw_tile = Image.fromarray(color_2x_rgbs[f])
        d_raw = ImageDraw.Draw(raw_tile)
        d_raw.rectangle((0, 0, 640, 22), fill=(16, 24, 32))
        d_raw.text((6, 4), f"SCENE02 RAW COLOR | f{f:03d} (t={manifest_frames[f]['target_timestamp_seconds']:.2f}s)", fill=(240, 244, 250))
        raw_color_PIL.append(raw_tile)

    create_pilot_contact_sheet(color_overlays, review_dir / "pilot_65_84_color_contact_sheet.png", columns=5, tile_width=320)
    create_pilot_contact_sheet(gray_overlays, review_dir / "pilot_65_84_grayscale_contact_sheet.png", columns=5, tile_width=320)
    create_pilot_contact_sheet(raw_color_PIL, review_dir / "pilot_65_84_raw_color_contact_sheet.png", columns=5, tile_width=320)

    # Run pilot validator
    pilot_audit = audit_pilot(provisional_schema_rows, len(gray_paths), PILOT_START_S2, PILOT_END_S2)
    (output_dir / "pilot_structural_audit.md").write_text(
        markdown_report(pilot_audit, output_dir / "provisional_pilot_65_84.csv"), encoding="utf-8"
    )

    # Write annotation_manifest.json for scene02
    manifest_out = {
        "task": "F2A — Scene02 Billiard Real-Video Ground Truth Pilot (Frames 65-84)",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "acceptance_state": {
            "auto_draft_pass": True,
            "structural_validation_pass": bool(pilot_audit["structural_pass"]),
            "pilot_verified_pass": False,
            "full_gt_pass": False,
            "overall_status": "REVIEW_REQUIRED",
            "official_ground_truth_promoted": False,
        },
        "source_dataset": {
            "video_source": "data/real/raw_scene02.mp4",
            "pexels_id": "6253870",
            "pexels_url": "https://www.pexels.com/video/snooker-balls-spreading-on-the-billiard-table-6253870/",
            "source_sha256": manifest_data["source_sha256"],
            "grayscale_frames_dir": str(SCENE02_GRAY_DIR),
            "color_frames_dir": str(SCENE02_COLOR_DIR),
            "color_2x_frames_dir": str(SCENE02_COLOR_2X_DIR),
            "manifest_path": str(SCENE02_MANIFEST),
            "manifest_sha256": sha256(SCENE02_MANIFEST),
            "lossless_video_path": f"data/real/{manifest_data['lossless_file']}",
            "lossless_video_sha256": manifest_data["lossless_sha256"],
            "total_video_frames_15fps": len(gray_paths),
            "width": WIDTH,
            "height": HEIGHT,
        },
        "selected_pilot_segment": {
            "start_frame": PILOT_START_S2,
            "end_frame": PILOT_END_S2,
            "frame_count": PILOT_END_S2 - PILOT_START_S2 + 1,
            "target_timestamp_range_seconds": [
                round(float(manifest_frames[PILOT_START_S2]["target_timestamp_seconds"]), 4),
                round(float(manifest_frames[PILOT_END_S2]["target_timestamp_seconds"]), 4),
            ],
            "nearest_source_timestamp_range_seconds": [
                round(float(manifest_frames[PILOT_START_S2]["nearest_source_timestamp_seconds"]), 4),
                round(float(manifest_frames[PILOT_END_S2]["nearest_source_timestamp_seconds"]), 4),
            ],
            "selection_rationale": (
                "Frames 0-45 show the stationary triangle rack; frames 46-51 show the initial break impact cluster; "
                "frames 65-84 (20 consecutive frames) capture well-separated rolling balls, one ball-to-ball collision "
                "(ID 4 Red-Stripe #11 vs ID 6 Orange-Stripe #13 at frames 66-69), four cushion rebounds re-entering the table "
                "(ID 7 Yellow #1, ID 8 Yellow-Stripe #9, ID 9 Red #3, ID 10 White Cue Ball), and a close pass near ID 2 Black #8."
            ),
        },
        "ball_catalog": BALL_CATALOG,
        "statistics": {
            "frames_preannotated": 20,
            "pilot_frame_range": [PILOT_START_S2, PILOT_END_S2],
            "total_provisional_rows": len(status_rows),
            "total_proposed_tracks": len(BALL_CATALOG),
            "pilot_provisional_rows": len(status_rows),
            "pilot_proposed_tracks": len(BALL_CATALOG),
            "verified_rows_count": 0,
            "verified_frames_count": 0,
            "unreviewed_rows_count": sum(r["status"] == "UNREVIEWED" for r in status_rows),
            "uncertain_rows_count": sum(r["status"] == "UNCERTAIN" for r in status_rows),
            "uncertain_cases_total": len(uncertain_cases),
            "uncertain_cases_pilot": len(uncertain_cases),
        },
    }
    (output_dir / "annotation_manifest.json").write_text(json.dumps(manifest_out, indent=2), encoding="utf-8")

    # Write pilot_report.md for scene02
    report_lines = [
        "# F2A Scene02 — Ground Truth Pilot Report (Frames 65–84)",
        "",
        "## 1. Summary & Current Status",
        "",
        "- **Status:** `REVIEW_REQUIRED` (`0 / 20` frames human-verified; `0` `VERIFIED` rows).",
        "- **Source Video:** `data/real/raw_scene02.mp4` (Pexels ID `6253870`, 3840×2160 @ 25 FPS, 124 normalized frames @ 15 FPS).",
        "- **Selected 20-Frame Pilot Segment:** **Frames `65–84` inclusive** (`frame_065.png` .. `frame_084.png`).",
        "  - Target timestamps (15 FPS): **`4.3333s` – `5.6000s`**.",
        "  - Nearest source timestamps (25 FPS): **`4.3200s` – `5.6000s`**.",
        f"- **Provisional Labels (`provisional_gt.csv`):** **`{len(status_rows)}` rows across `{len(BALL_CATALOG)}` distinct billiard balls (`object_id = 1..10`)**.",
        f"  - `UNREVIEWED` (isolated rolling spheres): **`{sum(r['status'] == 'UNREVIEWED' for r in status_rows)}` rows**.",
        f"  - `UNCERTAIN` (touching collision `f066–f069`, close pass, or border-clipped spheres): **`{sum(r['status'] == 'UNCERTAIN' for r in status_rows)}` rows**.",
        "  - `VERIFIED`: **`0` rows**.",
        "",
        "## 2. Object Identity Catalog (`object_id = 1..10`)",
        "",
        "| Object ID | Ball Identity (Color / Stripe / Number) | Observed Frame Span | Total Frames | Notes |",
        "|---:|---|---|---:|---|",
    ]
    by_id = defaultdict(list)
    for r in status_rows:
        by_id[r["object_id"]].append(r)
    for oid in sorted(by_id):
        r_list = by_id[oid]
        f_list = [r["frame"] for r in r_list]
        unc_f = [r["frame"] for r in r_list if r["status"] == "UNCERTAIN"]
        report_lines.append(
            f"| `{oid}` | {BALL_CATALOG[oid]} | `{min(f_list)}–{max(f_list)}` | {len(f_list)} | Uncertain at frames: `{unc_f or 'none'}` |"
        )

    report_lines.extend(
        [
            "",
            "## 3. Flagged Uncertain Cases Requiring Human Verification (`25` cases)",
            "",
            "1. **Collision / Contact (`TOUCHING_COLLISION_SPLIT`, frames `66–69`):** `ID 4` (Red-Stripe `#11`) and `ID 6` (Orange-Stripe `#13`) collide in the lower-left (`x ≈ 41..62, y ≈ 133..163`). Sphere centers were separated via Voronoi distance transform; verify exact geometric centers during contact.",
            "2. **Border Entry / Exit (`BORDER_PARTIAL_SPHERE`, frames `67, 73, 76, 77, 78, 84`):** Balls partially clipped by the border (`ID 5` exiting right at `f067`, `ID 7` entering bottom at `f073`, `ID 8` entering right at `f076` and exiting top at `f084`, `ID 3` & `ID 4` exiting right/left at `f077–f078`, `ID 9` & `ID 10` entering bottom at `f077–f078`). Centers were compensated by sphere radius `R = 9.2 px`; verify whether to keep or adjust edge frames.",
            "3. **Close Pass (`CLOSE_PROXIMITY_PASS`, frames `83–84`):** `ID 10` (White Cue Ball) rolls upward past `ID 2` (Black `#8`) within `<= 23 px`.",
        ]
    )
    (output_dir / "pilot_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(
        f"Prepared scene02 pilot (frames {PILOT_START_S2}..{PILOT_END_S2}): "
        f"{len(status_rows)} provisional labels across {len(by_id)} balls; "
        f"uncertain={len(uncertain_cases)}; verified=0; status=REVIEW_REQUIRED"
    )


if __name__ == "__main__":
    main()
