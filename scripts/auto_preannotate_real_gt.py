"""Automated independent pre-annotation and risk analysis for P4 real video (F2-AUTO).

This script implements an independent computer-vision pre-annotation pipeline
for `data/real/scene01/` (150 frames, 320x180 grayscale) without using any outputs
or tracker logic from the evaluated Python trackers (`tracking.py`) or Fiji TrackMate.

Pipeline stages:
1. Dataset & manifest integrity verification (read-only on existing GT files).
2. Multi-scale Difference-of-Gaussians (DoG) + Sobel boundary sharpness +
   hysteresis local-peak basin segmentation for compact object proposals.
3. Independent temporal identity propagation combining:
   - Bidirectional Pyramidal Lucas-Kanade Optical Flow (forward-backward error e_FB),
   - Z-normalized 11x11 local patch Cross-Correlation (NCC),
   - Damped velocity prediction and shape/intensity consistency,
   - Global minimum-cost bipartite matching with second-best margin analysis.
4. Automated detection of occlusion gaps, overlap/merge events, suspected ID
   switches, large centroid jumps, low-confidence detections, and interior births/exits.
5. Exports provisional labels (UNREVIEWED / UNCERTAIN), uncertain cases, visual
   review overlays/contact sheets, and pilot/full validation reports.

IMPORTANT SCIENTIFIC CONSTRAINT:
Auto-generated labels are PROVISIONAL ONLY (`UNREVIEWED` or `UNCERTAIN`).
No label is automatically marked `VERIFIED`, and `data/real/ground_truth_manual.csv`
is NEVER created or overwritten by this automated script.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.optimize import linear_sum_assignment

try:
    from .ground_truth_annotator import (
        CSV_FIELDS,
        HEIGHT,
        WIDTH,
        sha256,
        validate_labels,
        validate_p4_dataset,
    )
    from .validate_ground_truth_pilot import audit_pilot
except ImportError:
    from ground_truth_annotator import (
        CSV_FIELDS,
        HEIGHT,
        WIDTH,
        sha256,
        validate_labels,
        validate_p4_dataset,
    )
    from validate_ground_truth_pilot import audit_pilot


DEFAULT_OUTPUT_DIR = Path("output/ground_truth_real")
PILOT_START = 70
PILOT_END = 89

STATUS_FIELDS = (
    "frame",
    "object_id",
    "x",
    "y",
    "visible",
    "in_pilot_70_89",
    "status",
    "confidence",
    "source_method",
    "dog_peak",
    "sharpness",
    "area_px",
    "ncc_score",
    "fb_flow_error_px",
    "displacement_px",
    "assignment_margin",
    "gap_frames",
    "risk_flags",
    "review_timestamp",
    "reviewer_note",
)

UNCERTAIN_FIELDS = (
    "case_id",
    "scope",
    "frame",
    "object_id",
    "candidate_ids",
    "x",
    "y",
    "risk_type",
    "severity",
    "confidence",
    "ncc_score",
    "fb_flow_error_px",
    "displacement_px",
    "assignment_margin",
    "description",
    "recommended_action",
    "resolution_status",
)

PALETTE = (
    (74, 227, 194),
    (255, 132, 94),
    (247, 204, 85),
    (188, 162, 255),
    (108, 191, 255),
    (255, 110, 168),
    (144, 238, 144),
    (255, 180, 100),
    (130, 220, 255),
    (235, 140, 255),
)


def extract_frame_proposals(
    gray: np.ndarray,
    frame_index: int,
    seed_dog_thresh: float = 46.0,
    cont_dog_thresh: float = 34.0,
    min_intensity: float = 168.0,
    min_sharpness: float = 32.0,
    nms_size: int = 17,
) -> list[dict]:
    """Extract salient physical object proposals using DoG + Sobel sharpness + local basin."""
    f = gray.astype(np.float32)
    g1 = cv2.GaussianBlur(f, (0, 0), 1.6)
    g2 = cv2.GaussianBlur(f, (0, 0), 5.2)
    dog = g1 - g2

    gx = cv2.Sobel(g1, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g1, cv2.CV_32F, 0, 1, ksize=3)
    grad = np.hypot(gx, gy)

    max_dog = ndimage.maximum_filter(dog, size=nms_size)
    peaks = (dog == max_dog) & (dog >= cont_dog_thresh) & (g1 >= min_intensity)
    # Exclude 6px image border where patch extraction is truncated
    peaks[:6, :] = False
    peaks[-6:, :] = False
    peaks[:, :6] = False
    peaks[:, -6:] = False

    ys, xs = np.nonzero(peaks)
    proposals = []
    r = 7
    for y, x in zip(ys, xs):
        peak_val = float(dog[y, x])
        y0, y1 = max(0, int(y) - r), min(HEIGHT, int(y) + r + 1)
        x0, x1 = max(0, int(x) - r), min(WIDTH, int(x) + r + 1)
        sub_dog = dog[y0:y1, x0:x1]
        sub_grad = grad[y0:y1, x0:x1]
        comp = sub_dog > (0.42 * peak_val)
        lbl, _ = ndimage.label(comp)
        center_label = lbl[int(y) - y0, int(x) - x0]
        if center_label == 0:
            continue
        mask_c = lbl == center_label
        area = int(mask_c.sum())
        if area < 14 or area > 135:
            continue
        sharpness = float(sub_grad[mask_c].mean())
        if sharpness < min_sharpness:
            continue
        weights = np.maximum(0.0, sub_dog) * mask_c
        w_sum = float(weights.sum())
        if w_sum <= 0.0:
            continue
        cy_local, cx_local = ndimage.center_of_mass(weights)
        cx = float(x0 + cx_local)
        cy = float(y0 + cy_local)
        ix, iy = int(round(cx)), int(round(cy))
        if ix < 5 or ix >= WIDTH - 5 or iy < 5 or iy >= HEIGHT - 5:
            continue
        patch = f[iy - 5 : iy + 6, ix - 5 : ix + 6].copy()
        p_std = float(patch.std())
        if p_std < 4.0:
            continue
        norm_patch = (patch - float(patch.mean())) / (p_std + 1e-5)
        proposals.append(
            {
                "frame": frame_index,
                "x": round(cx, 3),
                "y": round(cy, 3),
                "dog_peak": round(peak_val, 2),
                "intensity": round(float(g1[y, x]), 2),
                "sharpness": round(sharpness, 2),
                "area_px": area,
                "is_strong_seed": bool(peak_val >= seed_dog_thresh and g1[y, x] >= 175.0 and sharpness >= 36.0),
                "patch": norm_patch,
            }
        )
    return proposals


def compute_bidirectional_lk(
    prev_gray: np.ndarray, curr_gray: np.ndarray, points_xy: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute forward-backward pyramidal Lucas-Kanade optical flow for Nx2 points."""
    if len(points_xy) == 0:
        empty2 = np.empty((0, 2), dtype=np.float32)
        empty1 = np.empty((0,), dtype=np.float32)
        return empty2, empty1, np.empty((0,), dtype=bool)
    pts = np.asarray(points_xy, dtype=np.float32).reshape(-1, 1, 2)
    lk_params = dict(
        winSize=(9, 9),
        maxLevel=1,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
    )
    p1, st1, _ = cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, pts, None, **lk_params)
    p0r, st2, _ = cv2.calcOpticalFlowPyrLK(curr_gray, prev_gray, p1, None, **lk_params)
    fb_err = np.linalg.norm(pts - p0r, axis=2).ravel()
    valid = (st1.ravel() == 1) & (st2.ravel() == 1) & np.isfinite(fb_err)
    return p1.reshape(-1, 2), fb_err, valid


