"""Manual ground-truth annotation helper for the P4 real-video frames.

Run ``python scripts/ground_truth_annotator.py --prepare`` to verify the P4
dataset and create a contact sheet plus empty CSV template. Run without
``--prepare`` to open the manual annotation window.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


WIDTH, HEIGHT = 320, 180
CSV_FIELDS = ("frame", "object_id", "x", "y", "visible")
DEFAULT_FRAMES = Path("data/real/scene01")
DEFAULT_MANIFEST = Path("data/real/scene01_manifest.json")
DEFAULT_TEMPLATE = Path("data/real/ground_truth_template.csv")
DEFAULT_CONTACT_SHEET = Path("output/person1/ground_truth/contact_sheet.png")
DEFAULT_ALL_FRAMES_SHEET = Path("output/person1/ground_truth/contact_sheet_all_frames.png")
DEFAULT_LABELS = Path("data/real/ground_truth_manual.csv")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_p4_dataset(frames_dir=DEFAULT_FRAMES, manifest_path=DEFAULT_MANIFEST):
    """Validate frame sequence, dimensions, modes and manifest hashes."""
    frames_dir, manifest_path = Path(frames_dir), Path(manifest_path)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"P4 manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = sorted(frames_dir.glob("frame_*.png"))
    count = manifest.get("frame_count")
    if not isinstance(count, int) or count <= 0 or len(files) != count:
        raise ValueError(f"Frame count mismatch: manifest={count}, PNGs={len(files)}")
    records = manifest.get("frames", [])
    if len(records) != count:
        raise ValueError(f"Manifest has {len(records)} frame records; expected {count}")
    expected_names = [f"frame_{index:03d}.png" for index in range(count)]
    if [path.name for path in files] != expected_names:
        raise ValueError("PNG files must be contiguous and indexed from frame_000.png")
    for index, (path, record) in enumerate(zip(files, records)):
        if (record.get("index") != index or record.get("file") != path.name
                or record.get("width") != WIDTH or record.get("height") != HEIGHT
                or record.get("mode") != "L"):
            raise ValueError(f"Invalid manifest record for frame {index}")
        try:
            with Image.open(path) as image:
                if image.mode != "L" or image.size != (WIDTH, HEIGHT):
                    raise ValueError(f"Invalid PNG frame {path.name}: {image.mode} {image.size}")
                image.verify()
        except (OSError, SyntaxError) as error:
            raise ValueError(f"Unreadable PNG frame {path.name}: {error}") from error
        if sha256(path) != record.get("sha256"):
            raise ValueError(f"SHA256 mismatch for {path.name}")
    if manifest.get("pixel_equality_verified") is not True:
        raise ValueError("P4 manifest does not record verified PNG/FFV1 pixel equality")
    lossless_name = manifest.get("lossless_file")
    if not lossless_name or not (manifest_path.parent / lossless_name).is_file():
        raise FileNotFoundError("P4 FFV1 video referenced by manifest is missing")
    if sha256(manifest_path.parent / lossless_name) != manifest.get("lossless_sha256"):
        raise ValueError("P4 FFV1 video checksum mismatch")
    source_path = Path(manifest.get("source_path", ""))
    if source_path.is_file() and sha256(source_path) != manifest.get("source_sha256"):
        raise ValueError("P4 source video checksum mismatch")
    return files, manifest


def create_contact_sheet(frames, output_path=DEFAULT_CONTACT_SHEET, columns=10,
                         tile_width=160):
    """Render all supplied frames as an indexed visual overview."""
    frames = list(frames)
    if not frames:
        raise ValueError("Cannot create a contact sheet without frames")
    if columns <= 0 or tile_width <= 0:
        raise ValueError("columns and tile_width must be positive")
    tile_height = round(tile_width * HEIGHT / WIDTH)
    label_height, margin = 20, 8
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new(
        "RGB",
        (margin + columns * (tile_width + margin),
         margin + rows * (tile_height + label_height + margin)),
        (24, 29, 36),
    )
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(frames):
        with Image.open(path) as source:
            thumbnail = source.convert("RGB").resize(
                (tile_width, tile_height), Image.Resampling.LANCZOS)
        row, col = divmod(index, columns)
        x = margin + col * (tile_width + margin)
        y = margin + row * (tile_height + label_height + margin)
        sheet.paste(thumbnail, (x, y + label_height))
        frame_label = Path(path).stem.replace("frame_", "frame ")
        draw.text((x + 3, y + 3), frame_label, fill=(240, 244, 250))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return output_path


def empty_template(path=DEFAULT_TEMPLATE):
    """Create a header-only template; this deliberately contains no labels."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.reader(stream))
        if rows == [list(CSV_FIELDS)]:
            return path
        raise FileExistsError(f"Refusing to overwrite nonempty template path: {path}")
    with path.open("w", newline="", encoding="utf-8") as stream:
        csv.writer(stream, lineterminator="\n").writerow(CSV_FIELDS)
    return path


