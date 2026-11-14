import csv
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.ground_truth_annotator import (
    CSV_FIELDS,
    create_contact_sheet,
    empty_template,
    load_labels,
    save_labels,
    sha256,
    upsert_label,
    validate_labels,
    validate_p4_dataset,
)


class GroundTruthAnnotatorTests(unittest.TestCase):
    def test_template_is_header_only_with_required_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = empty_template(Path(temporary) / "template.csv")
            with path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(rows, [list(CSV_FIELDS)])

    def test_upsert_edits_same_frame_id_and_preserves_id_across_frames(self):
        rows = upsert_label([], 0, 2, 10.5, 20.5, 1, 3)
        rows = upsert_label(rows, 0, 2, 11.5, 21.5, 0, 3)
        rows = upsert_label(rows, 1, 2, 12.5, 22.5, 1, 3)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], {"frame": 0, "object_id": 2,
                                   "x": 11.5, "y": 21.5, "visible": 0})
        self.assertEqual(rows[1]["object_id"], 2)
        self.assertEqual(rows[1]["frame"], 1)

    def test_validation_rejects_bounds_ids_visibility_and_duplicate(self):
        invalid = [
            {"frame": 3, "object_id": 1, "x": 0, "y": 0, "visible": 1},
            {"frame": 0, "object_id": 0, "x": 0, "y": 0, "visible": 1},
            {"frame": 0, "object_id": 1, "x": 320, "y": 0, "visible": 1},
            {"frame": 0, "object_id": 1, "x": 0, "y": float("nan"), "visible": 1},
            {"frame": 0, "object_id": 1, "x": 0, "y": 0, "visible": 2},
        ]
        for row in invalid:
            with self.subTest(row=row), self.assertRaises(ValueError):
                validate_labels([row], frame_count=3)
        duplicate = [
            {"frame": 0, "object_id": 1, "x": 1, "y": 2, "visible": 1},
            {"frame": 0, "object_id": 1, "x": 3, "y": 4, "visible": 1},
        ]
        with self.assertRaises(ValueError):
            validate_labels(duplicate, frame_count=3)

    def test_save_and_load_manual_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manual.csv"
            labels = [{"frame": 1, "object_id": 3, "x": 319.5,
                       "y": 179.5, "visible": 1}]
            self.assertEqual(save_labels(path, labels, 2), 1)
            loaded = load_labels(path, 2)
            self.assertEqual(loaded, labels)

    def test_p4_dataset_hashes_and_contact_sheet(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frame_dir = root / "frames"
            frame_dir.mkdir()
            records = []
            for index in range(2):
                path = frame_dir / f"frame_{index:03d}.png"
                Image.new("L", (320, 180), index * 30).save(path)
                records.append({"index": index, "file": path.name,
                                "width": 320, "height": 180, "mode": "L",
                                "sha256": sha256(path)})
            video = root / "lossless.mkv"
            video.write_bytes(b"fixture lossless bytes")
            manifest = {
                "frame_count": 2, "frames": records,
                "pixel_equality_verified": True, "lossless_file": video.name,
                "lossless_sha256": sha256(video),
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            frames, _ = validate_p4_dataset(frame_dir, manifest_path)
            sheet = create_contact_sheet(frames, root / "contact.png", columns=2)
            with Image.open(sheet) as image:
                self.assertEqual(image.size, (344, 126))
            (frame_dir / "frame_001.png").write_bytes(b"modified")
            with self.assertRaises(ValueError):
                validate_p4_dataset(frame_dir, manifest_path)


if __name__ == "__main__":
    unittest.main()
