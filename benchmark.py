"""Generate reproducible test videos and score all three trackers."""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.optimize import linear_sum_assignment

from evaluation import METRICS, score_with_identity as score
from tracking import METHODS, associate, detect, encoder, hungarian, overlay, run_video, write_csv

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT, FPS = 320, 180, 15
# Scenario name -> number of frames.
SCENARIOS = {"separate": 43, "crossing": 43, "dense": 30, "noisy": 43}
NOISY_SIGMA, NOISY_SEED = 100, 1


def positions(name, frame):
    if name == "dense":
        # Two convoys with 16 px spacing, moving right (top) and left (bottom),
        # both accelerating from 6 to 11 px/frame. Once a step exceeds half the
        # spacing (8 px, from frame 16), the closest spot belongs to the object behind.
        shift = sum(6 + t // 5 for t in range(frame))
        right = [(15 + 16 * k + shift, 62) for k in range(3)]
        left = [(305 - 16 * k - shift, 118) for k in range(3)]
        return right + left
    return (
        (32 + 6 * frame, 66),
        (288 - 6 * frame, 105 if name == "separate" else 66),
        (85 + 2 * frame, 146 - frame // 3),
    )


def variants(name):
    """(method, blur) pairs to run; the noisy scenario also runs with smoothing."""
    blurs = (0.0, 1.5) if name == "noisy" else (0.0,)
    return [(method, blur) for blur in blurs for method in METHODS]


def label(method, blur):
    return f"{method}_blur" if blur else method


def render(name, noise=5.0, seed=9):
    """Yield (frame image, truth rows). noise is the Gaussian background sigma.

    "noisy" is the crossing video with Gaussian sensor noise (sigma 100) added
    to every pixel, identical to one run of the noise experiment.
    """
    if name == "noisy":
        rng = np.random.default_rng(NOISY_SEED)
        for image, rows in render("crossing"):
            noisy = image.astype(float) + rng.normal(0, NOISY_SIGMA, image.shape)
            yield np.clip(noisy, 0, 255).astype(np.uint8), rows
        return
    rng = np.random.default_rng(seed)
    yy, xx = np.ogrid[:HEIGHT, :WIDTH]
    radius = 5 if name == "dense" else 7
    for frame in range(SCENARIOS[name]):
        image = np.clip(25 + rng.normal(0, noise, (HEIGHT, WIDTH)), 0, 255).astype(np.uint8)
        rows = []
        for object_id, (x, y) in enumerate(positions(name, frame), 1):
            visible = not (name == "crossing" and object_id == 1 and 20 <= frame <= 23)
            rows.append((frame, object_id, x, y, int(visible)))
            if visible:
                image[(xx - x)**2 + (yy - y)**2 <= radius**2] = 218
        # Isolated bright pixels, removed by the morphological opening.
        for x, y in rng.integers((1, 1), (WIDTH - 1, HEIGHT - 1), (25, 2)):
            image[y, x] = 205
        yield image, rows


def generate(name):
    data = ROOT / "data"
    frames_dir = data / name
    frames_dir.mkdir(parents=True, exist_ok=True)
    truth = []
    with encoder(data / f"{name}.mp4", WIDTH, HEIGHT, FPS) as video:
        for frame, (image, rows) in enumerate(render(name)):
            truth.extend(rows)
            png = Image.fromarray(image)
            png.save(frames_dir / f"frame_{frame:03d}.png")
            video.stdin.write(png.convert("RGB").tobytes())
        video.stdin.close()
        if video.wait():
            raise RuntimeError("Unable to write sample video.")
    write_csv(data / f"{name}_truth.csv", ("frame", "object_id", "x", "y", "visible"), truth)
    return truth


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
    for name in SCENARIOS:
        truth = generate(name)
        output = ROOT / "results" / name
        for method, blur in variants(name):
            args = argparse.Namespace(video=ROOT / "data" / f"{name}.mp4", output=output,
                                      method=method, threshold=110, min_area=35, max_area=240, blur=blur,
                                      gate=24, max_missing=5)
            metrics, rows = score(truth, run_video(args))
            summary.append((name, label(method, blur), *metrics))
            write_csv(output / f"{label(method, blur)}_evaluation.csv",
                      ("frame", "object_id", "track_id", "error_px", "id_switch"), rows)
    write_csv(ROOT / "results/summary.csv", ("scenario", "method", *METRICS), summary)
    segmentation_panel()
    print((ROOT / "results/summary.csv").read_text())


if __name__ == "__main__":
    main()
