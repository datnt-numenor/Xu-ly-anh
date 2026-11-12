"""Web demo gom các tính năng của dự án vào một trang.

Chạy:  python webapp/app.py   rồi mở http://127.0.0.1:5000

Server gọi trực tiếp tracking.py và evaluation.py nên kết quả trên web
trùng với kết quả chạy dòng lệnh (benchmark_png.py) cùng tham số.
"""
import base64
import csv
import io
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections import OrderedDict
from pathlib import Path
from time import perf_counter

import numpy as np
from flask import Flask, abort, jsonify, request, send_file, send_from_directory
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation import METRICS, score_with_identity  # noqa: E402
from tracking import METHODS, Tracker, associate, detect, otsu_threshold  # noqa: E402

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

UPLOAD_DIR = Path(tempfile.gettempdir()) / "xla_nhom9_uploads"
MAX_UPLOAD_FRAMES = 300
MAX_UPLOAD_WIDTH = 640

SCENARIOS = OrderedDict([
    ("separate", dict(title="Separate", note="3 vật đi tách nhau. Nearest neighbor là đủ.")),
    ("crossing", dict(title="Crossing",
                      note="2 vật đi ngược chiều, vật 1 bị ẩn ở frame 20–23 đúng lúc giao nhau. Cần Kalman.")),
    ("dense", dict(title="Dense",
                   note="2 đoàn 3 vật cách nhau 16 px, tăng tốc 6→11 px/frame. Cần Hungarian.")),
    ("noisy", dict(title="Noisy", note="Crossing cộng nhiễu Gauss σ = 100. Cần detector chịu nhiễu.")),
])

_frame_cache = OrderedDict()


def _source_dir(source):
    if source in SCENARIOS:
        return ROOT / "data" / source
    if re.fullmatch(r"upload-[0-9a-f]{8}", source) and (UPLOAD_DIR / source).is_dir():
        return UPLOAD_DIR / source
    abort(404, f"Không có nguồn dữ liệu '{source}'.")


def load_frames(source, noise=0.0, seed=1):
    """Grayscale uint8 frames, optionally with seeded Gaussian sensor noise."""
    key = (source, round(float(noise), 2), int(seed))
    if key in _frame_cache:
        _frame_cache.move_to_end(key)
        return _frame_cache[key]
    if noise > 0:
        rng = np.random.default_rng(int(seed))
        frames = [np.clip(f.astype(float) + rng.normal(0, noise, f.shape), 0, 255).astype(np.uint8)
                  for f in load_frames(source)]
    else:
        frames = [np.asarray(Image.open(p).convert("L"))
                  for p in sorted(_source_dir(source).glob("frame_*.png"))]
    if not frames:
        abort(404, "Nguồn dữ liệu không có frame nào.")
    _frame_cache[key] = frames
    while len(_frame_cache) > 24:
        _frame_cache.popitem(last=False)
    return frames


def load_truth(source):
    path = ROOT / "data" / f"{source}_truth.csv"
    if source not in SCENARIOS or not path.exists():
        return None
    return [tuple(int(v) for v in row)
            for row in np.loadtxt(path, delimiter=",", skiprows=1, dtype=int)]


def source_info(source):
    frames = load_frames(source)
    info = dict(id=source, frames=len(frames), height=int(frames[0].shape[0]),
                width=int(frames[0].shape[1]), has_truth=load_truth(source) is not None)
    info.update(SCENARIOS.get(source, dict(title=source.replace("upload-", "Tải lên "),
                                           note="Dữ liệu người dùng tải lên (không có ground truth).")))
    return info


def png_bytes(array):
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def data_url(array):
    return "data:image/png;base64," + base64.b64encode(png_bytes(array)).decode()


def detection_params(body):
    threshold = body.get("threshold", 110)
    if threshold != "otsu":
        threshold = int(threshold)
        if not 0 <= threshold <= 255:
            abort(400, "Ngưỡng phải nằm trong [0, 255] hoặc là 'otsu'.")
    params = dict(threshold=threshold, min_area=int(body.get("min_area", 35)),
                  max_area=int(body.get("max_area", 240)), blur=float(body.get("blur", 0.0)),
                  opening=bool(body.get("opening", True)), connectivity=int(body.get("connectivity", 8)))
    if not 0 < params["min_area"] <= params["max_area"] or not 0 <= params["blur"] <= 10:
        abort(400, "Cần 0 < min_area ≤ max_area và blur trong [0, 10].")
    if params["connectivity"] not in (4, 8):
        abort(400, "Connectivity phải là 4 hoặc 8.")
    return params