def _strict_int(value, field):
    text = str(value).strip()
    try:
        number = int(text)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be an integer") from error
    if str(number) != text and not (number == 0 and text == "-0"):
        raise ValueError(f"{field} must be an integer")
    return number


def validate_labels(rows, frame_count):
    """Validate manual labels and return normalized schema rows."""
    if frame_count <= 0:
        raise ValueError("frame_count must be positive")
    validated, seen = [], set()
    for line, raw in enumerate(rows, start=2):
        try:
            frame = _strict_int(raw["frame"], "frame")
            object_id = _strict_int(raw["object_id"], "object_id")
            x, y = float(raw["x"]), float(raw["y"])
            visible = _strict_int(raw["visible"], "visible")
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Invalid label at CSV line {line}: {error}") from error
        if not 0 <= frame < frame_count:
            raise ValueError(f"Frame out of range at CSV line {line}")
        if object_id <= 0:
            raise ValueError(f"object_id must be positive at CSV line {line}")
        if not math.isfinite(x) or not 0 <= x < WIDTH:
            raise ValueError(f"x must be finite and in [0, {WIDTH}) at CSV line {line}")
        if not math.isfinite(y) or not 0 <= y < HEIGHT:
            raise ValueError(f"y must be finite and in [0, {HEIGHT}) at CSV line {line}")
        if visible not in (0, 1):
            raise ValueError(f"visible must be 0 or 1 at CSV line {line}")
        key = (frame, object_id)
        if key in seen:
            raise ValueError(f"Duplicate object_id {object_id} in frame {frame}")
        seen.add(key)
        validated.append({"frame": frame, "object_id": object_id,
                          "x": x, "y": y, "visible": visible})
    return sorted(validated, key=lambda row: (row["frame"], row["object_id"]))


def load_labels(path, frame_count):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(CSV_FIELDS):
            raise ValueError(f"CSV header must be exactly: {','.join(CSV_FIELDS)}")
        return validate_labels(reader, frame_count)


def save_labels(path, rows, frame_count):
    path = Path(path)
    validated = validate_labels(rows, frame_count)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8",
                                         dir=path.parent, prefix=path.name + ".",
                                         suffix=".tmp", delete=False) as stream:
            temp_name = stream.name
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS,
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(validated)
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return len(validated)


def upsert_label(rows, frame, object_id, x, y, visible, frame_count):
    """Add or edit one object's label in one frame without duplicate IDs."""
    candidate = validate_labels([{"frame": frame, "object_id": object_id,
                                  "x": x, "y": y, "visible": int(visible)}],
                                frame_count)[0]
    key = (candidate["frame"], candidate["object_id"])
    result = {(row["frame"], row["object_id"]): dict(row) for row in rows}
    result[key] = candidate
    return sorted(result.values(), key=lambda row: (row["frame"], row["object_id"]))