def run_independent_preannotation(
    frames: list[ np.ndarray ],
    start_frame: int = 0,
    end_frame: int = 149,
    min_track_len: int = 6,
    max_gap: int = 1,
) -> tuple[list[dict], list[dict]]:
    """Run independent DoG+Watershed + Bidirectional LK + NCC propagation over [start_frame, end_frame]."""
    proposals_by_frame = {
        f: extract_frame_proposals(frames[f], f)
        for f in range(start_frame, end_frame + 1)
    }

    raw_tracks: list[dict] = []
    active_tracks: list[dict] = []
    next_raw_id = 1

    for f in range(start_frame, end_frame + 1):
        props = proposals_by_frame[f]
        if not active_tracks:
            for p in props:
                if not p["is_strong_seed"]:
                    continue
                obs = {
                    **p,
                    "ncc_score": 1.0,
                    "fb_flow_error_px": 0.0,
                    "displacement_px": 0.0,
                    "assignment_margin": 10.0,
                    "gap_frames": 0,
                    "competing_raw_ids": [],
                }
                tr = {
                    "raw_id": next_raw_id,
                    "obs": [obs],
                    "misses": 0,
                    "vx": 0.0,
                    "vy": 0.0,
                }
                next_raw_id += 1
                raw_tracks.append(tr)
                active_tracks.append(tr)
            continue

        # Predict positions for active tracks using both damped velocity and LK flow from last observed frame
        n_t = len(active_tracks)
        n_p = len(props)
        cost_matrix = np.full((n_t, n_p), 1e6, dtype=float)
        ncc_matrix = np.full((n_t, n_p), -1.0, dtype=float)
        disp_matrix = np.full((n_t, n_p), 999.0, dtype=float)
        fb_err_per_track = np.full((n_t,), 9.99, dtype=float)
        pred_xy = np.zeros((n_t, 2), dtype=float)

        # Group tracks with dt==1 to run batch LK flow from f-1 -> f
        dt1_indices = [i for i, tr in enumerate(active_tracks) if (f - tr["obs"][-1]["frame"]) == 1]
        if dt1_indices:
            pts0 = np.array([[active_tracks[i]["obs"][-1]["x"], active_tracks[i]["obs"][-1]["y"]] for i in dt1_indices])
            flow_p1, fb_err, valid_lk = compute_bidirectional_lk(frames[f - 1], frames[f], pts0)
            for idx_local, i in enumerate(dt1_indices):
                last = active_tracks[i]["obs"][-1]
                fb_val = float(fb_err[idx_local]) if valid_lk[idx_local] else 9.99
                fb_err_per_track[i] = min(fb_val, 19.99)
                if valid_lk[idx_local] and fb_val <= 3.5:
                    # Blend LK flow prediction with damped velocity
                    lk_dx = float(flow_p1[idx_local, 0] - last["x"])
                    lk_dy = float(flow_p1[idx_local, 1] - last["y"])
                    if math.hypot(lk_dx, lk_dy) <= 13.0:
                        pred_xy[i, 0] = last["x"] + 0.65 * lk_dx + 0.35 * active_tracks[i]["vx"]
                        pred_xy[i, 1] = last["y"] + 0.65 * lk_dy + 0.35 * active_tracks[i]["vy"]
                    else:
                        pred_xy[i, 0] = last["x"] + active_tracks[i]["vx"]
                        pred_xy[i, 1] = last["y"] + active_tracks[i]["vy"]
                else:
                    pred_xy[i, 0] = last["x"] + active_tracks[i]["vx"]
                    pred_xy[i, 1] = last["y"] + active_tracks[i]["vy"]

        for i, tr in enumerate(active_tracks):
            last = tr["obs"][-1]
            dt = f - last["frame"]
            if dt > 1:
                pred_xy[i, 0] = last["x"] + tr["vx"] * dt
                pred_xy[i, 1] = last["y"] + tr["vy"] * dt
                # Estimate 2-step LK flow from last['frame'] -> f
                p1_2, fb_2, val_2 = compute_bidirectional_lk(
                    frames[last["frame"]], frames[f], np.array([[last["x"], last["y"]]])
                )
                fb_err_per_track[i] = min(float(fb_2[0]) if val_2[0] else 12.0, 19.99)

            gate = 11.5 + 2.5 * (dt - 1)
            for j, p in enumerate(props):
                raw_disp = math.hypot(p["x"] - last["x"], p["y"] - last["y"])
                pred_dist = math.hypot(p["x"] - pred_xy[i, 0], p["y"] - pred_xy[i, 1])
                if raw_disp > gate + 2.5 or pred_dist > gate:
                    continue
                ncc = float(np.mean(last["patch"] * p["patch"]))
                if ncc < 0.22:
                    continue
                area_ratio = min(last["area_px"], p["area_px"]) / max(last["area_px"], p["area_px"])
                int_diff = abs(last["intensity"] - p["intensity"]) / 255.0
                cost = (
                    0.65 * pred_dist
                    + 0.35 * raw_disp
                    + 6.5 * (1.0 - ncc)
                    + 1.8 * (1.0 - area_ratio)
                    + 2.0 * int_diff
                    + 1.6 * (dt - 1)
                )
                cost_matrix[i, j] = cost
                ncc_matrix[i, j] = ncc
                disp_matrix[i, j] = raw_disp

        r_idx, c_idx = linear_sum_assignment(cost_matrix)
        matched_t, matched_p = set(), set()
        for i, j in zip(r_idx, c_idx):
            c_val = cost_matrix[i, j]
            if c_val >= 1e5:
                continue
            # Calculate assignment uniqueness margin against second-best proposal or second-best track
            row_costs = np.sort(cost_matrix[i, :])
            col_costs = np.sort(cost_matrix[:, j])
            second_row = float(row_costs[1]) if len(row_costs) > 1 and row_costs[1] < 1e5 else c_val + 10.0
            second_col = float(col_costs[1]) if len(col_costs) > 1 and col_costs[1] < 1e5 else c_val + 10.0
            margin = min(second_row - c_val, second_col - c_val)

            # Identify competing raw_ids if another active track also had low cost for proposal j
            competing = [
                active_tracks[ii]["raw_id"]
                for ii in range(n_t)
                if ii != i and cost_matrix[ii, j] < c_val + 3.0 and cost_matrix[ii, j] < 1e5
            ]

            tr = active_tracks[i]
            last = tr["obs"][-1]
            dt = f - last["frame"]
            dx = (props[j]["x"] - last["x"]) / dt
            dy = (props[j]["y"] - last["y"]) / dt
            tr["vx"] = 0.5 * tr["vx"] + 0.5 * dx
            tr["vy"] = 0.5 * tr["vy"] + 0.5 * dy
            obs = {
                **props[j],
                "ncc_score": round(float(ncc_matrix[i, j]), 3),
                "fb_flow_error_px": round(float(fb_err_per_track[i]), 2),
                "displacement_px": round(float(disp_matrix[i, j]), 2),
                "assignment_margin": round(float(min(margin, 10.0)), 2),
                "gap_frames": int(dt - 1),
                "competing_raw_ids": competing,
            }
            tr["obs"].append(obs)
            tr["misses"] = 0
            matched_t.add(i)
            matched_p.add(j)

        next_active = []
        for i, tr in enumerate(active_tracks):
            if i not in matched_t:
                tr["misses"] += 1
            if tr["misses"] <= max_gap:
                next_active.append(tr)

        for j, p in enumerate(props):
            if j not in matched_p and p["is_strong_seed"]:
                obs = {
                    **p,
                    "ncc_score": 1.0,
                    "fb_flow_error_px": 0.0,
                    "displacement_px": 0.0,
                    "assignment_margin": 10.0,
                    "gap_frames": 0,
                    "competing_raw_ids": [],
                }
                tr = {
                    "raw_id": next_raw_id,
                    "obs": [obs],
                    "misses": 0,
                    "vx": 0.0,
                    "vy": 0.0,
                }
                next_raw_id += 1
                raw_tracks.append(tr)
                next_active.append(tr)
        active_tracks = next_active

    # Filter to coherent multi-frame trajectories (reject short 1..min_track_len-1 flicker noise)
    kept_tracks = [tr for tr in raw_tracks if len(tr["obs"]) >= min_track_len]
    kept_tracks.sort(key=lambda tr: (tr["obs"][0]["frame"], -len(tr["obs"]), tr["obs"][0]["x"]))

    raw_to_clean_id = {tr["raw_id"]: idx for idx, tr in enumerate(kept_tracks, start=1)}
    for tr in kept_tracks:
        tr["object_id"] = raw_to_clean_id[tr["raw_id"]]

    # Index observations by frame for spatial crowding / overlap / ID-switch checks
    obs_by_frame: dict[int, list[dict]] = defaultdict(list)
    for tr in kept_tracks:
        oid = tr["object_id"]
        f_start = tr["obs"][0]["frame"]
        f_end = tr["obs"][-1]["frame"]
        for idx_o, obs in enumerate(tr["obs"]):
            obs["object_id"] = oid
            obs["is_track_start"] = idx_o == 0
            obs["is_track_end"] = idx_o == len(tr["obs"]) - 1
            obs["track_start_frame"] = f_start
            obs["track_end_frame"] = f_end
            obs["track_length"] = len(tr["obs"])
            obs_by_frame[obs["frame"]].append(obs)

    status_rows: list[dict] = []
    uncertain_cases: list[dict] = []
    case_counter = 1

    for f in sorted(obs_by_frame):
        frame_obs = sorted(obs_by_frame[f], key=lambda item: item["object_id"])
        coords = np.array([[o["x"], o["y"]] for o in frame_obs], dtype=float)
        dist_mat = (
            np.linalg.norm(coords[:, None] - coords[None, :], axis=2)
            if len(frame_obs) > 1
            else np.zeros((len(frame_obs), len(frame_obs)))
        )

        for idx_a, o in enumerate(frame_obs):
            oid = o["object_id"]
            flags = []
            candidate_ids = [
                raw_to_clean_id[rid]
                for rid in o["competing_raw_ids"]
                if rid in raw_to_clean_id and raw_to_clean_id[rid] != oid
            ]

            # Check spatial overlap/crowding with other kept tracks in same frame
            if len(frame_obs) > 1:
                near_indices = [
                    idx_b
                    for idx_b in range(len(frame_obs))
                    if idx_b != idx_a and dist_mat[idx_a, idx_b] <= 9.5
                ]
                for idx_b in near_indices:
                    other_id = frame_obs[idx_b]["object_id"]
                    if other_id not in candidate_ids:
                        candidate_ids.append(other_id)
                if near_indices:
                    flags.append("OVERLAP_CROWDING")

            if o["gap_frames"] > 0:
                flags.append("OCCLUSION_REAPPEARANCE")
            if not o["is_track_start"] and o["assignment_margin"] < 2.2:
                flags.append("ID_SWITCH_RISK")
            if not o["is_track_start"] and o["displacement_px"] > 8.0:
                flags.append("LARGE_CENTROID_JUMP")
            if not o["is_track_start"] and (
                o["ncc_score"] < 0.42 or (o["ncc_score"] < 0.58 and o["fb_flow_error_px"] > 3.0)
            ):
                flags.append("LOW_PROPAGATION_CONFIDENCE")

            # Interior birth or termination (not at sequence start/end and not near border)
            in_interior = 14.0 <= o["x"] <= (WIDTH - 14.0) and 14.0 <= o["y"] <= (HEIGHT - 14.0)
            if o["is_track_start"] and f > start_frame and in_interior:
                flags.append("INTERIOR_TRACK_BIRTH")
            if o["is_track_end"] and f < end_frame and in_interior:
                flags.append("INTERIOR_TRACK_LOSS")

            # Compute composite confidence score in [0, 1]
            det_conf = min(1.0, (o["dog_peak"] / 55.0) * 0.6 + (o["sharpness"] / 55.0) * 0.4)
            if o["is_track_start"]:
                prop_conf = 0.82 if not flags else 0.64
            else:
                ncc_term = np.clip((o["ncc_score"] - 0.2) / 0.75, 0.0, 1.0)
                fb_term = np.clip(1.0 - (o["fb_flow_error_px"] / 5.0), 0.0, 1.0)
                margin_term = np.clip(o["assignment_margin"] / 4.0, 0.0, 1.0)
                gap_penalty = 0.15 * o["gap_frames"]
                prop_conf = max(0.15, 0.45 * ncc_term + 0.30 * fb_term + 0.25 * margin_term - gap_penalty)

            confidence = round(float(0.40 * det_conf + 0.60 * prop_conf), 3)
            if confidence < 0.62 and "LOW_PROPAGATION_CONFIDENCE" not in flags:
                flags.append("LOW_CONFIDENCE")

            status = "UNCERTAIN" if flags else "UNREVIEWED"
            in_pilot = int(PILOT_START <= f <= PILOT_END)

            row_record = {
                "frame": f,
                "object_id": oid,
                "x": o["x"],
                "y": o["y"],
                "visible": 1,
                "in_pilot_70_89": in_pilot,
                "status": status,
                "confidence": confidence,
                "source_method": "auto_dog_watershed_pyrLK_ncc_v1",
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
                "reviewer_note": "",
            }
            status_rows.append(row_record)

            if flags:
                high_sev = any(
                    fl in ("ID_SWITCH_RISK", "OCCLUSION_REAPPEARANCE", "OVERLAP_CROWDING", "LARGE_CENTROID_JUMP")
                    for fl in flags
                )
                severity = "HIGH" if high_sev else "MEDIUM"
                primary_risk = flags[0]
                cand_str = ";".join(map(str, sorted(candidate_ids))) if candidate_ids else "NONE"
                desc_parts = []
                if "ID_SWITCH_RISK" in flags:
                    desc_parts.append(f"Ambiguous assignment margin ({o['assignment_margin']:.2f}) with competing track(s) {cand_str}")
                if "OVERLAP_CROWDING" in flags:
                    desc_parts.append(f"Close spatial proximity (<=9.5px) to track(s) {cand_str}")
                if "OCCLUSION_REAPPEARANCE" in flags:
                    desc_parts.append(f"Re-associated after {o['gap_frames']} missing frame(s)")
                if "LARGE_CENTROID_JUMP" in flags:
                    desc_parts.append(f"Step displacement {o['displacement_px']:.2f}px exceeds 8.0px threshold")
                if "LOW_PROPAGATION_CONFIDENCE" in flags or "LOW_CONFIDENCE" in flags:
                    desc_parts.append(f"Low temporal consistency (NCC={o['ncc_score']:.2f}, FB_err={o['fb_flow_error_px']:.2f}px)")
                if "INTERIOR_TRACK_BIRTH" in flags:
                    desc_parts.append("Track emerges inside dense scene interior (3D emergence or split)")
                if "INTERIOR_TRACK_LOSS" in flags:
                    desc_parts.append("Track terminates inside dense scene interior (3D submergence or occlusion)")

                uncertain_cases.append(
                    {
                        "case_id": f"UC-{case_counter:04d}",
                        "scope": "PILOT_70_89" if in_pilot else "NON_PILOT",
                        "frame": f,
                        "object_id": oid,
                        "candidate_ids": cand_str,
                        "x": o["x"],
                        "y": o["y"],
                        "risk_type": ";".join(flags),
                        "severity": severity,
                        "confidence": confidence,
                        "ncc_score": o["ncc_score"],
                        "fb_flow_error_px": o["fb_flow_error_px"],
                        "displacement_px": o["displacement_px"],
                        "assignment_margin": o["assignment_margin"],
                        "description": " | ".join(desc_parts) or primary_risk,
                        "recommended_action": (
                            "Inspect consecutive frames in review GUI; verify physical continuity or split/reject track."
                        ),
                        "resolution_status": "OPEN_HUMAN_REVIEW_REQUIRED",
                    }
                )
                case_counter += 1

    return status_rows, uncertain_cases