def noise_params(body):
    noise = float(body.get("noise", 0.0))
    if not 0 <= noise <= 200:
        abort(400, "σ nhiễu phải nằm trong [0, 200].")
    return noise, int(body.get("seed", 1))


# ---------------------------------------------------------------- pages / static

@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/results/<path:path>")
def results_file(path):
    return send_from_directory(ROOT / "results", path)


@app.get("/media/<path:path>")
def data_file(path):
    if not path.endswith(".mp4"):
        abort(404)
    return send_from_directory(ROOT / "data", path)


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(413)
def json_error(error):
    return jsonify(error=getattr(error, "description", str(error))), error.code


# ---------------------------------------------------------------- data sources

@app.get("/api/sources")
def sources():
    items = [source_info(s) for s in SCENARIOS]
    if UPLOAD_DIR.is_dir():
        for folder in sorted(UPLOAD_DIR.iterdir(), key=lambda p: p.stat().st_mtime):
            if folder.is_dir() and any(folder.glob("frame_*.png")):
                items.append(source_info(folder.name))
    return jsonify(items)


@app.get("/api/frame/<source>/<int:index>.png")
def frame_png(source, index):
    noise = float(request.args.get("noise", 0))
    seed = int(request.args.get("seed", 1))
    frames = load_frames(source, min(max(noise, 0), 200), seed)
    if not 0 <= index < len(frames):
        abort(404)
    response = send_file(io.BytesIO(png_bytes(frames[index])), mimetype="image/png")
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@app.get("/api/truth/<source>")
def truth(source):
    rows = load_truth(source) or []
    return jsonify([dict(frame=f, id=i, x=x, y=y, visible=v) for f, i, x, y, v in rows])


# ---------------------------------------------------------------- detection

@app.post("/api/detect")
def detect_frame():
    body = request.get_json(force=True)
    source = body.get("source", "crossing")
    noise, seed = noise_params(body)
    params = detection_params(body)
    frames = load_frames(source, noise, seed)
    index = int(body.get("frame", 0))
    if not 0 <= index < len(frames):
        abort(400, "Frame nằm ngoài phạm vi.")
    frame = frames[index]

    start = perf_counter()
    mask, spots = detect(frame, **params)
    elapsed = (perf_counter() - start) * 1000

    # Replicate the intermediate steps of detect() for display only.
    used_threshold = otsu_threshold(frame) if params["threshold"] == "otsu" else params["threshold"]
    work = ndimage.gaussian_filter(frame.astype(float), params["blur"]) if params["blur"] > 0 else frame
    raw_mask = work > used_threshold
    structure = (np.ones((3, 3)) if params["connectivity"] == 8
                 else ndimage.generate_binary_structure(2, 1))
    labels, count = ndimage.label(mask, structure=structure)
    areas = np.bincount(labels.ravel(), minlength=count + 1)
    components = []
    if count:
        centers = ndimage.center_of_mass(mask, labels, range(1, count + 1))
        for label, (cy, cx) in enumerate(centers, 1):
            area = int(areas[label])
            components.append(dict(x=float(cx), y=float(cy), area=area,
                                   accepted=params["min_area"] <= area <= params["max_area"]))
    components.sort(key=lambda c: (not c["accepted"], -c["area"]))

    hist = np.bincount(frame.ravel(), minlength=256).tolist()
    truth_rows = [dict(id=i, x=x, y=y) for f, i, x, y, v in (load_truth(source) or [])
                  if f == index and v]
    return jsonify(
        threshold=int(used_threshold), otsu=otsu_threshold(frame), histogram=hist,
        smoothed=data_url(np.clip(work, 0, 255).astype(np.uint8)) if params["blur"] > 0 else None,
        raw_mask=data_url((raw_mask * 255).astype(np.uint8)),
        mask=data_url((mask * 255).astype(np.uint8)),
        spots=[dict(x=float(x), y=float(y)) for x, y in spots],
        components=components[:200], component_count=int(count),
        truth=truth_rows, elapsed_ms=round(elapsed, 2))


