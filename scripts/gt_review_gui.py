"""Interactive Human-in-the-Loop Ground Truth Review & Correction GUI (Phase D).

Provides fast human verification, correction, propagation, and risk navigation
over the provisional labels produced by `scripts/auto_preannotate_real_gt.py`.

Features:
- Video playback (Play/Pause, adjustable FPS) and frame scrubbing (0..149 or Pilot 70..89).
- Visual overlay of centroids, Object IDs, trajectory tails, and verification status
  (`VERIFIED` green, `UNREVIEWED` cyan, `UNCERTAIN` red/orange, `REJECTED` gray).
- Mouse click to select nearest object centroid or Shift+Click / click empty area to set coordinates.
- Edit Object ID, edit (x, y) centroid, toggle visible=0/1, Add/Update or Delete label.
- Approve (`VERIFIED`), Mark `UNCERTAIN`, or Reject (`REJECTED`) selected label or current frame.
- Propagate ID reassignment or swap two IDs across a frame interval [start_frame, end_frame].
- Full Undo / Redo stack for all edits.
- Quick navigation to high-risk frames and uncertain cases from `uncertain_cases.csv`.
- Side-by-side comparison mode: Single Frame (t), 2-Frame Side-by-Side (t-1 vs t),
  or Red-Cyan Motion Anaglyph (t-1 -> t).
- Atomic save to `annotation_status.csv`, `reviewed_gt.csv` (VERIFIED rows only),
  and `annotation_manifest.json`. Never promotes unverified rows to official GT.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

try:
    from .auto_preannotate_real_gt import (
        DEFAULT_OUTPUT_DIR,
        PALETTE,
        PILOT_END,
        PILOT_START,
        STATUS_FIELDS,
        UNCERTAIN_FIELDS,
    )
    from .ground_truth_annotator import (
        CSV_FIELDS,
        DEFAULT_FRAMES,
        DEFAULT_MANIFEST,
        HEIGHT,
        WIDTH,
        save_labels,
        validate_p4_dataset,
    )
except ImportError:
    from auto_preannotate_real_gt import (
        DEFAULT_OUTPUT_DIR,
        PALETTE,
        PILOT_END,
        PILOT_START,
        STATUS_FIELDS,
        UNCERTAIN_FIELDS,
    )
    from ground_truth_annotator import (
        CSV_FIELDS,
        DEFAULT_FRAMES,
        DEFAULT_MANIFEST,
        HEIGHT,
        WIDTH,
        save_labels,
        validate_p4_dataset,
    )


def load_status_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        for raw in reader:
            rows.append(
                {
                    "frame": int(raw["frame"]),
                    "object_id": int(raw["object_id"]),
                    "x": float(raw["x"]),
                    "y": float(raw["y"]),
                    "visible": int(raw["visible"]),
                    "in_pilot_70_89": int(raw.get("in_pilot_70_89", int(PILOT_START <= int(raw["frame"]) <= PILOT_END))),
                    "status": raw.get("status", "UNREVIEWED"),
                    "confidence": float(raw.get("confidence", 0.5)),
                    "source_method": raw.get("source_method", "manual_or_auto"),
                    "dog_peak": float(raw.get("dog_peak", 0.0)),
                    "sharpness": float(raw.get("sharpness", 0.0)),
                    "area_px": int(float(raw.get("area_px", 0))),
                    "ncc_score": float(raw.get("ncc_score", 0.0)),
                    "fb_flow_error_px": float(raw.get("fb_flow_error_px", 0.0)),
                    "displacement_px": float(raw.get("displacement_px", 0.0)),
                    "assignment_margin": float(raw.get("assignment_margin", 0.0)),
                    "gap_frames": int(float(raw.get("gap_frames", 0))),
                    "risk_flags": raw.get("risk_flags", "NONE"),
                    "review_timestamp": raw.get("review_timestamp", ""),
                    "reviewer_note": raw.get("reviewer_note", ""),
                }
            )
    return sorted(rows, key=lambda r: (r["frame"], r["object_id"]))


def load_uncertain_cases(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def save_review_state(
    output_dir: Path,
    status_rows: list[dict],
    uncertain_cases: list[dict],
    frame_count: int,
    reviewed_frames: set[int] | None = None,
) -> dict:
    """Atomically save status_rows, verified-only reviewed_gt.csv, frame_review_status.csv, and manifest."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "annotation_status.csv"
    reviewed_path = output_dir / "reviewed_gt.csv"
    uncertain_path = output_dir / "uncertain_cases.csv"
    frame_status_path = output_dir / "frame_review_status.csv"
    manifest_path = output_dir / "annotation_manifest.json"

    sorted_rows = sorted(status_rows, key=lambda r: (r["frame"], r["object_id"]))

    # Write annotation_status.csv atomically
    with tempfile.NamedTemporaryFile(
        "w", newline="", encoding="utf-8", dir=output_dir, prefix="status.", suffix=".tmp", delete=False
    ) as tmp:
        tmp_status = tmp.name
        writer = csv.DictWriter(tmp, fieldnames=STATUS_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted_rows)
    os.replace(tmp_status, status_path)

    # Extract ONLY human-verified rows (status == 'VERIFIED') for reviewed_gt.csv
    verified_schema_rows = [
        {
            "frame": r["frame"],
            "object_id": r["object_id"],
            "x": r["x"],
            "y": r["y"],
            "visible": r["visible"],
        }
        for r in sorted_rows
        if r["status"] == "VERIFIED"
    ]
    save_labels(reviewed_path, verified_schema_rows, frame_count)

    # Synchronize uncertain_cases resolution_status with current row statuses
    status_lookup = {(r["frame"], r["object_id"]): r["status"] for r in sorted_rows}
    for c in uncertain_cases:
        key = (int(c["frame"]), int(c["object_id"]))
        st = status_lookup.get(key, "DELETED")
        if st in ("VERIFIED", "REJECTED", "DELETED"):
            c["resolution_status"] = f"RESOLVED_{st}"
        else:
            c["resolution_status"] = "OPEN_HUMAN_REVIEW_REQUIRED"

    if uncertain_cases:
        with tempfile.NamedTemporaryFile(
            "w", newline="", encoding="utf-8", dir=output_dir, prefix="unc.", suffix=".tmp", delete=False
        ) as tmp:
            tmp_unc = tmp.name
            writer = csv.DictWriter(tmp, fieldnames=UNCERTAIN_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(uncertain_cases)
        os.replace(tmp_unc, uncertain_path)

    # Update frame_review_status.csv if it exists
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if frame_status_path.is_file():
        with frame_status_path.open(newline="", encoding="utf-8") as stream:
            f_rows = list(csv.DictReader(stream))
            f_fields = tuple(f_rows[0].keys()) if f_rows else ()
        if f_rows:
            by_f = defaultdict(list)
            for r in sorted_rows:
                if r["status"] != "REJECTED":
                    by_f[r["frame"]].append(r)
            for fr in f_rows:
                f_idx = int(fr["frame"])
                active_f = by_f.get(f_idx, [])
                n_ver = sum(r["status"] == "VERIFIED" for r in active_f)
                n_unc = sum(r["status"] == "UNCERTAIN" for r in active_f)
                n_unr = sum(r["status"] == "UNREVIEWED" for r in active_f)
                fr["provisional_objects"] = str(len(active_f))
                fr["verified_objects"] = str(n_ver)
                fr["uncertain_objects"] = str(n_unc)
                is_rev = (reviewed_frames and f_idx in reviewed_frames) or (
                    len(active_f) > 0 and n_unc == 0 and n_unr == 0 and n_ver == len(active_f)
                )
                if is_rev:
                    fr["frame_reviewed_by_human"] = "1"
                    if not fr.get("review_timestamp"):
                        fr["review_timestamp"] = now_iso
            with tempfile.NamedTemporaryFile(
                "w", newline="", encoding="utf-8", dir=output_dir, prefix="fstat.", suffix=".tmp", delete=False
            ) as tmp:
                tmp_f = tmp.name
                writer = csv.DictWriter(tmp, fieldnames=f_fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(f_rows)
            os.replace(tmp_f, frame_status_path)

    summary = {
        "total_rows": len(sorted_rows),
        "verified_rows": len(verified_schema_rows),
        "unreviewed_rows": sum(r["status"] == "UNREVIEWED" for r in sorted_rows),
        "uncertain_rows": sum(r["status"] == "UNCERTAIN" for r in sorted_rows),
        "rejected_rows": sum(r["status"] == "REJECTED" for r in sorted_rows),
    }

    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.setdefault("statistics", {})["verified_rows_count"] = summary["verified_rows"]
        manifest["statistics"]["unreviewed_rows_count"] = summary["unreviewed_rows"]
        manifest["statistics"]["uncertain_rows_count"] = summary["uncertain_rows"]
        manifest["statistics"]["rejected_rows_count"] = summary["rejected_rows"]
        manifest["last_human_review_save_utc"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return summary


def propagate_id_change(
    status_rows: list[dict],
    source_id: int,
    target_id: int,
    start_frame: int,
    end_frame: int,
    mode: str = "reassign",
) -> list[dict]:
    """Propagate ID reassignment or swap across [start_frame, end_frame] without duplicate (frame, id)."""
    if source_id <= 0 or target_id <= 0:
        raise ValueError("Object IDs must be positive integers.")
    if start_frame > end_frame:
        raise ValueError("start_frame must be <= end_frame.")
    if mode not in ("reassign", "swap"):
        raise ValueError("mode must be 'reassign' or 'swap'.")

    updated = copy.deepcopy(status_rows)
    by_frame: dict[int, dict[int, dict]] = defaultdict(dict)
    for r in updated:
        by_frame[r["frame"]][r["object_id"]] = r

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for f in range(start_frame, end_frame + 1):
        f_map = by_frame.get(f, {})
        if mode == "swap":
            if source_id in f_map and target_id in f_map:
                f_map[source_id]["object_id"] = target_id
                f_map[target_id]["object_id"] = source_id
                f_map[source_id]["review_timestamp"] = now_iso
                f_map[target_id]["review_timestamp"] = now_iso
            elif source_id in f_map:
                f_map[source_id]["object_id"] = target_id
                f_map[source_id]["review_timestamp"] = now_iso
            elif target_id in f_map:
                f_map[target_id]["object_id"] = source_id
                f_map[target_id]["review_timestamp"] = now_iso
        else:
            if source_id in f_map:
                if target_id in f_map and target_id != source_id:
                    raise ValueError(
                        f"Frame {f} already contains target ID {target_id}; use 'swap' mode instead."
                    )
                f_map[source_id]["object_id"] = target_id
                f_map[source_id]["review_timestamp"] = now_iso

    return sorted(updated, key=lambda r: (r["frame"], r["object_id"]))


class GroundTruthReviewApp:
    """Tkinter Human-in-the-Loop Review Interface for Phase D."""

    SCALE = 2

    def __init__(
        self,
        root,
        frame_paths: list[Path],
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        start_frame: int | None = None,
        display_frames: list[Path] | None = None,
    ):
        import tkinter as tk
        from tkinter import messagebox, ttk
        from PIL import ImageTk

        self.tk, self.ttk, self.messagebox = tk, ttk, messagebox
        self.ImageTk = ImageTk
        self.root = root
        self.frame_paths = list(frame_paths)
        self.display_frames = list(display_frames) if display_frames else self.frame_paths
        self.output_dir = Path(output_dir)
        self.status_rows = load_status_rows(self.output_dir / "annotation_status.csv")
        self.uncertain_cases = load_uncertain_cases(self.output_dir / "uncertain_cases.csv")
        self.reviewed_frames: set[int] = set()

        self.pilot_start = PILOT_START
        self.pilot_end = PILOT_END
        manifest_file = self.output_dir / "annotation_manifest.json"
        if manifest_file.is_file():
            try:
                m_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                p_range = m_data.get("statistics", {}).get("pilot_frame_range")
                if isinstance(p_range, list) and len(p_range) == 2:
                    self.pilot_start, self.pilot_end = int(p_range[0]), int(p_range[1])
            except (ValueError, KeyError, json.JSONDecodeError):
                pass

        init_f = self.pilot_start if start_frame is None else start_frame
        self.undo_stack: list[list[dict]] = []
        self.redo_stack: list[list[dict]] = []
        self.frame_index = max(0, min(len(self.frame_paths) - 1, init_f))
        self.selected_key: tuple[int, int] | None = None
        self.pending_point: tuple[float, float] | None = None
        self.playing = False
        self.dirty = False

        root.title(f"F2-AUTO Ground Truth Human-in-the-Loop Review — {self.output_dir.name}")
        main = ttk.Frame(root, padding=8)
        main.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # Left column: Canvas + Playback + View Mode
        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nw")

        self.canvas = tk.Canvas(
            left,
            width=WIDTH * self.SCALE * 2 + 8,
            height=HEIGHT * self.SCALE + 28,
            bg="#14181f",
            highlightthickness=1,
        )
        self.canvas.grid(row=0, column=0, sticky="nw")
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        play_bar = ttk.Frame(left, padding=(0, 6, 0, 0))
        play_bar.grid(row=1, column=0, sticky="ew")
        ttk.Button(play_bar, text="<< Prev (Left)", command=lambda: self.step_frame(-1)).grid(row=0, column=0, padx=2)
        self.play_btn = ttk.Button(play_bar, text="Play", command=self.toggle_play)
        self.play_btn.grid(row=0, column=1, padx=2)
        ttk.Button(play_bar, text="Next (Right) >>", command=lambda: self.step_frame(1)).grid(row=0, column=2, padx=2)
        ttk.Button(play_bar, text=f"Pilot {self.pilot_start}", command=lambda: self.jump_to_frame(self.pilot_start)).grid(row=0, column=3, padx=4)
        ttk.Button(play_bar, text="Prev Risk Frame", command=lambda: self.jump_risk_frame(-1)).grid(row=0, column=4, padx=2)
        ttk.Button(play_bar, text="Next Risk Frame", command=lambda: self.jump_risk_frame(1)).grid(row=0, column=5, padx=2)

        self.view_mode = tk.StringVar(value="side_by_side")
        ttk.Label(play_bar, text="View:").grid(row=0, column=6, padx=(8, 2))
        view_combo = ttk.Combobox(
            play_bar,
            textvariable=self.view_mode,
            values=("single", "side_by_side", "anaglyph"),
            width=12,
            state="readonly",
        )
        view_combo.grid(row=0, column=7, padx=2)
        view_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        self.show_rejected = tk.IntVar(value=0)
        ttk.Checkbutton(
            play_bar, text="Show Rejected", variable=self.show_rejected, command=self.refresh
        ).grid(row=0, column=8, padx=4)

        self.slider = tk.Scale(
            left,
            from_=0,
            to=len(self.frame_paths) - 1,
            orient="horizontal",
            length=WIDTH * self.SCALE * 2,
            command=self.on_slider,
        )
        self.slider.set(self.frame_index)
        self.slider.grid(row=2, column=0, sticky="ew", pady=(2, 0))

        # Right column: Controls, Object List, Propagation, Uncertain Cases, Save
        right = ttk.Frame(main, padding=(12, 0, 0, 0))
        right.grid(row=0, column=1, sticky="nw")

        self.summary_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.summary_var, font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )

        # Label Editor Box
        edit_box = ttk.LabelFrame(right, text="Selected Object / Centroid Editor", padding=6)
        edit_box.grid(row=1, column=0, sticky="ew", pady=3)
        self.obj_id_var = tk.StringVar(value="1")
        self.x_var = tk.StringVar(value="")
        self.y_var = tk.StringVar(value="")
        self.vis_var = tk.IntVar(value=1)
        self.note_var = tk.StringVar(value="")

        ttk.Label(edit_box, text="ID:").grid(row=0, column=0, sticky="w")
        ttk.Entry(edit_box, textvariable=self.obj_id_var, width=6).grid(row=0, column=1, padx=3)
        ttk.Label(edit_box, text="x:").grid(row=0, column=2, sticky="w")
        ttk.Entry(edit_box, textvariable=self.x_var, width=7).grid(row=0, column=3, padx=3)
        ttk.Label(edit_box, text="y:").grid(row=0, column=4, sticky="w")
        ttk.Entry(edit_box, textvariable=self.y_var, width=7).grid(row=0, column=5, padx=3)
        ttk.Checkbutton(edit_box, text="Visible", variable=self.vis_var).grid(row=0, column=6, padx=4)

        btn_row1 = ttk.Frame(edit_box)
        btn_row1.grid(row=1, column=0, columnspan=7, sticky="w", pady=(6, 2))
        ttk.Button(btn_row1, text="Add / Update Point", command=self.add_or_update_label).grid(row=0, column=0, padx=2)
        ttk.Button(btn_row1, text="Approve (VERIFIED)", command=lambda: self.set_selected_status("VERIFIED")).grid(row=0, column=1, padx=2)
        ttk.Button(btn_row1, text="Mark UNCERTAIN", command=lambda: self.set_selected_status("UNCERTAIN")).grid(row=0, column=2, padx=2)
        ttk.Button(btn_row1, text="Reject", command=lambda: self.set_selected_status("REJECTED")).grid(row=0, column=3, padx=2)
        ttk.Button(btn_row1, text="Delete", command=self.delete_selected).grid(row=0, column=4, padx=2)

        btn_row2 = ttk.Frame(edit_box)
        btn_row2.grid(row=2, column=0, columnspan=7, sticky="w", pady=2)
        ttk.Button(btn_row2, text="Approve Frame (VERIFIED)", command=self.approve_clean_in_frame).grid(row=0, column=0, padx=2)
        ttk.Button(btn_row2, text=f"Approve Track ({self.pilot_start}-{self.pilot_end})", command=self.approve_selected_track_pilot).grid(row=0, column=1, padx=2)

        # Propagation Box
        prop_box = ttk.LabelFrame(right, text="Propagate ID Correction Across Frames", padding=6)
        prop_box.grid(row=2, column=0, sticky="ew", pady=3)
        self.prop_src_var = tk.StringVar(value="")
        self.prop_dst_var = tk.StringVar(value="")
        self.prop_from_var = tk.StringVar(value=str(self.pilot_start))
        self.prop_to_var = tk.StringVar(value=str(self.pilot_end))
        self.prop_mode_var = tk.StringVar(value="reassign")

        ttk.Label(prop_box, text="From ID").grid(row=0, column=0)
        ttk.Entry(prop_box, textvariable=self.prop_src_var, width=5).grid(row=0, column=1, padx=2)
        ttk.Label(prop_box, text="To ID").grid(row=0, column=2)
        ttk.Entry(prop_box, textvariable=self.prop_dst_var, width=5).grid(row=0, column=3, padx=2)
        ttk.Label(prop_box, text="Frames").grid(row=0, column=4)
        ttk.Entry(prop_box, textvariable=self.prop_from_var, width=4).grid(row=0, column=5, padx=1)
        ttk.Label(prop_box, text="..").grid(row=0, column=6)
        ttk.Entry(prop_box, textvariable=self.prop_to_var, width=4).grid(row=0, column=7, padx=1)
        ttk.Combobox(
            prop_box, textvariable=self.prop_mode_var, values=("reassign", "swap"), width=8, state="readonly"
        ).grid(row=0, column=8, padx=3)
        ttk.Button(prop_box, text="Apply", command=self.apply_propagation).grid(row=0, column=9, padx=2)

        # Frame Objects Listbox
        ttk.Label(right, text="Labels in Current Frame (click to select):").grid(row=3, column=0, sticky="w", pady=(4, 0))
        self.frame_list = tk.Listbox(right, width=62, height=8, exportselection=False, font=("Consolas", 9))
        self.frame_list.grid(row=4, column=0, sticky="ew")
        self.frame_list.bind("<<ListboxSelect>>", self.on_select_frame_list)

        # High-Risk / Uncertain Cases Listbox
        ttk.Label(right, text="Flagged Uncertain Cases (click to jump & inspect):").grid(row=5, column=0, sticky="w", pady=(6, 0))
        self.unc_list = tk.Listbox(right, width=62, height=7, exportselection=False, font=("Consolas", 9))
        self.unc_list.grid(row=6, column=0, sticky="ew")
        self.unc_list.bind("<<ListboxSelect>>", self.on_select_uncertain_case)
        self.populate_uncertain_list()

        # Undo / Redo / Save Bar
        action_bar = ttk.Frame(right, padding=(0, 6, 0, 0))
        action_bar.grid(row=7, column=0, sticky="ew")
        ttk.Button(action_bar, text="Undo (Ctrl+Z)", command=self.undo).grid(row=0, column=0, padx=2)
        ttk.Button(action_bar, text="Redo (Ctrl+Y)", command=self.redo).grid(row=0, column=1, padx=2)
        ttk.Button(action_bar, text="Save Progress (Ctrl+S)", command=self.save).grid(row=0, column=2, padx=6)

        self.status_msg = tk.StringVar(value="Ready. Click an object on the canvas or select from list.")
        ttk.Label(right, textvariable=self.status_msg, wraplength=430, foreground="#2b579a").grid(
            row=8, column=0, sticky="w", pady=(4, 0)
        )

        root.bind("<Left>", lambda _e: self.step_frame(-1))
        root.bind("<Right>", lambda _e: self.step_frame(1))
        root.bind("<Control-z>", lambda _e: self.undo())
        root.bind("<Control-y>", lambda _e: self.redo())
        root.bind("<Control-s>", lambda _e: self.save())
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh()

    def push_undo(self) -> None:
        self.undo_stack.append(copy.deepcopy(self.status_rows))
        if len(self.undo_stack) > 40:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.dirty = True

    def undo(self) -> None:
        if not self.undo_stack:
            self.status_msg.set("Nothing to undo.")
            return
        self.redo_stack.append(copy.deepcopy(self.status_rows))
        self.status_rows = self.undo_stack.pop()
        self.refresh()
        self.status_msg.set("Undid last change.")

    def redo(self) -> None:
        if not self.redo_stack:
            self.status_msg.set("Nothing to redo.")
            return
        self.undo_stack.append(copy.deepcopy(self.status_rows))
        self.status_rows = self.redo_stack.pop()
        self.refresh()
        self.status_msg.set("Redid change.")

    def current_frame_rows(self, frame_idx: int | None = None) -> list[dict]:
        f = self.frame_index if frame_idx is None else frame_idx
        show_rej = bool(self.show_rejected.get())
        return [
            r
            for r in self.status_rows
            if r["frame"] == f and (show_rej or r["status"] != "REJECTED")
        ]

    def render_panel(self, frame_idx: int, label_prefix: str = "") -> Image.Image:
        w, h = WIDTH * self.SCALE, HEIGHT * self.SCALE
        base = Image.open(self.display_frames[frame_idx]).convert("RGB")
        if base.size != (w, h):
            base = base.resize((w, h), Image.Resampling.NEAREST)
        draw = ImageDraw.Draw(base)

        rows = self.current_frame_rows(frame_idx)
        by_id_hist: dict[int, list[tuple[int, float, float]]] = defaultdict(list)
        for r in self.status_rows:
            if r["status"] != "REJECTED" and frame_idx - 8 <= r["frame"] <= frame_idx:
                by_id_hist[r["object_id"]].append((r["frame"], r["x"], r["y"]))

        for r in rows:
            oid = r["object_id"]
            pts = by_id_hist.get(oid, [])
            col = PALETTE[(oid - 1) % len(PALETTE)]
            for (f0, x0, y0), (f1, x1, y1) in zip(pts, pts[1:]):
                draw.line((x0 * self.SCALE, y0 * self.SCALE, x1 * self.SCALE, y1 * self.SCALE), fill=col, width=2)

        for r in rows:
            oid = r["object_id"]
            x, y = r["x"] * self.SCALE, r["y"] * self.SCALE
            st = r["status"]
            if st == "VERIFIED":
                color = (40, 240, 120)
            elif st == "UNCERTAIN":
                color = (255, 90, 60)
            elif st == "REJECTED":
                color = (140, 140, 140)
            else:
                color = (70, 215, 255)
            rad = 8 if (frame_idx, oid) == self.selected_key else 5
            draw.ellipse((x - rad, y - rad, x + rad, y + rad), outline=color, width=2)
            draw.text((x + rad + 2, y - rad), f"{oid}", fill=color, stroke_width=1, stroke_fill=(0, 0, 0))

        if frame_idx == self.frame_index and self.pending_point:
            px, py = self.pending_point[0] * self.SCALE, self.pending_point[1] * self.SCALE
            draw.line((px - 8, py, px + 8, py), fill=(255, 255, 60), width=2)
            draw.line((px, py - 8, px, py + 8), fill=(255, 255, 60), width=2)

        draw.rectangle((0, 0, w, 20), fill=(18, 24, 32))
        draw.text((6, 3), f"{label_prefix}Frame {frame_idx:03d} ({len(rows)} labels)", fill=(240, 244, 250))
        return base

    def refresh(self) -> None:
        w, h = WIDTH * self.SCALE, HEIGHT * self.SCALE
        mode = self.view_mode.get()
        composite = Image.new("RGB", (w * 2 + 8, h + 24), (20, 24, 31))
        draw_c = ImageDraw.Draw(composite)

        curr_panel = self.render_panel(self.frame_index, "CURRENT: ")
        if mode == "single" or self.frame_index == 0:
            composite.paste(curr_panel, (0, 0))
            draw_c.text((w + 16, 20), "Single-frame view (advance to frame >= 1 for comparison).", fill=(180, 190, 205))
        elif mode == "side_by_side":
            prev_panel = self.render_panel(self.frame_index - 1, "PREVIOUS: ")
            composite.paste(prev_panel, (0, 0))
            composite.paste(curr_panel, (w + 8, 0))
        elif mode == "anaglyph":
            import numpy as np
            f_prev = np.asarray(Image.open(self.frame_paths[self.frame_index - 1]).convert("L"))
            f_curr = np.asarray(Image.open(self.frame_paths[self.frame_index]).convert("L"))
            ana = Image.fromarray(np.stack([f_prev, f_curr, f_curr], axis=-1)).resize((w, h), Image.Resampling.NEAREST)
            d_ana = ImageDraw.Draw(ana)
            d_ana.rectangle((0, 0, w, 20), fill=(18, 24, 32))
            d_ana.text((6, 3), f"ANAGLYPH Red=f{self.frame_index-1:03d} -> Cyan=f{self.frame_index:03d}", fill=(255, 235, 90))
            composite.paste(curr_panel, (0, 0))
            composite.paste(ana, (w + 8, 0))

        self.photo = self.ImageTk.PhotoImage(composite)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")

        # Update summary & frame list
        n_ver = sum(r["status"] == "VERIFIED" for r in self.status_rows)
        n_unc = sum(r["status"] == "UNCERTAIN" for r in self.status_rows)
        n_unr = sum(r["status"] == "UNREVIEWED" for r in self.status_rows)
        self.summary_var.set(
            f"Frame {self.frame_index:03d}/{len(self.frame_paths)-1} | VERIFIED={n_ver} | UNCERTAIN={n_unc} | UNREVIEWED={n_unr}"
        )

        self.frame_list.delete(0, self.tk.END)
        self.frame_keys = []
        for r in self.current_frame_rows():
            self.frame_list.insert(
                self.tk.END,
                f"ID {r['object_id']:3d} | ({r['x']:5.1f},{r['y']:5.1f}) | {r['status']:10s} | conf={r['confidence']:.2f} | {r['risk_flags']}",
            )
            self.frame_keys.append((r["frame"], r["object_id"]))

    def on_canvas_click(self, event) -> None:
        w = WIDTH * self.SCALE
        mode = self.view_mode.get()
        # Determine if click is on Current panel
        if mode == "side_by_side" and self.frame_index > 0 and event.x >= w + 8:
            x = (event.x - (w + 8)) / self.SCALE
        else:
            x = event.x / self.SCALE
        y = event.y / self.SCALE
        if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
            return

        # Find nearest object within 8 px unless pending_point is desired
        rows = self.current_frame_rows()
        nearest = None
        best_d = 8.0
        for r in rows:
            d = math.hypot(r["x"] - x, r["y"] - y)
            if d < best_d:
                best_d = d
                nearest = r

        if nearest is not None:
            self.selected_key = (nearest["frame"], nearest["object_id"])
            self.obj_id_var.set(str(nearest["object_id"]))
            self.x_var.set(f"{nearest['x']:.2f}")
            self.y_var.set(f"{nearest['y']:.2f}")
            self.vis_var.set(nearest["visible"])
            self.prop_src_var.set(str(nearest["object_id"]))
            self.pending_point = None
            self.status_msg.set(
                f"Selected ID {nearest['object_id']} ({nearest['status']}, flags={nearest['risk_flags']})."
            )
        else:
            self.pending_point = (x, y)
            self.x_var.set(f"{x:.2f}")
            self.y_var.set(f"{y:.2f}")
            self.status_msg.set(f"Point ({x:.1f}, {y:.1f}) picked; click 'Add / Update Point' to assign to ID {self.obj_id_var.get()}.")
        self.refresh()

    def add_or_update_label(self) -> None:
        try:
            oid = int(self.obj_id_var.get())
            x = float(self.x_var.get())
            y = float(self.y_var.get())
            vis = int(self.vis_var.get())
            if oid <= 0 or not (0 <= x < WIDTH and 0 <= y < HEIGHT) or vis not in (0, 1):
                raise ValueError("Require ID > 0, 0 <= x < 320, 0 <= y < 180, visible in {0,1}.")
        except ValueError as err:
            self.messagebox.showerror("Invalid input", str(err))
            return

        self.push_undo()
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        key = (self.frame_index, oid)
        existing = next((r for r in self.status_rows if (r["frame"], r["object_id"]) == key), None)
        if existing:
            existing["x"] = round(x, 3)
            existing["y"] = round(y, 3)
            existing["visible"] = vis
            existing["status"] = "VERIFIED"
            existing["confidence"] = 1.0
            existing["source_method"] = "human_edited_verified"
            existing["risk_flags"] = "NONE"
            existing["review_timestamp"] = now_iso
        else:
            self.status_rows.append(
                {
                    "frame": self.frame_index,
                    "object_id": oid,
                    "x": round(x, 3),
                    "y": round(y, 3),
                    "visible": vis,
                    "in_pilot_70_89": int(PILOT_START <= self.frame_index <= PILOT_END),
                    "status": "VERIFIED",
                    "confidence": 1.0,
                    "source_method": "human_added_verified",
                    "dog_peak": 0.0,
                    "sharpness": 0.0,
                    "area_px": 0,
                    "ncc_score": 1.0,
                    "fb_flow_error_px": 0.0,
                    "displacement_px": 0.0,
                    "assignment_margin": 10.0,
                    "gap_frames": 0,
                    "risk_flags": "NONE",
                    "review_timestamp": now_iso,
                    "reviewer_note": "manual_upsert",
                }
            )
            self.status_rows.sort(key=lambda r: (r["frame"], r["object_id"]))
        self.selected_key = key
        self.pending_point = None
        self.refresh()
        self.status_msg.set(f"Upserted and VERIFIED ID {oid} at frame {self.frame_index}.")

    def set_selected_status(self, new_status: str) -> None:
        if self.selected_key is None:
            self.status_msg.set("Select a label first.")
            return
        self.push_undo()
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for r in self.status_rows:
            if (r["frame"], r["object_id"]) == self.selected_key:
                r["status"] = new_status
                r["review_timestamp"] = now_iso
                break
        self.refresh()
        self.status_msg.set(f"Set {self.selected_key} status to {new_status}.")

    def approve_clean_in_frame(self) -> None:
        self.push_undo()
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        count = 0
        for r in self.status_rows:
            if r["frame"] == self.frame_index and r["status"] in ("UNREVIEWED", "UNCERTAIN"):
                r["status"] = "VERIFIED"
                r["review_timestamp"] = now_iso
                count += 1
        self.reviewed_frames.add(self.frame_index)
        self.refresh()
        self.status_msg.set(f"Marked {count} labels in frame {self.frame_index} as VERIFIED (frame recorded as reviewed).")

    def approve_selected_track_pilot(self) -> None:
        if self.selected_key is None:
            self.status_msg.set("Select an object track first.")
            return
        oid = self.selected_key[1]
        self.push_undo()
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        count = 0
        for r in self.status_rows:
            if r["object_id"] == oid and self.pilot_start <= r["frame"] <= self.pilot_end and r["status"] != "REJECTED":
                r["status"] = "VERIFIED"
                r["review_timestamp"] = now_iso
                count += 1
        self.refresh()
        self.status_msg.set(f"Approved {count} pilot frames ({self.pilot_start}-{self.pilot_end}) for Track ID {oid} as VERIFIED.")

    def delete_selected(self) -> None:
        if self.selected_key is None:
            self.status_msg.set("Select a label first.")
            return
        self.push_undo()
        self.status_rows = [
            r for r in self.status_rows if (r["frame"], r["object_id"]) != self.selected_key
        ]
        self.selected_key = None
        self.refresh()
        self.status_msg.set("Deleted selected label.")

    def apply_propagation(self) -> None:
        try:
            src_id = int(self.prop_src_var.get())
            dst_id = int(self.prop_dst_var.get())
            f_start = int(self.prop_from_var.get())
            f_end = int(self.prop_to_var.get())
            mode = self.prop_mode_var.get()
            self.push_undo()
            self.status_rows = propagate_id_change(
                self.status_rows, src_id, dst_id, f_start, f_end, mode=mode
            )
        except ValueError as err:
            self.messagebox.showerror("Propagation error", str(err))
            return
        self.refresh()
        self.status_msg.set(f"Propagated {mode} ID {src_id} -> {dst_id} across frames {f_start}..{f_end}.")

    def on_select_frame_list(self, _event=None) -> None:
        sel = self.frame_list.curselection()
        if not sel:
            return
        key = self.frame_keys[sel[0]]
        row = next((r for r in self.status_rows if (r["frame"], r["object_id"]) == key), None)
        if row:
            self.selected_key = key
            self.obj_id_var.set(str(row["object_id"]))
            self.x_var.set(f"{row['x']:.2f}")
            self.y_var.set(f"{row['y']:.2f}")
            self.vis_var.set(row["visible"])
            self.prop_src_var.set(str(row["object_id"]))
            self.refresh()

    def populate_uncertain_list(self) -> None:
        self.unc_list.delete(0, self.tk.END)
        for c in self.uncertain_cases:
            self.unc_list.insert(
                self.tk.END,
                f"{c['case_id']} | f{int(c['frame']):03d} ID {int(c['object_id']):3d} | {c['severity']:6s} | {c['risk_type']}",
            )

    def on_select_uncertain_case(self, _event=None) -> None:
        sel = self.unc_list.curselection()
        if not sel:
            return
        c = self.uncertain_cases[sel[0]]
        f_idx = int(c["frame"])
        oid = int(c["object_id"])
        self.frame_index = f_idx
        self.slider.set(f_idx)
        self.selected_key = (f_idx, oid)
        self.obj_id_var.set(str(oid))
        self.prop_src_var.set(str(oid))
        self.refresh()
        self.status_msg.set(f"{c['case_id']}: {c['description']}")

    def step_frame(self, delta: int) -> None:
        self.jump_to_frame(self.frame_index + delta)

    def jump_to_frame(self, target: int) -> None:
        self.frame_index = max(0, min(len(self.frame_paths) - 1, target))
        self.slider.set(self.frame_index)
        self.pending_point = None
        self.refresh()

    def jump_risk_frame(self, direction: int) -> None:
        risk_frames = sorted({r["frame"] for r in self.status_rows if r["status"] == "UNCERTAIN"})
        if not risk_frames:
            self.status_msg.set("No uncertain frames remaining.")
            return
        if direction > 0:
            nxt = [f for f in risk_frames if f > self.frame_index]
            target = nxt[0] if nxt else risk_frames[0]
        else:
            prv = [f for f in risk_frames if f < self.frame_index]
            target = prv[-1] if prv else risk_frames[-1]
        self.jump_to_frame(target)

    def on_slider(self, value: str) -> None:
        idx = int(value)
        if idx != self.frame_index:
            self.frame_index = idx
            self.pending_point = None
            self.refresh()

    def toggle_play(self) -> None:
        self.playing = not self.playing
        self.play_btn.config(text="Pause" if self.playing else "Play")
        if self.playing:
            self._tick_play()

    def _tick_play(self) -> None:
        if not self.playing:
            return
        nxt = (self.frame_index + 1) % len(self.frame_paths)
        self.jump_to_frame(nxt)
        self.root.after(150, self._tick_play)

    def save(self) -> None:
        summary = save_review_state(
            self.output_dir,
            self.status_rows,
            self.uncertain_cases,
            len(self.frame_paths),
            reviewed_frames=self.reviewed_frames,
        )
        self.dirty = False
        self.status_msg.set(
            f"Saved! VERIFIED={summary['verified_rows']} rows written to reviewed_gt.csv; "
            f"UNCERTAIN={summary['uncertain_rows']}, UNREVIEWED={summary['unreviewed_rows']}."
        )

    def on_close(self) -> None:
        self.playing = False
        if self.dirty and not self.messagebox.askyesno(
            "Unsaved review changes", "Discard unsaved review changes and close?"
        ):
            return
        self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, default=DEFAULT_FRAMES)
    parser.add_argument("--display-frames", type=Path, default=None,
                        help="optional RGB/zoomed frame directory for display")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start-frame", type=int, default=None)
    args = parser.parse_args()

    frame_paths, _ = validate_p4_dataset(args.frames, args.manifest)
    display_frames = None
    if args.display_frames is not None:
        display_frames = sorted(Path(args.display_frames).glob("frame_*.png"))
    elif "scene02" in str(args.frames) or "scene02" in str(args.output_dir):
        c2 = Path("data/real/scene02_color_2x")
        c1 = Path("data/real/scene02_color")
        if c2.is_dir():
            display_frames = sorted(c2.glob("frame_*.png"))
        elif c1.is_dir():
            display_frames = sorted(c1.glob("frame_*.png"))
    import tkinter as tk

    root = tk.Tk()
    GroundTruthReviewApp(
        root,
        frame_paths,
        args.output_dir,
        start_frame=args.start_frame,
        display_frames=display_frames,
    )
    root.mainloop()


if __name__ == "__main__":
    main()

