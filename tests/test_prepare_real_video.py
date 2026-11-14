import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.prepare_real_video import (fps_filter, nearest_source_timestamp,
                                        transform_metadata, validate_pngs)


class PrepareRealVideoTests(unittest.TestCase):
    def test_aspect_ratio_transform_centers_padding(self):
        transform = transform_metadata(640, 360)
        self.assertEqual(transform["scaled_size_nominal"], [320, 180])
        self.assertEqual((transform["pad_left"], transform["pad_top"]), (0, 0))
        portrait = transform_metadata(180, 320)
        self.assertEqual(portrait["scaled_size_nominal"], [101, 180])
        self.assertEqual(portrait["pad_left"], 109)

    def test_filter_sets_fps_gray_and_letterboxes(self):
        chain = fps_filter()
        self.assertIn("fps=15", chain)
        self.assertIn("setpts=PTS-STARTPTS", chain)
        self.assertIn("pad=320:180", chain)
        self.assertIn("format=gray", chain)

    def test_timestamp_mapping_accounts_for_nonzero_source_start(self):
        self.assertEqual(nearest_source_timestamp(1 / 15, [10.0, 10.067, 10.134], 10.0), 10.067)

    def test_png_sequence_accepts_exact_geometry_and_contiguous_indices(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for index in range(2):
                Image.new("L", (320, 180), index).save(folder / f"frame_{index:03d}.png")
            self.assertEqual(len(validate_pngs(folder)), 2)

    def test_png_sequence_rejects_gap_and_wrong_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            Image.new("L", (320, 180)).save(folder / "frame_000.png")
            Image.new("L", (320, 180)).save(folder / "frame_002.png")
            with self.assertRaises(RuntimeError):
                validate_pngs(folder)
            (folder / "frame_002.png").unlink()
            Image.new("RGB", (320, 180)).save(folder / "frame_001.png")
            with self.assertRaises(RuntimeError):
                validate_pngs(folder)


if __name__ == "__main__":
    unittest.main()
