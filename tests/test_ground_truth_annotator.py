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
from scripts.gt_review_gui import propagate_id_change, save_review_state
from scripts.validate_ground_truth_full import validate_ground_truth_bundle


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

    def test_propagate_id_change_reassign_and_swap(self):
        rows = [
            {"frame": 70, "object_id": 1, "x": 10.0, "y": 20.0, "visible": 1, "review_timestamp": ""},
            {"frame": 71, "object_id": 1, "x": 11.0, "y": 21.0, "visible": 1, "review_timestamp": ""},
            {"frame": 71, "object_id": 2, "x": 50.0, "y": 60.0, "visible": 1, "review_timestamp": ""},
        ]
        # Reassign ID 1 -> 5 on frame 70 only
        reassigned = propagate_id_change(rows, 1, 5, 70, 70, mode="reassign")
        self.assertEqual(reassigned[0]["object_id"], 5)
        self.assertEqual(reassigned[1]["object_id"], 1)
        # Reassigning 1 -> 2 on frame 71 must fail due to collision unless mode="swap"
        with self.assertRaises(ValueError):
            propagate_id_change(rows, 1, 2, 71, 71, mode="reassign")
        swapped = propagate_id_change(rows, 1, 2, 71, 71, mode="swap")
        f71_ids = {r["object_id"]: r["x"] for r in swapped if r["frame"] == 71}
        self.assertEqual(f71_ids[2], 11.0)
        self.assertEqual(f71_ids[1], 50.0)

    def test_validate_ground_truth_bundle_on_workspace_output(self):
        output_dir = Path("output/ground_truth_real")
        if not (
            output_dir.is_dir()
            and (output_dir / "annotation_manifest.json").is_file()
            and Path("data/real/scene01/frame_000.png").is_file()
        ):
            self.skipTest("Unversioned P4 PNG sequence data/real/scene01 is not present in CI checkout.")
        result = validate_ground_truth_bundle(output_dir)
        self.assertTrue(result["structural_pass"])
        self.assertTrue(result["auto_draft_pass"])
        self.assertFalse(result["full_gt_pass"])

    def test_scene02_verified_pilot_ground_truth_integrity(self):
        manual_csv = Path("data/real/scene02_ground_truth_manual.csv")
        reviewed_csv = Path("output/ground_truth_real/scene02/reviewed_gt.csv")
        frame_status_csv = Path("output/ground_truth_real/scene02/frame_review_status.csv")
        self.assertTrue(manual_csv.is_file(), f"Missing committed GT CSV: {manual_csv}")
        self.assertTrue(reviewed_csv.is_file(), f"Missing committed reviewed CSV: {reviewed_csv}")
        self.assertTrue(frame_status_csv.is_file(), f"Missing committed frame status CSV: {frame_status_csv}")
        rows = load_labels(manual_csv, frame_count=124)
        reviewed = load_labels(reviewed_csv, frame_count=124)
        self.assertEqual(rows, reviewed)
        self.assertEqual(len(rows), 129)
        self.assertEqual(sorted({r["frame"] for r in rows}), list(range(65, 85)))
        self.assertEqual(sorted({r["object_id"] for r in rows}), list(range(1, 11)))
        with frame_status_csv.open(newline="", encoding="utf-8") as stream:
            f_rows = list(csv.DictReader(stream))
        self.assertEqual(len(f_rows), 20)
        self.assertTrue(all(int(r["frame_reviewed_by_human"]) == 1 for r in f_rows))
        self.assertTrue(all(r["review_timestamp"].strip() != "" for r in f_rows))


if __name__ == "__main__":
    unittest.main()