# ---------------------------------------------------------------- tracking

def run_tracking(frames, spots_per_frame, method, gate, max_missing, solver):
    tracker = Tracker(method, gate, max_missing, solver)
    observations, states = [], []
    start = perf_counter()
    for index, spots in enumerate(spots_per_frame):
        for track in tracker.update(index, spots):
            observations.append((index, track.id, *map(float, track.points[-1][1:])))
        states.extend((index, t.id, float(t.state[0]), float(t.state[1]),
                       float(t.state[2]), float(t.state[3]), int(t.misses == 0))
                      for t in tracker.active)
    elapsed = (perf_counter() - start) * 1000 / max(len(frames), 1)
    return observations, states, elapsed


@app.post("/api/track")
def track():
    body = request.get_json(force=True)
    source = body.get("source", "crossing")
    noise, seed = noise_params(body)
    params = detection_params(body)
    methods = [m for m in body.get("methods", ["kalman"]) if m in METHODS] or ["kalman"]
    gate = float(body.get("gate", 24))
    max_missing = int(body.get("max_missing", 5))
    solver = body.get("solver", "educational")
    if not np.isfinite(gate) or gate <= 0 or max_missing < 0 or solver not in ("educational", "scipy"):
        abort(400, "Tham số tracker không hợp lệ.")

    frames = load_frames(source, noise, seed)
    start = perf_counter()
    spots_per_frame = [detect(f, **params)[1] for f in frames]
    detect_ms = (perf_counter() - start) * 1000 / len(frames)
    truth_rows = load_truth(source)

    results = {}
    for method in methods:
        observations, states, track_ms = run_tracking(frames, spots_per_frame, method, gate,
                                                      max_missing, solver)
        result = dict(observations=observations, states=states, track_ms=round(track_ms, 4))
        if truth_rows is not None:
            metrics, matches = score_with_identity(truth_rows, observations)
            result["metrics"] = dict(zip(METRICS, metrics))
            result["switches"] = [dict(frame=f, object=o, track=t) for f, o, t, _, s in matches if s]
        results[method] = result
    return jsonify(
        source=source_info(source),
        detections=[[[float(x), float(y)] for x, y in spots] for spots in spots_per_frame],
        truth=[r for r in (truth_rows or []) if r[4]],
        detect_ms=round(detect_ms, 4), results=results)


# ---------------------------------------------------------------- association playground

@app.post("/api/associate")
def associate_points():
    body = request.get_json(force=True)
    tracks = np.asarray(body.get("tracks", []), dtype=float).reshape(-1, 2)
    spots = np.asarray(body.get("spots", []), dtype=float).reshape(-1, 2)
    gate = float(body.get("gate", 24))
    if len(tracks) > 12 or len(spots) > 12 or gate <= 0:
        abort(400, "Tối đa 12 track và 12 spot, gate > 0.")
    distances = np.linalg.norm(tracks[:, None] - spots[None, :], axis=2) if len(tracks) and len(spots) \
        else np.zeros((len(tracks), len(spots)))
    out = {}
    for method in ("nearest", "hungarian"):
        start = perf_counter()
        matches = associate(distances, gate, method)
        out[method] = dict(matches=[[int(i), int(j)] for i, j in matches],
                           cost=round(float(sum(distances[i, j] for i, j in matches)), 3),
                           us=round((perf_counter() - start) * 1e6, 1))
    # Reference check against SciPy on the same gated problem.
    # Ties may yield different pairs with equal cost, so compare cardinality and cost.
    scipy_matches = associate(distances, gate, "hungarian", solver="scipy")
    scipy_cost = float(sum(distances[i, j] for i, j in scipy_matches))
    out["scipy_agrees"] = bool(len(scipy_matches) == len(out["hungarian"]["matches"])
                               and abs(scipy_cost - out["hungarian"]["cost"]) < 1e-2)
    out["distances"] = np.round(distances, 2).tolist()
    return jsonify(out)


