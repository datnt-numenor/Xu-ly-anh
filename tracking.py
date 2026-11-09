"""Threshold segmentation and centroid tracking in grayscale videos."""
import argparse
import csv
import json
import subprocess
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.optimize import linear_sum_assignment

METHODS = ("nearest", "hungarian", "kalman")
COLORS = ("#ff845e", "#4ae3c2", "#f7cc55", "#bca2ff", "#6cbfff")


def write_csv(path, columns, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def otsu_threshold(frame):
    """8-bit Otsu threshold; choose the first maximum for deterministic plateaus."""
    hist = np.bincount(frame.ravel(), minlength=256).astype(float)
    weight = hist.cumsum()
    moment = (hist * np.arange(256)).cumsum()
    denominator = weight * (weight[-1] - weight)
    variance = np.zeros(256)
    valid = denominator > 0
    variance[valid] = (moment[-1] * weight[valid] - moment[valid] * weight[-1]) ** 2 / denominator[valid]
    return int(np.argmax(variance)) if valid.any() else int(frame.flat[0])


def detect(frame, threshold, min_area, max_area, blur=0.0, opening=True, connectivity=8):
    """Threshold, open, label and return (mask, centroids as x, y).

    blur > 0 applies a Gaussian filter with that sigma first to suppress noise.
    opening=False and connectivity=4 mimic TrackMate's thresholding detector.
    """
    if frame.ndim != 2 or frame.dtype != np.uint8 or frame.size == 0:
        raise ValueError("Detector expects a nonempty 2D uint8 grayscale frame.")
    threshold = otsu_threshold(frame) if threshold == "otsu" else threshold
    if blur > 0:
        frame = ndimage.gaussian_filter(frame.astype(float), blur)
    mask = frame > threshold
    if opening:
        mask = ndimage.binary_opening(mask, structure=np.ones((3, 3)))
    neighbours = np.ones((3, 3)) if connectivity == 8 else ndimage.generate_binary_structure(2, 1)
    labels, count = ndimage.label(mask, structure=neighbours)
    areas = np.bincount(labels.ravel(), minlength=count + 1)
    indices = np.flatnonzero((areas >= min_area) & (areas <= max_area))
    indices = indices[indices != 0]
    centers_yx = ndimage.center_of_mass(mask, labels, indices)
    return mask, np.asarray(centers_yx, dtype=float).reshape(-1, 2)[:, ::-1]


def hungarian(cost):
    """Minimum-cost square assignment using potentials and augmenting paths."""
    n = len(cost)
    u, v = np.zeros(n + 1), np.zeros(n + 1)
    row_at_column = np.zeros(n + 1, dtype=int)
    previous = np.zeros(n + 1, dtype=int)
    for row in range(1, n + 1):
        row_at_column[0] = row
        slack = np.full(n + 1, np.inf)
        used = np.zeros(n + 1, dtype=bool)
        column = 0
        while True:
            used[column] = True
            active_row = row_at_column[column]
            free = np.flatnonzero(~used)
            reduced = cost[active_row - 1, free - 1] - u[active_row] - v[free]
            better = reduced < slack[free]
            slack[free[better]] = reduced[better]
            previous[free[better]] = column
            next_column = free[np.argmin(slack[free])]
            delta = slack[next_column]
            u[row_at_column[used]] += delta
            v[used] -= delta
            slack[free] -= delta
            column = next_column
            if row_at_column[column] == 0:
                break
        while column != 0:
            prior_column = previous[column]
            row_at_column[column] = row_at_column[prior_column]
            column = prior_column
    return [(row - 1, col) for col, row in enumerate(row_at_column[1:])]


def associate(distances, gate, method, solver="educational"):
    if method not in METHODS or solver not in ("educational", "scipy"):
        raise ValueError("Unknown method or assignment solver.")
    tracks, spots = distances.shape
    if not tracks or not spots:
        return []
    if method == "nearest":
        candidates = sorted((distances[i, j], i, j)
                            for i, j in zip(*np.where(distances <= gate)))
        rows, cols, matches = set(), set(), []
        for _, i, j in candidates:
            if i not in rows and j not in cols:
                rows.add(i)
                cols.add(j)
                matches.append((i, j))
        return matches

    # Dummy rows/columns permit unmatched spots and tracks.
    # The penalty makes maximum valid cardinality the first priority.
    penalty = (min(tracks, spots) + 1) * (gate + 1)
    size = tracks + spots
    cost = np.zeros((size, size))
    cost[:tracks, :spots] = np.where(distances <= gate, distances, penalty * (size + 1))
    cost[:tracks, spots:] = penalty
    cost[tracks:, :spots] = penalty
    pairs = hungarian(cost) if solver == "educational" else zip(*linear_sum_assignment(cost))
    return [(i, j) for i, j in pairs if i < tracks and j < spots and distances[i, j] <= gate]


F = np.eye(4)
F[0, 2] = F[1, 3] = 1
H = np.eye(4)[:2]
G = np.vstack((0.5 * np.eye(2), np.eye(2)))
Q = 0.10 * (G @ G.T)
R = 1.0 * np.eye(2)


@dataclass
class Track:
    id: int
    state: np.ndarray
    covariance: np.ndarray = field(default_factory=lambda: np.diag([4., 4., 100., 100.]))
    misses: int = 0
    points: deque = field(default_factory=lambda: deque(maxlen=30))

    def predict(self):
        self.state = F @ self.state
        self.covariance = F @ self.covariance @ F.T + Q

    def observe(self, frame, point, use_kalman):
        if use_kalman:
            gain = np.linalg.solve(H @ self.covariance @ H.T + R, H @ self.covariance).T
            self.state += gain @ (point - H @ self.state)
            remainder = np.eye(4) - gain @ H
            self.covariance = remainder @ self.covariance @ remainder.T + gain @ R @ gain.T
        else:
            self.state[:2] = point
        self.misses = 0
        self.points.append((frame, *point))


class Tracker:
    def __init__(self, method, gate, max_missing, solver="educational"):
        if method not in METHODS or solver not in ("educational", "scipy"):
            raise ValueError("Unknown method or assignment solver.")
        if not np.isfinite(gate) or gate <= 0 or max_missing < 0 or int(max_missing) != max_missing:
            raise ValueError("Expected positive finite gate and nonnegative integer max_missing.")
        self.solver = solver
        self.last_frame = None
        self.method = method
        self.gate = gate
        self.max_missing = max_missing
        self.active = []
        self.next_id = 1

    def update(self, frame, spots):
        if not np.isfinite(frame) or frame < 0 or int(frame) != frame:
            raise ValueError("Frame must be a nonnegative integer.")
        if self.last_frame is not None and frame != self.last_frame + 1:
            raise ValueError("Call update for every consecutive frame, including empty detections.")
        spots = np.asarray(spots, dtype=float)
        if spots.size == 0:
            spots = np.empty((0, 2))
        if spots.ndim != 2 or spots.shape[1] != 2 or not np.isfinite(spots).all():
            raise ValueError("Spots must be a finite Nx2 array.")
        self.last_frame = frame
        use_kalman = self.method == "kalman"
        if use_kalman:
            for track in self.active:
                track.predict()
        positions = np.asarray([t.state[:2] for t in self.active]).reshape(-1, 2)
        distances = np.linalg.norm(positions[:, None] - spots[None, :], axis=2)
        matches = associate(distances, self.gate, self.method, self.solver)
        assigned_tracks = {i for i, _ in matches}
        assigned_spots = {j for _, j in matches}
        visible = []
        for i, j in matches:
            track = self.active[i]
            track.observe(frame, spots[j], use_kalman)
            visible.append(track)
        for i, track in enumerate(self.active):
            track.misses += i not in assigned_tracks
        self.active = [t for t in self.active if t.misses <= self.max_missing]
        for j, point in enumerate(spots):
            if j in assigned_spots:
                continue
            track = Track(self.next_id, np.r_[point, 0., 0.])
            self.next_id += 1
            track.observe(frame, point, False)
            self.active.append(track)
            visible.append(track)
        return visible


def video_info(path):
    command = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height,avg_frame_rate", "-of", "json", str(path)]
    stream = json.loads(subprocess.check_output(command))["streams"][0]
    rate = stream["avg_frame_rate"]
    if rate == "0/0":
        raise ValueError("Video frame rate is unavailable.")
    return stream["width"], stream["height"], rate


def video_frames(path, width, height):
    command = ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0",
               "-an", "-f", "rawvideo", "-pix_fmt", "gray", "-threads", "1", "-"]
    with subprocess.Popen(command, stdout=subprocess.PIPE) as decoder:
        while raw := decoder.stdout.read(width * height):
            if len(raw) != width * height:
                raise RuntimeError("Truncated video frame.")
            yield np.frombuffer(raw, dtype=np.uint8).reshape(height, width)
        if decoder.wait():
            raise RuntimeError("FFmpeg failed to decode the video.")


