"""Generate two reproducible videos and score all three trackers."""
import argparse
import csv
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.optimize import linear_sum_assignment

from tracking import METHODS, associate, detect, encoder, hungarian, overlay, run_video, write_csv

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT, FPS, FRAMES = 320, 180, 15, 43


def generate(name):
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    frames_dir = data / name
    frames_dir.mkdir(exist_ok=True)
    rng = np.random.default_rng(9)
    yy, xx = np.ogrid[:HEIGHT, :WIDTH]
    truth = []
    with encoder(data / f"{name}.mp4", WIDTH, HEIGHT, FPS) as video:
        for frame in range(FRAMES):
            image = np.clip(25 + rng.normal(0, 5, (HEIGHT, WIDTH)), 0, 255).astype(np.uint8)
            positions = (
                (32 + 6 * frame, 66),
                (288 - 6 * frame, 105 if name == "separate" else 66),
                (85 + 2 * frame, 146 - frame // 3),
            )
            for object_id, (x, y) in enumerate(positions, 1):
                visible = not (name == "crossing" and object_id == 1 and 20 <= frame <= 23)
                truth.append((frame, object_id, x, y, int(visible)))
                if visible:
                    image[(xx - x)**2 + (yy - y)**2 <= 7**2] = 218
            for x, y in rng.integers((1, 1), (WIDTH - 1, HEIGHT - 1), (25, 2)):
                image[y, x] = 205
            png = Image.fromarray(image)
            png.save(frames_dir / f"frame_{frame:03d}.png")
            video.stdin.write(png.convert("RGB").tobytes())
        video.stdin.close()
        if video.wait():
            raise RuntimeError("Unable to write sample video.")
    write_csv(data / f"{name}_truth.csv", ("frame", "object_id", "x", "y", "visible"), truth)
    return truth


def score(truth, observations):
    last_id, rows, errors = {}, [], []
    switches = missed = false_positive = 0
    for frame in range(FRAMES):
        gt = [(i, x, y) for f, i, x, y, visible in truth if f == frame and visible]
        pred = [(i, x, y) for f, i, x, y in observations if f == frame]
        a = np.asarray([p[1:] for p in gt]).reshape(-1, 2)
        b = np.asarray([p[1:] for p in pred]).reshape(-1, 2)
        distances = np.linalg.norm(a[:, None] - b[None, :], axis=2)
        pairs = associate(distances, 8, "hungarian")
        missed += len(gt) - len(pairs)
        false_positive += len(pred) - len(pairs)
        for i, j in pairs:
            object_id, track_id = gt[i][0], pred[j][0]
            switched = object_id in last_id and last_id[object_id] != track_id
            switches += switched
            last_id[object_id] = track_id
            errors.append(distances[i, j])
            rows.append((frame, object_id, track_id, round(distances[i, j], 4), int(switched)))
    rmse = round(float(np.sqrt(np.mean(np.square(errors)))), 4) if errors else ""
    return (len(errors), missed, false_positive, switches, len({r[1] for r in observations}), rmse), rows


def segmentation_panel():
    image = Image.open(ROOT / "data/crossing/frame_021.png")
    mask, centers = detect(np.asarray(image), 110, 35, 240)
    marked = overlay(np.asarray(image), [], "Centroids", 21)
    marker = ImageDraw.Draw(marked)
    for x, y in centers:
        marker.line((x - 6, y, x + 6, y), fill="#4ae3c2", width=2)
        marker.line((x, y - 6, x, y + 6), fill="#4ae3c2", width=2)
    canvas = Image.new("RGB", (3 * WIDTH + 16, HEIGHT + 28), "#101923")
    for index, (tile, label) in enumerate(((image, "01  INPUT FRAME"), (
            Image.fromarray(mask.astype(np.uint8) * 255), "02  BINARY MASK"), (marked, "03  CENTROIDS"))):
        x = index * (WIDTH + 8)
        canvas.paste(tile, (x, 28))
        ImageDraw.Draw(canvas).text((x + 7, 7), label, fill="white")
    canvas.save(ROOT / "results/segmentation.png")


def main():
    # Cross-check the educational Hungarian solver against SciPy on random costs.
    rng = np.random.default_rng(19)
    for size in range(1, 13):
        for _ in range(20):
            cost = rng.integers(-10, 80, (size, size))
            ref = cost[linear_sum_assignment(cost)].sum()
            assert sum(cost[i, j] for i, j in hungarian(cost)) == ref
    assert len(associate(np.array([[2., 3.], [4., 9.]]), 5, "nearest")) == 1
    assert len(associate(np.array([[2., 3.], [4., 9.]]), 5, "hungarian")) == 2
    summary = []
    for name in ("separate", "crossing"):
        truth = generate(name)
        output = ROOT / "results" / name
        for method in METHODS:
            args = argparse.Namespace(video=ROOT / "data" / f"{name}.mp4", output=output,
                                      method=method, threshold=110, min_area=35, max_area=240,
                                      gate=24, max_missing=5)
            metrics, rows = score(truth, run_video(args))
            summary.append((name, method, *metrics))
            write_csv(output / f"{method}_evaluation.csv",
                      ("frame", "object_id", "track_id", "error_px", "id_switch"), rows)
    fields = ("scenario", "method", "matched", "missed", "false_positive", "id_switches", "track_ids", "rmse_px")
    write_csv(ROOT / "results/summary.csv", fields, summary)
    segmentation_panel()
    print((ROOT / "results/summary.csv").read_text())


if __name__ == "__main__":
    main()