# ---------------------------------------------------------------- upload

def _resize(image):
    if image.width > MAX_UPLOAD_WIDTH:
        height = round(image.height * MAX_UPLOAD_WIDTH / image.width)
        image = image.resize((MAX_UPLOAD_WIDTH, height), Image.BILINEAR)
    return image


@app.post("/api/upload")
def upload():
    files = [f for f in request.files.getlist("files") if f.filename]
    if not files:
        abort(400, "Chưa chọn tệp.")
    source = f"upload-{uuid.uuid4().hex[:8]}"
    folder = UPLOAD_DIR / source
    folder.mkdir(parents=True, exist_ok=True)
    try:
        videos = [f for f in files if Path(f.filename).suffix.lower() in
                  (".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v")]
        if videos:
            if not shutil.which("ffmpeg"):
                abort(400, "Cần cài FFmpeg (có trong PATH) để đọc video. "
                           "Có thể tải lên chuỗi ảnh PNG/JPG thay thế.")
            video_path = folder / ("input" + Path(videos[0].filename).suffix.lower())
            videos[0].save(video_path)
            command = ["ffmpeg", "-v", "error", "-i", str(video_path),
                       "-vf", f"scale='min({MAX_UPLOAD_WIDTH},iw)':-2,format=gray",
                       "-frames:v", str(MAX_UPLOAD_FRAMES), str(folder / "frame_%03d.png")]
            result = subprocess.run(command, capture_output=True, text=True)
            video_path.unlink(missing_ok=True)
            if result.returncode:
                abort(400, "FFmpeg không giải mã được video: " + result.stderr[-300:])
            # ffmpeg numbers from 1; keep zero-based names like data/.
            for i, path in enumerate(sorted(folder.glob("frame_*.png"))):
                path.rename(folder / f"frame_{i:03d}.png")
        else:
            images = sorted(files, key=lambda f: f.filename)[:MAX_UPLOAD_FRAMES]
            size = None
            for i, file in enumerate(images):
                try:
                    image = _resize(Image.open(file.stream).convert("L"))
                except Exception:
                    abort(400, f"Không đọc được ảnh {file.filename}.")
                size = size or image.size
                if image.size != size:
                    image = image.resize(size, Image.BILINEAR)
                image.save(folder / f"frame_{i:03d}.png")
        if not any(folder.glob("frame_*.png")):
            abort(400, "Không trích được frame nào.")
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return jsonify(source_info(source))


# ---------------------------------------------------------------- saved results

def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@app.get("/api/results")
def saved_results():
    results = ROOT / "results"
    shots = {}
    screenshot_root = results / "fiji" / "screenshots"
    if screenshot_root.is_dir():
        for folder in sorted(screenshot_root.iterdir()):
            shots[folder.name] = [f"fiji/screenshots/{folder.name}/{p.name}"
                                  for p in sorted(folder.glob("*.png"))]
    videos = {}
    for scenario in SCENARIOS:
        order = lambda p: (p.stem.endswith("_blur"), METHODS.index(p.stem.removesuffix("_blur"))
                           if p.stem.removesuffix("_blur") in METHODS else 9)
        videos[scenario] = [f"{scenario}/{p.name}"
                            for p in sorted((results / scenario).glob("*.mp4"), key=order)]

    def table(name):
        path = results / name
        return read_csv(path) if path.exists() else []

    return jsonify(
        python=table("summary.csv"), fiji=table("fiji/summary.csv"),
        timing=table("timing_png.csv"), sweep=table("sweep_png.csv"),
        noise=table("noise_sweep.csv"), stress=table("stress/aggregate.csv"),
        figures=[f"figures/{p.name}" for p in sorted((results / "figures").glob("*.png"))],
        report_figures=[f"figures/report/{p.name}"
                        for p in sorted((results / "figures" / "report").glob("*.png"))],
        screenshots=shots, videos=videos)


if __name__ == "__main__":
    import argparse
    import webbrowser
    parser = argparse.ArgumentParser(description="Web demo nhóm 9")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not args.no_browser:
        webbrowser.open(f"http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