def encoder(path, width, height, rate):
    command = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{width}x{height}", "-r", str(rate), "-i", "-", "-an",
               "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p",
               "-c:v", "libx264", "-movflags", "+faststart", str(path)]
    return subprocess.Popen(command, stdin=subprocess.PIPE)


def overlay(frame, tracks, label, index):
    image = Image.fromarray(frame).convert("RGB")
    draw = ImageDraw.Draw(image)
    for track in tracks:
        color = COLORS[(track.id - 1) % len(COLORS)]
        recent = list(track.points)
        for (t0, x0, y0), (t1, x1, y1) in zip(recent, recent[1:]):
            if t1 == t0 + 1:
                draw.line((x0, y0, x1, y1), fill=color, width=2)
        _, x, y = recent[-1]
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), outline=color, width=2)
        draw.text((x + 8, y - 13), f"ID {track.id}", fill=color, stroke_width=1, stroke_fill="black")
    draw.rectangle((0, 0, image.width, 22), fill="#101923")
    draw.text((7, 5), f"{label.upper()}  |  FRAME {index:03d}", fill="white")
    return image


def run_video(args, collect=True):
    """Stream CSV/video output; collect observations only for benchmark callers."""
    from contextlib import ExitStack
    width, height, rate = video_info(args.video)
    args.output.mkdir(parents=True, exist_ok=True)
    tracker = Tracker(args.method, args.gate, args.max_missing, getattr(args, "solver", "educational"))
    blur = getattr(args, "blur", 0.0)
    stem = f"{args.method}_blur" if blur else args.method
    observations = []
    with ExitStack() as stack:
        def csv_sink(name, columns):
            handle = stack.enter_context((args.output / name).open("w", newline="", encoding="utf-8"))
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(columns)
            return writer
        detection_csv = csv_sink("detections.csv", ("frame", "x", "y"))
        observation_csv = csv_sink(f"{stem}.csv", ("frame", "track_id", "x", "y"))
        state_csv = csv_sink(f"{stem}_states.csv",
                             ("frame", "track_id", "state_x", "state_y", "vx_px_per_frame",
                              "vy_px_per_frame", "observed", "misses"))
        output = stack.enter_context(encoder(args.output / f"{stem}.mp4", width, height, rate))
        try:
            for index, frame in enumerate(video_frames(args.video, width, height)):
                _, points = detect(frame, args.threshold, args.min_area, args.max_area, blur)
                tracks = tracker.update(index, points)
                detection_csv.writerows((index, *point) for point in points)
                rows = [(index, t.id, *t.points[-1][1:]) for t in tracks]
                observation_csv.writerows(rows)
                state_csv.writerows((index, t.id, *t.state, int(t.misses == 0), t.misses)
                                    for t in tracker.active)
                if collect:
                    observations.extend(rows)
                output.stdin.write(overlay(frame, tracks, stem, index).tobytes())
        finally:
            output.stdin.close()
        if output.wait():
            raise RuntimeError("FFmpeg failed to encode the overlay.")
    return observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--method", choices=METHODS, default="kalman")
    parser.add_argument("--threshold", default="110", help="Integer in [0,255], or otsu")
    parser.add_argument("--solver", choices=("educational", "scipy"), default="educational")
    parser.add_argument("--blur", type=float, default=0.0,
                        help="Gaussian sigma applied before thresholding (0 = off)")
    parser.add_argument("--min-area", type=int, default=35)
    parser.add_argument("--max-area", type=int, default=240)
    parser.add_argument("--gate", type=float, default=24)
    parser.add_argument("--max-missing", type=int, default=5)
    args = parser.parse_args()
    if args.threshold != "otsu":
        try:
            args.threshold = int(args.threshold)
        except ValueError:
            parser.error("Expected an integer threshold or otsu.")
    if (args.threshold != "otsu" and not 0 <= args.threshold <= 255) or not 0 < args.min_area <= args.max_area:
        parser.error("Expected threshold in [0, 255] and 0 < min-area <= max-area.")
    if not 0 <= args.blur <= 10:
        parser.error("Expected blur in [0, 10].")
    if not np.isfinite(args.gate) or args.gate <= 0 or args.max_missing < 0:
        parser.error("Expected a positive finite gate and nonnegative max-missing.")
    run_video(args, collect=False)


if __name__ == "__main__":
    main()