class AnnotationApp:
    """Small click-to-label Tkinter UI; it never calls an automatic detector."""
    SCALE = 2

    def __init__(self, root, frames, labels_path):
        import tkinter as tk
        from tkinter import messagebox, ttk
        from PIL import ImageTk

        self.tk, self.messagebox, self.ttk = tk, messagebox, ttk
        self.ImageTk = ImageTk
        self.root, self.frames = root, list(frames)
        self.labels_path = Path(labels_path)
        self.rows = load_labels(self.labels_path, len(self.frames))
        self.frame_index = 0
        self.pending_point = None
        self.selected_key = None
        self.dirty = False
        root.title("Manual ground truth - scene01")

        body = ttk.Frame(root, padding=10)
        body.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(body, width=WIDTH * self.SCALE,
                                height=HEIGHT * self.SCALE, highlightthickness=1)
        self.canvas.grid(row=0, column=0, rowspan=8, sticky="n")
        self.canvas.bind("<Button-1>", self.on_image_click)

        controls = ttk.Frame(body, padding=(14, 0, 0, 0))
        controls.grid(row=0, column=1, sticky="nw")
        self.frame_text = tk.StringVar(value="0")
        self.object_text = tk.StringVar(value="1")
        self.x_text = tk.StringVar(value="")
        self.y_text = tk.StringVar(value="")
        self.visible_var = tk.IntVar(value=1)
        self.status_text = tk.StringVar(value="Ready. Labels are manual; Save writes CSV.")

        nav = ttk.Frame(controls)
        nav.grid(row=0, column=0, sticky="w")
        ttk.Button(nav, text="Previous", command=lambda: self.go(-1)).grid(row=0, column=0)
        ttk.Button(nav, text="Next", command=lambda: self.go(1)).grid(row=0, column=1, padx=4)
        ttk.Label(nav, text="Frame").grid(row=0, column=2, padx=(8, 2))
        ttk.Entry(nav, textvariable=self.frame_text, width=6).grid(row=0, column=3)
        ttk.Button(nav, text="Go", command=self.go_to_entry).grid(row=0, column=4, padx=4)

        fields = ttk.Frame(controls)
        fields.grid(row=1, column=0, sticky="w", pady=(12, 4))
        ttk.Label(fields, text="Object ID (known IDs selectable)").grid(
            row=0, column=0, sticky="w")
        self.id_combo = ttk.Combobox(fields, textvariable=self.object_text,
                                     values=(), width=10)
        self.id_combo.grid(row=1, column=0, padx=(0, 6))
        for col, (label, variable) in enumerate((("x", self.x_text),
                                                  ("y", self.y_text)), start=1):
            ttk.Label(fields, text=label).grid(row=0, column=col, sticky="w")
            ttk.Entry(fields, textvariable=variable, width=8).grid(
                row=1, column=col, padx=(0, 6))
        ttk.Checkbutton(controls, text="Visible", variable=self.visible_var).grid(
            row=2, column=0, sticky="w")
        ttk.Label(controls, text="Click an object's center, then Add / Update.").grid(
            row=3, column=0, sticky="w", pady=(6, 0))
        ttk.Button(controls, text="Add / Update label", command=self.add_or_update).grid(
            row=4, column=0, sticky="w", pady=4)
        ttk.Button(controls, text="Delete selected label", command=self.delete_selected).grid(
            row=5, column=0, sticky="w", pady=4)
        self.listbox = tk.Listbox(controls, width=38, height=9, exportselection=False)
        self.listbox.grid(row=6, column=0, sticky="w", pady=(6, 0))
        self.listbox.bind("<<ListboxSelect>>", self.on_select_label)
        ttk.Button(controls, text="Save CSV", command=self.save).grid(
            row=7, column=0, sticky="w", pady=8)
        ttk.Label(controls, textvariable=self.status_text, wraplength=300).grid(
            row=8, column=0, sticky="w")
        ttk.Label(controls, text=f"CSV: {self.labels_path}", wraplength=330).grid(
            row=9, column=0, sticky="w", pady=(8, 0))
        root.bind("<Left>", lambda _event: self.go(-1))
        root.bind("<Right>", lambda _event: self.go(1))
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh()

    def current_rows(self):
        return [row for row in self.rows if row["frame"] == self.frame_index]

    def refresh(self):
        image = Image.open(self.frames[self.frame_index]).convert("RGB")
        image = image.resize((WIDTH * self.SCALE, HEIGHT * self.SCALE),
                             Image.Resampling.NEAREST)
        from PIL import ImageDraw
        draw = ImageDraw.Draw(image)
        radius = 6
        for row in self.current_rows():
            x, y = row["x"] * self.SCALE, row["y"] * self.SCALE
            color = (40, 240, 120) if row["visible"] else (255, 165, 40)
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline=color, width=2)
            draw.text((x + radius + 2, y - radius), str(row["object_id"]),
                      fill=color, stroke_width=1, stroke_fill=(0, 0, 0))
        if self.pending_point:
            x, y = self.pending_point[0] * self.SCALE, self.pending_point[1] * self.SCALE
            draw.line((x-8, y, x+8, y), fill=(50, 170, 255), width=2)
            draw.line((x, y-8, x, y+8), fill=(50, 170, 255), width=2)
        self.photo = self.ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.frame_text.set(str(self.frame_index))
        self.listbox.delete(0, self.tk.END)
        self.list_keys = []
        self.id_combo["values"] = tuple(str(value) for value in sorted(
            {row["object_id"] for row in self.rows}))
        for row in self.current_rows():
            self.listbox.insert(self.tk.END,
                f"ID {row['object_id']}  ({row['x']:.1f}, {row['y']:.1f})  visible={row['visible']}")
            self.list_keys.append((row["frame"], row["object_id"]))

    def on_image_click(self, event):
        x, y = event.x / self.SCALE, event.y / self.SCALE
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            self.pending_point = (x, y)
            self.x_text.set(f"{x:.2f}")
            self.y_text.set(f"{y:.2f}")
            self.status_text.set("Point selected; assign ID/visibility and Add / Update.")
            self.refresh()

    def add_or_update(self):
        try:
            self.rows = upsert_label(
                self.rows, self.frame_index, self.object_text.get(),
                self.x_text.get(), self.y_text.get(), self.visible_var.get(),
                len(self.frames))
        except (KeyError, TypeError, ValueError) as error:
            self.messagebox.showerror("Invalid label", str(error))
            return
        self.selected_key = (self.frame_index, int(self.object_text.get()))
        self.dirty = True
        self.pending_point = None
        self.status_text.set("Label updated in memory. Save CSV to persist changes.")
        self.refresh()

    def on_select_label(self, _event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        key = self.list_keys[selection[0]]
        row = next(item for item in self.rows
                   if (item["frame"], item["object_id"]) == key)
        self.selected_key = key
        self.object_text.set(str(row["object_id"]))
        self.x_text.set(str(row["x"]))
        self.y_text.set(str(row["y"]))
        self.visible_var.set(row["visible"])
        self.pending_point = None
        self.refresh()

    def delete_selected(self):
        if self.selected_key is None:
            self.status_text.set("Select a label in the list first.")
            return
        self.rows = [row for row in self.rows
                     if (row["frame"], row["object_id"]) != self.selected_key]
        self.selected_key = None
        self.dirty = True
        self.status_text.set("Label deleted in memory. Save CSV to persist changes.")
        self.refresh()

    def go(self, offset):
        self.frame_index = max(0, min(len(self.frames) - 1, self.frame_index + offset))
        self.selected_key = None
        self.pending_point = None
        self.refresh()

    def go_to_entry(self):
        try:
            frame = _strict_int(self.frame_text.get(), "frame")
            if not 0 <= frame < len(self.frames):
                raise ValueError(f"Frame must be between 0 and {len(self.frames)-1}")
        except ValueError as error:
            self.messagebox.showerror("Invalid frame", str(error))
            return
        self.frame_index = frame
        self.selected_key = None
        self.pending_point = None
        self.refresh()

    def save(self):
        try:
            count = save_labels(self.labels_path, self.rows, len(self.frames))
        except (OSError, TypeError, ValueError) as error:
            self.messagebox.showerror("Save failed", str(error))
            return
        self.dirty = False
        self.status_text.set(f"Saved {count} manual labels to {self.labels_path}.")

    def on_close(self):
        if self.dirty and not self.messagebox.askyesno(
                "Unsaved labels", "Discard unsaved changes and close?"):
            return
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, default=DEFAULT_FRAMES)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--csv", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--contact-sheet", type=Path, default=DEFAULT_CONTACT_SHEET)
    parser.add_argument("--all-frames-sheet", type=Path, default=DEFAULT_ALL_FRAMES_SHEET)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--prepare", action="store_true",
                        help="validate P4 files and create contact sheet plus empty template")
    args = parser.parse_args()
    try:
        frames, manifest = validate_p4_dataset(args.frames, args.manifest)
        if args.prepare:
            key_frames = [0, 1, 2, 48, 49, 50, 74, 75, 76, 88, 89, 90,
                          len(frames) - 3, len(frames) - 2, len(frames) - 1]
            representatives = [frames[index] for index in key_frames]
            contact = create_contact_sheet(representatives, args.contact_sheet,
                                           columns=5, tile_width=320)
            overview = create_contact_sheet(frames, args.all_frames_sheet)
            template = empty_template(args.template)
            print(f"Validated {len(frames)} P4 frames; representative sheet: {contact}; "
                  f"all-frame overview: {overview}; empty template: {template}")
            return
        import tkinter as tk
        root = tk.Tk()
        AnnotationApp(root, frames, args.csv)
        root.mainloop()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(2, f"FAILED: {error}\n")


if __name__ == "__main__":
    main()
