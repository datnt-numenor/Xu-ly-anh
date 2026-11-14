"""Prepare a real video as timestamped 320x180 grayscale PNGs and FFV1.

Run from the repository root:
    python scripts/prepare_real_video.py

Outputs are refused if any destination already exists. No synthetic frames are
created by this utility.
"""
import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image


WIDTH, HEIGHT, FPS, MAX_FRAMES = 320, 180, 15, 150


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_tools():
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise RuntimeError("Missing required executable(s): " + ", ".join(missing))


def run_json(command):
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def source_metadata(source):
    return run_json([
        "ffprobe", "-v", "error", "-show_streams", "-show_format",
        "-show_frames", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,time_base,duration,nb_frames:format=duration,format_name:frame=best_effort_timestamp_time",
        "-of", "json", str(source),
    ])


def transform_metadata(width, height):
    scale = min(WIDTH / width, HEIGHT / height)
    scaled_width = min(WIDTH, max(1, math.floor(width * scale + 1e-9)))
    scaled_height = min(HEIGHT, max(1, math.floor(height * scale + 1e-9)))
    left = (WIDTH - scaled_width) // 2
    top = (HEIGHT - scaled_height) // 2
    return {
        "source_size": [width, height], "target_size": [WIDTH, HEIGHT],
        "scale_nominal": scale, "scaled_size_nominal": [scaled_width, scaled_height],
        "pad_left": left, "pad_top": top,
        "source_to_output": {"x": f"{scale:.12g}*x+{left}", "y": f"{scale:.12g}*y+{top}"},
        "note": "Centered black padding; nominal scale, coordinate origin at top-left; pixel resampling may round scaled dimensions.",
    }


def fps_filter():
    return (f"setpts=PTS-STARTPTS,fps={FPS},scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease:force_divisible_by=1,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,format=gray")


def nearest_source_timestamp(target_time, source_times, source_origin=0.0):
    if not source_times:
        return None
    normalized_target = source_origin + target_time
    return min(source_times, key=lambda timestamp: abs(timestamp - normalized_target))


def validate_pngs(png_dir, expected_max=MAX_FRAMES):
    files = sorted(png_dir.glob("frame_*.png"))
    if not files or len(files) > expected_max:
        raise RuntimeError(f"Expected 1..{expected_max} PNG frames, found {len(files)}")
    expected = [f"frame_{i:03d}.png" for i in range(len(files))]
    if [p.name for p in files] != expected:
        raise RuntimeError("PNG sequence must be contiguous and start at frame_000.png")
    for path in files:
        with Image.open(path) as image:
            if image.mode != "L" or image.size != (WIDTH, HEIGHT):
                raise RuntimeError(f"Invalid PNG mode/size: {path.name}: {image.mode} {image.size}")
            image.verify()
    return files


def verify_lossless(video, png_files):
    process = subprocess.run([
        "ffmpeg", "-v", "error", "-i", str(video), "-f", "rawvideo",
        "-pix_fmt", "gray", "-fps_mode", "passthrough", "pipe:1",
    ], check=True, capture_output=True)
    expected_bytes = WIDTH * HEIGHT
    raw = process.stdout
    if len(raw) != expected_bytes * len(png_files):
        raise RuntimeError(f"Decoded lossless video has {len(raw) // expected_bytes} frames/partial data; expected {len(png_files)}")
    for index, png in enumerate(png_files):
        with Image.open(png) as image:
            expected = image.tobytes()
        actual = raw[index * expected_bytes:(index + 1) * expected_bytes]
        if actual != expected:
            raise RuntimeError(f"Pixel mismatch at frame {index}")


def prepare(source, png_dir, lossless, manifest, commit="unknown"):
    require_tools()
    source, png_dir, lossless, manifest = map(Path, (source, png_dir, lossless, manifest))
    if not source.is_file():
        raise FileNotFoundError(f"Real video source not found: {source}")
    for target in (png_dir, lossless, manifest):
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite existing path: {target}")
    metadata = source_metadata(source)
    streams = metadata.get("streams", [])
    if not streams or not streams[0].get("width") or not streams[0].get("height"):
        raise RuntimeError("ffprobe did not return a usable video stream")

    png_dir.parent.mkdir(parents=True, exist_ok=True)
    lossless.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="real_video_", dir=str(png_dir.parent)) as temporary:
        temporary = Path(temporary)
        staged_png = temporary / "frames"
        staged_png.mkdir()
        staged_video = temporary / "scene01_lossless.mkv"
        staged_manifest = temporary / "manifest.json"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-v", "error", "-i", str(source),
            "-vf", fps_filter(), "-frames:v", str(MAX_FRAMES), "-start_number", "0",
            str(staged_png / "frame_%03d.png"),
        ], check=True)
        png_files = validate_pngs(staged_png)
        subprocess.run([
            "ffmpeg", "-hide_banner", "-v", "error", "-framerate", str(FPS),
            "-i", str(staged_png / "frame_%03d.png"), "-frames:v", str(len(png_files)),
            "-c:v", "ffv1", "-level", "3", "-pix_fmt", "gray", str(staged_video),
        ], check=True)
        verify_lossless(staged_video, png_files)

        frame_records = []
        source_frames = metadata.get("frames", [])
        source_times = [float(frame["best_effort_timestamp_time"]) for frame in source_frames
                        if frame.get("best_effort_timestamp_time") is not None]
        source_origin = min(source_times) if source_times else 0.0
        for index, path in enumerate(png_files):
            target_time = index / FPS
            selected_source_time = nearest_source_timestamp(target_time, source_times, source_origin)
            frame_records.append({
                "index": index, "file": path.name, "target_timestamp_seconds": target_time,
                "nearest_source_timestamp_seconds": selected_source_time,
                "sha256": sha256(path), "width": WIDTH, "height": HEIGHT, "mode": "L",
            })
        ffmpeg_version = subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, text=True).stdout.splitlines()[0]
        manifest_data = {
            "source_path": str(source), "source_sha256": sha256(source), "source_probe": metadata,
            "target_fps": FPS, "max_frames": MAX_FRAMES, "frame_count": len(png_files),
            "frame_index_origin": 0, "coordinate_transform": transform_metadata(streams[0]["width"], streams[0]["height"]),
            "source_timestamp_origin_seconds": source_origin,
            "ffmpeg_version": ffmpeg_version, "commit": commit,
            "lossless_file": lossless.name, "lossless_sha256": sha256(staged_video),
            "pixel_equality_verified": True, "frames": frame_records,
        }
        staged_manifest.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

        # Destinations were checked before processing; recheck before publishing.
        for target in (png_dir, lossless, manifest):
            if target.exists():
                raise FileExistsError(f"Refusing to overwrite existing path: {target}")
        shutil.move(str(staged_png), str(png_dir))
        shutil.move(str(staged_video), str(lossless))
        shutil.move(str(staged_manifest), str(manifest))
    return len(frame_records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/real/raw_scene01.mp4"))
    parser.add_argument("--png-dir", type=Path, default=Path("data/real/scene01"))
    parser.add_argument("--lossless", type=Path, default=Path("data/real/scene01_lossless.mkv"))
    parser.add_argument("--manifest", type=Path, default=Path("data/real/scene01_manifest.json"))
    args = parser.parse_args()
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        count = prepare(args.input, args.png_dir, args.lossless, args.manifest, commit)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"BLOCKED/FAILED: {error}\n")
    print(f"Prepared and verified {count} frames: {args.png_dir}, {args.lossless}, {args.manifest}")


if __name__ == "__main__":
    main()