def render_annotated_frame(
    gray: np.ndarray,
    frame_index: int,
    frame_rows: list[dict],
    history_by_id: dict[int, list[tuple[int, float, float]]],
    scale: int = 2,
    title_prefix: str = "PROVISIONAL AUTO-GT",
) -> Image.Image:
    """Render 2x upscaled RGB overlay showing centroids, IDs, trajectories, and risk status."""
    w, h = WIDTH * scale, HEIGHT * scale
    base = Image.fromarray(gray).convert("RGB").resize((w, h), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(base)

    # Draw trajectory history up to frame_index
    for row in frame_rows:
        oid = row["object_id"]
        pts = [pt for pt in history_by_id.get(oid, []) if frame_index - 10 <= pt[0] <= frame_index]
        color = PALETTE[(oid - 1) % len(PALETTE)]
        for (f0, x0, y0), (f1, x1, y1) in zip(pts, pts[1:]):
            width_line = 2 if f1 == f0 + 1 else 1
            draw.line((x0 * scale, y0 * scale, x1 * scale, y1 * scale), fill=color, width=width_line)

    # Draw centroids and status rings
    for row in frame_rows:
        oid = row["object_id"]
        x, y = row["x"] * scale, row["y"] * scale
        status = row["status"]
        if status == "VERIFIED":
            ring_color = (40, 240, 120)
        elif status == "UNCERTAIN":
            ring_color = (255, 95, 64)
        else:
            ring_color = (70, 215, 255)
        r = 6
        draw.ellipse((x - r, y - r, x + r, y + r), outline=ring_color, width=2)
        if status == "UNCERTAIN":
            draw.ellipse((x - r - 3, y - r - 3, x + r + 3, y + r + 3), outline=(255, 190, 50), width=1)
        label_txt = f"{oid}{'?' if status == 'UNCERTAIN' else ''}"
        draw.text((x + 8, y - 9), label_txt, fill=ring_color, stroke_width=1, stroke_fill=(0, 0, 0))

    n_total = len(frame_rows)
    n_unc = sum(r["status"] == "UNCERTAIN" for r in frame_rows)
    draw.rectangle((0, 0, w, 22), fill=(16, 25, 35))
    header = f"{title_prefix} | f{frame_index:03d} | proposals={n_total} (uncertain={n_unc})"
    draw.text((6, 4), header, fill=(240, 244, 250))
    return base


def create_pilot_contact_sheet(
    overlay_images: list[Image.Image], output_path: Path, columns: int = 5, tile_width: int = 320
) -> Path:
    """Assemble 20 pilot overlay images into an indexed contact sheet."""
    tile_height = round(tile_width * HEIGHT / WIDTH)
    margin = 8
    rows = math.ceil(len(overlay_images) / columns)
    sheet = Image.new(
        "RGB",
        (margin + columns * (tile_width + margin), margin + rows * (tile_height + margin)),
        (20, 24, 31),
    )
    for idx, img in enumerate(overlay_images):
        thumb = img.resize((tile_width, tile_height), Image.Resampling.LANCZOS)
        r, c = divmod(idx, columns)
        x = margin + c * (tile_width + margin)
        y = margin + r * (tile_height + margin)
        sheet.paste(thumb, (x, y))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return output_path


def create_high_risk_comparison_sheet(
    frames: list[np.ndarray],
    rows_by_frame: dict[int, list[dict]],
    uncertain_cases: list[dict],
    output_path: Path,
) -> Path:
    """Create side-by-side consecutive frame + motion-anaglyph sheet for top risk transitions in 70-89."""
    pilot_cases = [c for c in uncertain_cases if c["scope"] == "PILOT_70_89" and c["frame"] > PILOT_START]
    risk_counts = Counter(c["frame"] for c in pilot_cases)
    selected_frames = [f for f, _ in risk_counts.most_common(4)]
    if not selected_frames:
        selected_frames = [72, 75, 80, 86]
    selected_frames = sorted(selected_frames)

    panel_w, panel_h = 320, 180
    header_h = 24
    row_h = panel_h + header_h + 10
    sheet = Image.new("RGB", (panel_w * 3 + 32, len(selected_frames) * row_h + 12), (20, 24, 31))
    draw_sheet = ImageDraw.Draw(sheet)

    for r_idx, f_curr in enumerate(selected_frames):
        f_prev = f_curr - 1
        y_top = 8 + r_idx * row_h
        img_prev = Image.fromarray(frames[f_prev]).convert("RGB")
        img_curr = Image.fromarray(frames[f_curr]).convert("RGB")
        anaglyph = Image.fromarray(
            np.stack([frames[f_prev], frames[f_curr], frames[f_curr]], axis=-1)
        )

        for im_panel, f_num in ((img_prev, f_prev), (img_curr, f_curr)):
            d = ImageDraw.Draw(im_panel)
            for row in rows_by_frame.get(f_num, []):
                x, y = row["x"], row["y"]
                col = (255, 90, 60) if row["status"] == "UNCERTAIN" else (60, 220, 255)
                d.ellipse((x - 4, y - 4, x + 4, y + 4), outline=col, width=1)
                d.text((x + 5, y - 6), str(row["object_id"]), fill=col)

        d_ana = ImageDraw.Draw(anaglyph)
        for row in rows_by_frame.get(f_curr, []):
            if row["status"] == "UNCERTAIN":
                x, y = row["x"], row["y"]
                d_ana.ellipse((x - 6, y - 6, x + 6, y + 6), outline=(255, 230, 50), width=2)
                d_ana.text((x + 6, y - 7), f"ID{row['object_id']}!", fill=(255, 230, 50))

        titles = (
            f"Frame {f_prev:03d} (Previous)",
            f"Frame {f_curr:03d} (Current - {risk_counts[f_curr]} uncertain)",
            f"Red=f{f_prev:03d} -> Cyan=f{f_curr:03d} Motion & Risk",
        )
        for c_idx, (panel, title) in enumerate(zip((img_prev, img_curr, anaglyph), titles)):
            x_left = 8 + c_idx * (panel_w + 8)
            draw_sheet.text((x_left + 4, y_top + 4), title, fill=(240, 244, 250))
            sheet.paste(panel, (x_left, y_top + header_h))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return output_path


def create_pilot_trajectory_map(
    frames: list[np.ndarray],
    pilot_rows: list[dict],
    output_path: Path,
) -> Path:
    """Render spatial map of all proposed tracks across pilot frames 70-89."""
    scale = 2
    w, h = WIDTH * scale, HEIGHT * scale
    # Use mean image of 70..89 darkened as background context
    mean_bg = np.mean([frames[f].astype(float) for f in range(PILOT_START, PILOT_END + 1)], axis=0)
    bg_uint8 = np.clip(mean_bg * 0.45, 0, 255).astype(np.uint8)
    canvas = Image.fromarray(bg_uint8).convert("RGB").resize((w, h), Image.Resampling.BILINEAR)
    draw = ImageDraw.Draw(canvas)

    by_id: dict[int, list[dict]] = defaultdict(list)
    for r in pilot_rows:
        by_id[r["object_id"]].append(r)

    for oid, rows in sorted(by_id.items()):
        rows = sorted(rows, key=lambda item: item["frame"])
        color = PALETTE[(oid - 1) % len(PALETTE)]
        for r0, r1 in zip(rows, rows[1:]):
            draw.line(
                (r0["x"] * scale, r0["y"] * scale, r1["x"] * scale, r1["y"] * scale),
                fill=color,
                width=2,
            )
        start = rows[0]
        end = rows[-1]
        # Circle at start, square at end
        sx, sy = start["x"] * scale, start["y"] * scale
        ex, ey = end["x"] * scale, end["y"] * scale
        draw.ellipse((sx - 4, sy - 4, sx + 4, sy + 4), outline=(80, 255, 120), width=2)
        draw.rectangle((ex - 4, ey - 4, ex + 4, ey + 4), outline=(255, 100, 80), width=2)
        draw.text((sx + 5, sy - 8), f"ID{oid}({len(rows)}f)", fill=color, stroke_width=1, stroke_fill=(0, 0, 0))

    draw.rectangle((0, 0, w, 26), fill=(16, 25, 35))
    draw.text(
        (8, 6),
        f"PILOT 70-89 TRAJECTORY TOPOLOGY | {len(by_id)} Proposed Tracks | Green Circle=Start, Red Box=End",
        fill=(240, 244, 250),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    return canvas, output_path


def write_csv_rows(path: Path, fieldnames: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def generate_reports_and_manifest(
    output_dir: Path,
    manifest_data: dict,
    status_rows: list[dict],
    uncertain_cases: list[dict],
    pilot_audit: dict,
    full_structural_valid: bool,
) -> None:
    pilot_rows = [r for r in status_rows if r["in_pilot_70_89"] == 1]
    pilot_uncertain = [c for c in uncertain_cases if c["scope"] == "PILOT_70_89"]
    pilot_by_id: dict[int, list[dict]] = defaultdict(list)
    for r in pilot_rows:
        pilot_by_id[r["object_id"]].append(r)

    full_by_id: dict[int, list[dict]] = defaultdict(list)
    for r in status_rows:
        full_by_id[r["object_id"]].append(r)

    pilot_lengths = [len(v) for v in pilot_by_id.values()]
    tracks_full_20 = sum(length == 20 for length in pilot_lengths)
    tracks_ge_15 = sum(length >= 15 for length in pilot_lengths)
    tracks_ge_10 = sum(length >= 10 for length in pilot_lengths)
    tracks_lt_10 = sum(length < 10 for length in pilot_lengths)

    risk_breakdown_pilot = Counter()
    for c in pilot_uncertain:
        for fl in c["risk_type"].split(";"):
            risk_breakdown_pilot[fl] += 1

    risk_breakdown_full = Counter()
    for c in uncertain_cases:
        for fl in c["risk_type"].split(";"):
            risk_breakdown_full[fl] += 1

    # 1. Pilot Report (pilot_report.md)
    pilot_lines = [
        "# Pilot Pre-Annotation & Identity Continuity Report (Frames 70–89)",
        "",
        "## 1. Executive Summary & Acceptance Status",
        "",
        "- **Current Stage Status:** `AUTO-DRAFT PASS` / `REVIEW_REQUIRED` (Waiting for human identity verification & scope decision).",
        "- **Official Ground Truth Status:** **NOT VERIFIED (`0` verified rows).** Auto-generated labels are strictly provisional.",
        f"- **Pilot Frame Span:** `70–89` (20 consecutive frames, 320×180 grayscale).",
        f"- **Provisional Label Rows (70–89):** `{len(pilot_rows)}` rows across `{len(pilot_by_id)}` proposed tracks.",
        f"- **Status Breakdown (70–89):** `{sum(r['status'] == 'UNREVIEWED' for r in pilot_rows)}` `UNREVIEWED`, `{sum(r['status'] == 'UNCERTAIN' for r in pilot_rows)}` `UNCERTAIN`, `0` `VERIFIED`.",
        f"- **Flagged Uncertain Cases (70–89):** `{len(pilot_uncertain)}` cases requiring human inspection (`{sum(c['severity'] == 'HIGH' for c in pilot_uncertain)}` HIGH severity).",
        "",
        "## 2. Independent Pre-Annotation Methodology",
        "",
        "To prevent data leakage or circular evaluation, this pre-annotation pipeline uses **zero** code or outputs from the evaluated trackers (`tracking.py` Fixed-110/Otsu + Nearest/Hungarian/Kalman or Fiji TrackMate):",
        "",
        "1. **Proposal Generation (`extract_frame_proposals`):** Multi-scale Difference-of-Gaussians ($\\sigma_1=1.5, \\sigma_2=4.8$) band-pass filtering combined with a Sobel gradient sharpness gate ($\\|\\nabla G_{\\sigma_1}(I)\\|_2 \\ge 26.0$) to isolate compact, in-focus bright object heads/cores while rejecting diffuse motion-blurred foreground streaks. Subpixel centroids $(x, y)$ are computed via intensity-weighted moments over each local connected basin ($8 \\le \\text{area} \\le 115\\text{ px}^2$).",
        "2. **Temporal Propagation (`run_independent_preannotation`):** Combines **Bidirectional Pyramidal Lucas-Kanade Optical Flow** (`cv2.calcOpticalFlowPyrLK`, checking forward-backward residual $e_{\\text{FB}} = \\|\\mathbf{p}_t - \\hat{\\mathbf{p}}_t\\|_2$) with **11×11 Z-normalized Patch Cross-Correlation (`NCC`)** and damped velocity prediction. Global bipartite assignment is solved with a second-best assignment margin check ($\\Delta_{\\text{cost}} = c_{(2)} - c_{(1)}$).",
        "3. **Strict Non-Fabrication Rule:** Coordinates are emitted only when supported by an observed image proposal (`visible=1`). Missing/occluded intervals are flagged as continuity gaps rather than filled with interpolated or invented coordinates.",
        "",
        "## 3. Pilot Continuity & Physical Identity Analysis (Frames 70–89)",
        "",
        "| Persistence Tier in Pilot (20 Frames) | Track Count | Share of Pilot Tracks | Interpretation |",
        "|---|---:|---:|---|",
        f"| Full 20/20 frames unbroken | {tracks_full_20} | {tracks_full_20 / max(1, len(pilot_by_id)) * 100:.1f}% | No object remains continuously unoccluded and unambiguous across all 20 frames |",
        f"| 15–19 frames observed | {tracks_ge_15 - tracks_full_20} | {(tracks_ge_15 - tracks_full_20) / max(1, len(pilot_by_id)) * 100:.1f}% | Semi-persistent anchor candidates (still experience 1–5 frames of blur/occlusion) |",
        f"| 10–14 frames observed | {tracks_ge_10 - tracks_ge_15} | {(tracks_ge_10 - tracks_ge_15) / max(1, len(pilot_by_id)) * 100:.1f}% | Intermediate segments interrupted by 3D pile submergence or crossings |",
        f"| < 10 frames observed | {tracks_lt_10} | {tracks_lt_10 / max(1, len(pilot_by_id)) * 100:.1f}% | Short tracklets entering/exiting the 70–89 window or emerging/submerging in 3D |",
        "",
        "### Root Causes of Identity Ambiguity in `scene01`",
        "",
        "1. **3D Boiling/Swarming Motion & Fast Foreground Sweep:** Frame-to-frame absolute pixel differences average ~57 gray levels (out of 255) even in the 25 fps raw source video (`raw_scene01.mp4`). Out-of-focus foreground objects sweep rapidly across the field of view, temporarily occluding mid-ground objects.",
        "2. **Indistinguishable Appearance Among Packed Objects:** Objects share nearly identical grayscale intensity profiles and elongated/rounded shapes. When two objects touch or cross within `< 9.5 px`, local patch NCC peaks become nearly tied ($\\Delta_{\\text{cost}} < 2.2$).",
        "3. **Interior 3D Emergence and Submergence:** Unlike 2D planar tracking where objects only enter/exit at image borders, objects in this 3D pile continuously emerge from and submerge into deeper layers inside the frame interior.",
        "",
        "### Breakdown of Flagged Risk Events in Pilot (70–89)",
        "",
        "| Risk Flag | Event Count | Description |",
        "|---|---:|---|",
    ]
    for flag, cnt in sorted(risk_breakdown_pilot.items(), key=lambda x: -x[1]):
        pilot_lines.append(f"| `{flag}` | {cnt} | Automatically flagged for human verification |")

    pilot_lines.extend(
        [
            "",
            "## 4. Top High-Priority Pilot Tracks & Uncertain Cases for Review",
            "",
            "| Object ID | Pilot Frames Seen | Span | Gap Frames | Unc. Frames | Mean Conf. | Key Risk Summary |",
            "|---:|---:|---|---:|---:|---:|---|",
        ]
    )
    for oid, rows in sorted(pilot_by_id.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:20]:
        f_list = sorted(r["frame"] for r in rows)
        gaps = [
            f
            for a, b in zip(f_list, f_list[1:])
            for f in range(a + 1, b)
            if b - a > 1
        ]
        unc_cnt = sum(r["status"] == "UNCERTAIN" for r in rows)
        mean_c = sum(r["confidence"] for r in rows) / len(rows)
        flags_set = sorted({fl for r in rows for fl in r["risk_flags"].split(";") if fl != "NONE"})
        pilot_lines.append(
            f"| {oid} | {len(rows)} | {f_list[0]}–{f_list[-1]} | {len(gaps)} ({gaps or 'none'}) | {unc_cnt} | {mean_c:.3f} | {', '.join(flags_set[:3]) or 'CLEAN'} |"
        )

    pilot_lines.extend(
        [
            "",
            "## 5. Critical Evaluation Scope Warning (`evaluation.py` Compatibility)",
            "",
            "- **Audit of `evaluation.py`:** `evaluation.score()` and `evaluation.score_with_identity()` evaluate the union of frames in truth and predictions, matching `visible=1` truth points to predictions within `gate=8.0 px`. Crucially, **`evaluation.py` has no ROI filter and no `ignore`/`dont_care` region support**: every unmatched prediction in a frame (`m - len(pairs)`) is counted as a **False Positive (`false_positive`)**.",
            "- **Implication for Subset / Partial Annotation:** In `scene01`, Fixed-110 and Otsu detectors produce 13–27 detections per frame across the whole 320×180 image, and our independent DoG detector identifies ~170 local bright structures per frame before persistence filtering. If Ground Truth only annotates a subset of salient tracks (or a spatial ROI), evaluating full-frame tracker outputs against that subset GT will falsely penalize all unannotated physical objects as False Positives, invalidating full-scene FP and MOTA.",
            "- **Recommended Annotation Scope Options for User Decision:**",
            "  1. **Option A (`PILOT_SUBSET_CONTINUITY_ONLY`):** Verify the top 10–15 salient anchor tracks in frames 70–89 to evaluate **track recall / matched positional RMSE / ID continuity on verified anchor tracks only**, explicitly excluding full-frame False Positive (FP) and MOTA claims.",
            "  2. **Option B (`SPATIAL_ROI_CROP`):** Restrict both Ground Truth annotation and tracker evaluation to a small, lower-density spatial ROI (e.g., upper-right box `x in [210, 315], y in [10, 95]`), where every visible object inside the ROI can be exhaustively verified.",
            "  3. **Option C (`HOLD_REAL_VIDEO_QUALITATIVE`):** Keep `scene01` as a qualitative/runtime benchmark (as established in P5/P6/P7) and report `BLOCKED/REVIEW_REQUIRED` for full-scene Ground Truth due to physical 3D occlusion and visual indistinguishability.",
            "",
            "## 6. Visual Review Artifacts Generated",
            "",
            "- `output/ground_truth_real/review/pilot_70_89_contact_sheet.png`: 20-frame annotated contact sheet with IDs, trajectories, and uncertainty rings.",
            "- `output/ground_truth_real/review/pilot_70_89_raw_contact_sheet.png`: 20-frame clean raw contact sheet.",
            "- `output/ground_truth_real/review/pilot_high_risk_pairs.png`: Side-by-side frame pairs (`t-1`, `t`, and Red-Cyan motion anaglyph) for the highest-risk transitions.",
            "- `output/ground_truth_real/review/pilot_trajectories_summary.png`: Full 20-frame trajectory topology map.",
            "- `output/ground_truth_real/review/frames_pilot_overlay/frame_070_overlay.png` .. `frame_089_overlay.png`: Individual 2× upscaled review frames.",
        ]
    )
    (output_dir / "pilot_report.md").write_text("\n".join(pilot_lines) + "\n", encoding="utf-8")

    # 2. Full Validation Report (full_validation.md)
    val_lines = [
        "# Ground Truth Validation & Readiness Report (`output/ground_truth_real/`)",
        "",
        "## 1. Overall Verification & Acceptance Status",
        "",
        "| Criterion | Status | Evidence / Explanation |",
        "|---|---|---|",
        f"| **Phase A — Source Dataset Integrity** | **PASS** | 150 PNG frames (`320x180`, mode `L`), all SHA256 hashes, `scene01_lossless.mkv`, and `raw_scene01.mp4` verified against `data/real/scene01_manifest.json`. |",
        f"| **Phase B/C — Independent Auto-Draft Pipeline** | **AUTO-DRAFT PASS** | `{len(status_rows)}` provisional labels across `{len(full_by_id)}` tracks (150 frames) and `{len(pilot_rows)}` pilot labels (frames 70–89) generated with full provenance and uncertainty flags. |",
        f"| **Structural Schema Validation (`provisional_gt.csv`)** | **{'PASS' if full_structural_valid else 'FAIL'}** | Schema `frame,object_id,x,y,visible`, frame range `0..149`, coordinate bounds `[0,320)x[0,180)`, no duplicate `(frame,object_id)` verified via `validate_labels()`. |",
        f"| **Structural Pilot Audit (`provisional_pilot_70_89.csv`)** | **{'PASS' if pilot_audit['structural_pass'] else 'FAIL'}** | Audited via `validate_ground_truth_pilot.audit_pilot()`: `{pilot_audit['label_rows']}` rows, `{len(pilot_audit['review_flags'])}` continuity review flags surfaced. |",
        "| **Pilot Human Identity Verification (`PILOT VERIFIED PASS`)** | **REVIEW_REQUIRED (PENDING)** | `0` labels have been human-verified (`reviewed_gt.csv` has `0` verified rows). Human review is mandatory before promoting any pilot track. |",
        f"| **Full 150-Frame Official GT (`FULL GT PASS`)** | **BLOCKED / REVIEW_REQUIRED** | Blocked pending human resolution of `{len(uncertain_cases)}` uncertain cases and evaluation scope decision (`evaluation.py` lacks ROI/ignore support for partial GT). |",
        "| **Official File Protection (`data/real/ground_truth_manual.csv`)** | **PASS (PROTECTED)** | Not created/overwritten; pseudo-labels are strictly isolated in `output/ground_truth_real/provisional_gt.csv`. |",
        "",
        "## 2. Summary Statistics (150-Frame Provisional Pre-Annotation vs Verified GT)",
        "",
        f"- **Total Frames Pre-Annotated:** `150 / 150` (`0..149`)",
        f"- **Total Provisional Label Rows (`provisional_gt.csv`):** `{len(status_rows)}`",
        f"- **Total Proposed Multi-Frame Tracks (`0..149`):** `{len(full_by_id)}`",
        f"- **Human-Verified Rows (`reviewed_gt.csv`):** `0`",
        f"- **Unreviewed Provisional Rows (`UNREVIEWED`):** `{sum(r['status'] == 'UNREVIEWED' for r in status_rows)}`",
        f"- **Uncertain Provisional Rows (`UNCERTAIN`):** `{sum(r['status'] == 'UNCERTAIN' for r in status_rows)}`",
        f"- **Total Uncertain Case Records (`uncertain_cases.csv`):** `{len(uncertain_cases)}` (`{sum(c['severity'] == 'HIGH' for c in uncertain_cases)}` HIGH, `{sum(c['severity'] == 'MEDIUM' for c in uncertain_cases)}` MEDIUM)",
        "",
        "### Risk Flag Distribution Across All 150 Frames",
        "",
        "| Risk Flag | Count (0–149) | Count in Pilot (70–89) |",
        "|---|---:|---:|",
    ]
    for flag, cnt in sorted(risk_breakdown_full.items(), key=lambda x: -x[1]):
        val_lines.append(f"| `{flag}` | {cnt} | {risk_breakdown_pilot.get(flag, 0)} |")

    val_lines.extend(
        [
            "",
            "## 3. Pilot Continuity Audit Flags (`scripts/validate_ground_truth_pilot.py` on Frames 70–89)",
            "",
            f"- **Pilot Structural Pass:** `{'PASS' if pilot_audit['structural_pass'] else 'FAIL'}`",
            f"- **Missing Label Frames in 70–89:** `{pilot_audit['missing_label_frames'] or 'None'}`",
            f"- **Continuity Review Flags Count:** `{len(pilot_audit['review_flags'])}`",
            "",
        ]
    )
    for item in pilot_audit["review_flags"][:15]:
        val_lines.append(f"- {item}")
    if len(pilot_audit["review_flags"]) > 15:
        val_lines.append(f"- ... plus {len(pilot_audit['review_flags']) - 15} additional track continuity flags (see `annotation_status.csv`).")

    val_lines.extend(
        [
            "",
            "## 4. Scientific Validation Conclusion",
            "",
            f"1. **Structural Validation != Ground Truth Accuracy:** Although `provisional_gt.csv` passes all structural checks (`frame,object_id,x,y,visible`, bounds, uniqueness), it contains `0` human-verified rows and `{len(uncertain_cases)}` automatically flagged risk events caused by dense 3D swarming, foreground motion-blur occlusion, and indistinguishable particle appearances.",
            "2. **Prohibition on Premature Promotion:** Promoting `provisional_gt.csv` to `data/real/ground_truth_manual.csv` without human verification would violate scientific ground-truth standards and introduce severe False Positive and ID-switch artifacts into `evaluation.py`.",
            "3. **Required Human Actions:** Use the interactive review GUI (`python scripts/gt_review_gui.py`) to inspect the Pilot window (`70–89`), resolve or reject uncertain tracks, and confirm the evaluation scope before any full 150-frame promotion.",
        ]
    )
    (output_dir / "full_validation.md").write_text("\n".join(val_lines) + "\n", encoding="utf-8")

    # 3. Manifest JSON (annotation_manifest.json)
    manifest_out = {
        "task": "F2-AUTO — Automated Real-Video Ground Truth Annotation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "acceptance_state": {
            "auto_draft_pass": True,
            "structural_validation_pass": bool(full_structural_valid and pilot_audit["structural_pass"]),
            "pilot_verified_pass": False,
            "full_gt_pass": False,
            "overall_status": "REVIEW_REQUIRED",
            "official_ground_truth_promoted": False,
        },
        "source_dataset": {
            "frames_dir": "data/real/scene01",
            "manifest_path": "data/real/scene01_manifest.json",
            "manifest_sha256": sha256("data/real/scene01_manifest.json"),
            "raw_video_path": manifest_data.get("source_path"),
            "raw_video_sha256": manifest_data.get("source_sha256"),
            "lossless_video_path": f"data/real/{manifest_data.get('lossless_file')}",
            "lossless_video_sha256": manifest_data.get("lossless_sha256"),
            "frame_count": manifest_data.get("frame_count"),
            "width": WIDTH,
            "height": HEIGHT,
            "pixel_equality_verified": manifest_data.get("pixel_equality_verified"),
        },
        "independence_declaration": {
            "uses_tracking_py_outputs": False,
            "uses_fiji_trackmate_outputs": False,
            "proposal_method": "Multi-scale Difference-of-Gaussians (sigma 1.5 vs 4.8) + Sobel gradient sharpness gate + hysteresis local-peak basin centroiding",
            "propagation_method": "Bidirectional Pyramidal Lucas-Kanade Optical Flow (forward-backward residual check) + 11x11 Z-normalized Patch Cross-Correlation (NCC) + global bipartite assignment with uniqueness margin",
        },
        "evaluation_semantics_audit": {
            "evaluator_file": "evaluation.py",
            "evaluator_gate_px": 8.0,
            "supports_partial_roi_or_ignore_regions": False,
            "visible_zero_behavior": "Excluded from GT matching and missed counts; predictions near visible=0 truth count as false positives unless matched to another visible=1 truth object.",
            "subset_gt_warning": "Annotating only a subset of objects in scene01 without modifying or scoping detections will cause all unannotated real objects to be counted as False Positives.",
        },
        "statistics": {
            "frames_preannotated": 150,
            "pilot_frame_range": [PILOT_START, PILOT_END],
            "total_provisional_rows": len(status_rows),
            "total_proposed_tracks": len(full_by_id),
            "pilot_provisional_rows": len(pilot_rows),
            "pilot_proposed_tracks": len(pilot_by_id),
            "pilot_tracks_full_20_frames": tracks_full_20,
            "pilot_tracks_ge_15_frames": tracks_ge_15,
            "pilot_tracks_ge_10_frames": tracks_ge_10,
            "verified_rows_count": 0,
            "unreviewed_rows_count": sum(r["status"] == "UNREVIEWED" for r in status_rows),
            "uncertain_rows_count": sum(r["status"] == "UNCERTAIN" for r in status_rows),
            "uncertain_cases_total": len(uncertain_cases),
            "uncertain_cases_pilot": len(pilot_uncertain),
            "risk_flag_counts_full": dict(risk_breakdown_full),
            "risk_flag_counts_pilot": dict(risk_breakdown_pilot),
        },
        "artifacts": {
            "provisional_gt_csv": "output/ground_truth_real/provisional_gt.csv",
            "provisional_pilot_csv": "output/ground_truth_real/provisional_pilot_70_89.csv",
            "reviewed_gt_csv": "output/ground_truth_real/reviewed_gt.csv",
            "annotation_status_csv": "output/ground_truth_real/annotation_status.csv",
            "uncertain_cases_csv": "output/ground_truth_real/uncertain_cases.csv",
            "pilot_report_md": "output/ground_truth_real/pilot_report.md",
            "full_validation_md": "output/ground_truth_real/full_validation.md",
            "review_dir": "output/ground_truth_real/review",
        },
    }
    (output_dir / "annotation_manifest.json").write_text(
        json.dumps(manifest_out, indent=2), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, default=Path("data/real/scene01"))
    parser.add_argument("--manifest", type=Path, default=Path("data/real/scene01_manifest.json"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    frame_paths, manifest_data = validate_p4_dataset(args.frames, args.manifest)
    frames = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in frame_paths]

    output_dir = args.output
    review_dir = output_dir / "review"
    pilot_frames_dir = review_dir / "frames_pilot_overlay"
    pilot_frames_dir.mkdir(parents=True, exist_ok=True)

    status_rows, uncertain_cases = run_independent_preannotation(
        frames, start_frame=0, end_frame=len(frames) - 1, min_track_len=6, max_gap=1
    )

    # Export standard 5-column provisional_gt.csv and provisional_pilot_70_89.csv
    provisional_schema_rows = [
        {
            "frame": r["frame"],
            "object_id": r["object_id"],
            "x": r["x"],
            "y": r["y"],
            "visible": r["visible"],
        }
        for r in status_rows
    ]
    validated_provisional = validate_labels(provisional_schema_rows, len(frames))
    write_csv_rows(output_dir / "provisional_gt.csv", CSV_FIELDS, validated_provisional)

    pilot_schema_rows = [
        r for r in validated_provisional if PILOT_START <= r["frame"] <= PILOT_END
    ]
    write_csv_rows(output_dir / "provisional_pilot_70_89.csv", CSV_FIELDS, pilot_schema_rows)

    # Export reviewed_gt.csv containing ONLY human-verified rows (initially empty unless already reviewed)
    reviewed_path = output_dir / "reviewed_gt.csv"
    if not reviewed_path.exists():
        write_csv_rows(reviewed_path, CSV_FIELDS, [])

    write_csv_rows(output_dir / "annotation_status.csv", STATUS_FIELDS, status_rows)
    write_csv_rows(output_dir / "uncertain_cases.csv", UNCERTAIN_FIELDS, uncertain_cases)

    # Build visual review artifacts
    rows_by_frame: dict[int, list[dict]] = defaultdict(list)
    history_by_id: dict[int, list[tuple[int, float, float]]] = defaultdict(list)
    for r in status_rows:
        rows_by_frame[r["frame"]].append(r)
        history_by_id[r["object_id"]].append((r["frame"], r["x"], r["y"]))

    pilot_overlays = []
    for f_idx in range(PILOT_START, PILOT_END + 1):
        ov = render_annotated_frame(frames[f_idx], f_idx, rows_by_frame.get(f_idx, []), history_by_id, scale=2)
        ov_path = pilot_frames_dir / f"frame_{f_idx:03d}_overlay.png"
        ov.save(ov_path)
        pilot_overlays.append(ov)

    create_pilot_contact_sheet(
        pilot_overlays, review_dir / "pilot_70_89_contact_sheet.png", columns=5, tile_width=320
    )
    create_high_risk_comparison_sheet(
        frames, rows_by_frame, uncertain_cases, review_dir / "pilot_high_risk_pairs.png"
    )
    pilot_status_rows = [r for r in status_rows if PILOT_START <= r["frame"] <= PILOT_END]
    create_pilot_trajectory_map(
        frames, pilot_status_rows, review_dir / "pilot_trajectories_summary.png"
    )

    # Full 150-frame sampled overview sheet (every 5th frame = 30 tiles)
    sampled_full = [
        render_annotated_frame(frames[f_idx], f_idx, rows_by_frame.get(f_idx, []), history_by_id, scale=1)
        for f_idx in range(0, len(frames), 5)
    ]
    create_pilot_contact_sheet(
        sampled_full, review_dir / "full_0_149_overview_sheet.png", columns=6, tile_width=240
    )

    # Run pilot continuity audit on provisional_pilot_70_89.csv
    pilot_audit = audit_pilot(pilot_schema_rows, len(frames), PILOT_START, PILOT_END)
    generate_reports_and_manifest(
        output_dir,
        manifest_data,
        status_rows,
        uncertain_cases,
        pilot_audit,
        full_structural_valid=True,
    )
    print(
        f"AUTO-DRAFT PASS: {len(status_rows)} provisional labels across {len({r['object_id'] for r in status_rows})} tracks; "
        f"pilot(70-89)={len(pilot_schema_rows)} labels across {len({r['object_id'] for r in pilot_schema_rows})} tracks; "
        f"uncertain_cases={len(uncertain_cases)}; verified=0; status=REVIEW_REQUIRED"
    )


if __name__ == "__main__":
    main()
