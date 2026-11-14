"""Run the existing TrackMate Groovy script on P3 seed0 stress sequences.

This is a thin sequential launcher/validator; it does not implement detection
or tracking. Existing complete outputs are validated and skipped. The
separate_seed0 directory is protected and never modified by this runner.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIJI = Path("fiji-windows-x64.exe")
DEFAULT_FIJI_ROOT = DEFAULT_FIJI.parent
DEFAULT_OUTPUT = ROOT / "output/person1/fiji_stress"
DEFAULT_SCENARIOS = ("occlusion_seed0", "overlap_seed0", "turn_seed0", "illumination_seed0")
ALL_SCENARIOS = ("separate_seed0",) + DEFAULT_SCENARIOS
METHODS = {
    "nearest": "NEAREST_NEIGHBOR_TRACKER",
    "lap": "SIMPLE_SPARSE_LAP_TRACKER",
    "kalman": "KALMAN_TRACKER",
}
CSV_FIELDS = ("frame", "track_id", "x", "y")
FRAME_COUNT, WIDTH, HEIGHT = 80, 320, 180


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source_manifest(manifest_path, scenario):
    """Require this exact P3 scenario's 80 source PNGs to match its manifest."""
    expected_dir = f"data/stress/{scenario}"
    records = []
    with Path(manifest_path).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["scenario"] == scenario.removesuffix("_seed0") and row["seed"] == "0":
                records.append(row)
    records.sort(key=lambda row: int(row["frame"]))
    if len(records) != FRAME_COUNT:
        raise ValueError(f"P3 manifest has {len(records)} rows for {scenario}; expected 80")
    for index, row in enumerate(records):
        relative = Path(row["file_path"])
        path = ROOT / relative
        if (relative.as_posix() != f"{expected_dir}/frame_{index:03d}.png"
                or int(row["frame"]) != index
                or int(row["width"]) != WIDTH or int(row["height"]) != HEIGHT
                or row["mode"] != "L" or not path.is_file()):
            raise ValueError(f"Invalid P3 manifest entry for {scenario} frame {index}")
        if sha256(path) != row["sha256"]:
            raise ValueError(f"P3 SHA256 mismatch: {path}")
    return records


def _float_attr(node, name, expected):
    value = node.get(name)
    if value is None or not math.isclose(float(value), expected, rel_tol=0, abs_tol=1e-9):
        raise ValueError(f"XML {node.tag}.{name} expected {expected}; got {value}")


def validate_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(CSV_FIELDS):
            raise ValueError(f"{path}: CSV header must be {','.join(CSV_FIELDS)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path}: no tracking rows")
    seen, frames, ids = set(), set(), set()
    for line, row in enumerate(rows, start=2):
        try:
            frame, track_id = int(row["frame"]), int(row["track_id"])
            x, y = float(row["x"]), float(row["y"])
        except (TypeError, ValueError) as error:
            raise ValueError(f"{path}:{line}: invalid frame/track_id/coordinate") from error
        if not 0 <= frame < FRAME_COUNT:
            raise ValueError(f"{path}:{line}: frame outside 0..79")
        if not math.isfinite(x) or not 0 <= x < WIDTH:
            raise ValueError(f"{path}:{line}: x outside [0,320)")
        if not math.isfinite(y) or not 0 <= y < HEIGHT:
            raise ValueError(f"{path}:{line}: y outside [0,180)")
        key = (frame, track_id)
        if key in seen:
            raise ValueError(f"{path}:{line}: duplicate frame/track_id {key}")
        seen.add(key)
        frames.add(frame)
        ids.add(track_id)
    return {"rows": len(rows), "frames": len(frames),
            "frame_min": min(frames), "frame_max": max(frames),
            "missing_frames": sorted(set(range(FRAME_COUNT)) - frames),
            "track_ids": len(ids)}


def validate_xml(path, scenario, method, trackmate_version):
    root = ET.parse(path).getroot()
    if root.tag != "TrackMate":
        raise ValueError(f"{path}: unexpected root element {root.tag}")
    version = root.get("version")
    if not version or (trackmate_version and version != trackmate_version):
        raise ValueError(f"{path}: TrackMate version {version!r}, expected {trackmate_version!r}")
    settings = root.find("Settings")
    if settings is None:
        raise ValueError(f"{path}: missing Settings")
    image = settings.find("ImageData")
    basic = settings.find("BasicSettings")
    if image is None or basic is None:
        raise ValueError(f"{path}: missing image/basic settings")
    for key, expected in (("width", WIDTH), ("height", HEIGHT), ("nframes", FRAME_COUNT)):
        if image.get(key) != str(expected):
            raise ValueError(f"{path}: image {key}={image.get(key)}, expected {expected}")
    if not math.isclose(float(image.get("timeinterval", "nan")), 1 / 15,
                        rel_tol=0, abs_tol=1e-9):
        raise ValueError(f"{path}: unexpected frame interval {image.get('timeinterval')}")
    if image.get("filename") != scenario:
        raise ValueError(f"{path}: image name {image.get('filename')!r} != {scenario!r}")
    if basic.get("tstart") != "0" or basic.get("tend") != str(FRAME_COUNT - 1):
        raise ValueError(f"{path}: expected frame interval 0..79")

    detector = settings.find("DetectorSettings")
    if (detector is None or detector.get("DETECTOR_NAME") != "THRESHOLD_DETECTOR"
            or detector.get("INTENSITY_THRESHOLD") != "110.0"
            or detector.get("SIMPLIFY_CONTOURS") != "false"):
        raise ValueError(f"{path}: threshold detector settings differ from requested config")
    filters = settings.find("SpotFilterCollection")
    filter_config = sorted((f.get("feature"), f.get("value"), f.get("isabove"))
                           for f in filters.findall("Filter")) if filters is not None else []
    if filter_config != [("QUALITY", "240.0", "false"), ("QUALITY", "35.0", "true")]:
        raise ValueError(f"{path}: expected quality filters 35..240; got {filter_config}")

    tracker = settings.find("TrackerSettings")
    if tracker is None or tracker.get("TRACKER_NAME") != METHODS[method]:
        raise ValueError(f"{path}: unexpected tracker factory for {method}")
    if method == "lap":
        linking, gap = tracker.find("Linking"), tracker.find("GapClosing")
        if linking is None or gap is None or gap.get("ALLOW_GAP_CLOSING") != "true":
            raise ValueError(f"{path}: Simple LAP link/gap settings missing")
        _float_attr(linking, "LINKING_MAX_DISTANCE", 24)
        _float_attr(gap, "GAP_CLOSING_MAX_DISTANCE", 36)
        if gap.get("MAX_FRAME_GAP") != "6":
            raise ValueError(f"{path}: Simple LAP max frame gap must be 6")
    else:
        _float_attr(tracker, "LINKING_MAX_DISTANCE", 24)
        if method == "kalman":
            _float_attr(tracker, "KALMAN_SEARCH_RADIUS", 24)
            if tracker.get("MAX_FRAME_GAP") != "6":
                raise ValueError(f"{path}: Kalman max frame gap must be 6")

    spots = root.find("./Model/AllSpots")
    if spots is None:
        raise ValueError(f"{path}: missing model spots")
    spot_frames = {int(frame.get("frame")) for frame in spots.findall("SpotsInFrame")}
    if spot_frames != set(range(FRAME_COUNT)):
        raise ValueError(f"{path}: XML does not store all input frames 0..79")
    visible_spots = [spot for spot in spots.iter("Spot") if spot.get("VISIBILITY") == "1"]
    for spot in visible_spots:
        x, y = float(spot.get("POSITION_X", "nan")), float(spot.get("POSITION_Y", "nan"))
        if not math.isfinite(x) or not 0 <= x < WIDTH or not math.isfinite(y) or not 0 <= y < HEIGHT:
            raise ValueError(f"{path}: visible XML spot has invalid coordinates")
    return {"trackmate_version": version, "tracker_factory": tracker.get("TRACKER_NAME"),
            "xml_frames": image.get("nframes"), "xml_spot_frames": len(spot_frames),
            "xml_visible_spots": len(visible_spots)}


def validate_scenario(output_dir, scenario, trackmate_version):
    summary = {"scenario": scenario, "csv_count": 0, "xml_count": 0, "trackers": {}}
    expected_files = {f"{scenario}_{method}.{ext}"
                      for method in METHODS for ext in ("csv", "xml")}
    actual_files = {path.name for path in output_dir.iterdir() if path.is_file()
                    and path.suffix.lower() in (".csv", ".xml")}
    if actual_files != expected_files:
        raise ValueError(f"{scenario}: expected exactly 3 result CSV and 3 XML; "
                         f"found {sorted(actual_files)}")
    for method in METHODS:
        stem = f"{scenario}_{method}"
        csv_path, xml_path = output_dir / f"{stem}.csv", output_dir / f"{stem}.xml"
        if not csv_path.is_file() or not xml_path.is_file():
            raise ValueError(f"{scenario}: missing CSV/XML pair for {method}")
        csv_info = validate_csv(csv_path)
        xml_info = validate_xml(xml_path, scenario, method, trackmate_version)
        if csv_info["rows"] != xml_info["xml_visible_spots"]:
            raise ValueError(f"{scenario}/{method}: CSV rows do not match visible XML spots")
        summary["csv_count"] += 1
        summary["xml_count"] += 1
        summary["trackers"][method] = {**csv_info, **xml_info}
    return summary


def complete_or_empty(directory, scenario, trackmate_version):
    files = [p for p in directory.iterdir() if p.is_file()]
    expected = {f"{scenario}_{method}.{ext}" for method in METHODS for ext in ("csv", "xml")}
    existing_results = {p.name for p in files if p.suffix.lower() in (".csv", ".xml")}
    if not existing_results and not files:
        return None
    if existing_results != expected:
        raise FileExistsError(
            f"Refusing partial/unknown existing output in {directory}: "
            f"found={sorted(existing_results)}, expected={sorted(expected)}")
    return validate_scenario(directory, scenario, trackmate_version)


def wait_for_outputs(directory, scenario, timeout, stable_seconds=2.0):
    expected = [directory / f"{scenario}_{method}.{ext}"
                for method in METHODS for ext in ("csv", "xml")]
    deadline, last_signature, stable_since = time.monotonic() + timeout, None, None
    while time.monotonic() < deadline:
        if all(path.is_file() and path.stat().st_size > 0 for path in expected):
            signature = tuple((path.name, path.stat().st_size, path.stat().st_mtime_ns)
                              for path in expected)
            if signature == last_signature:
                if stable_since is None:
                    stable_since = time.monotonic()
                elif time.monotonic() - stable_since >= stable_seconds:
                    return expected
            else:
                last_signature, stable_since = signature, time.monotonic()
        time.sleep(0.5)
    missing = [str(path) for path in expected if not path.is_file()]
    raise TimeoutError(f"Timed out waiting for stable Fiji outputs; missing={missing}")


def fiji_metadata(fiji_root):
    jar = fiji_root / "jars/TrackMate-8.1.6.jar"
    if not jar.is_file():
        raise FileNotFoundError(f"Expected TrackMate 8.1.6 jar not found: {jar}")
    imagej_jars = sorted((fiji_root / "jars").glob("ij-*.jar"))
    if not imagej_jars:
        raise FileNotFoundError(f"ImageJ core jar not found under {fiji_root / 'jars'}")
    imagej_jar = imagej_jars[-1]
    java_files = list((fiji_root / "java").glob("**/bin/java.exe"))
    java_version = "unknown"
    if java_files:
        result = subprocess.run([str(java_files[0]), "-version"], capture_output=True,
                                text=True, timeout=15)
        java_version = (result.stderr or result.stdout).splitlines()[0]
    launcher = fiji_root / "fiji-windows-x64.exe"
    return {"imagej_jar": str(imagej_jar),
            "imagej_version": imagej_jar.stem.removeprefix("ij-"),
            "fiji_launcher_sha256": sha256(launcher) if launcher.is_file() else "",
            "trackmate_jar": str(jar), "trackmate_jar_sha256": sha256(jar),
            "trackmate_version_expected": "8.1.6", "java_executable": str(java_files[0]) if java_files else "",
            "java_version": java_version}


def write_run_log(path, scenario, command, returncode, stdout, stderr,
                  source_dir, output_dir, commit, validation, error=None):
    def as_text(value):
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value) if value else "(empty)"

    lines = [
        f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}",
        f"scenario: {scenario}",
        f"source_dir: {source_dir}",
        f"output_dir: {output_dir}",
        f"commit: {commit}",
        f"command: {subprocess.list2cmdline(command)}",
        f"exit_code: {returncode}",
        "--- stdout ---", as_text(stdout),
        "--- stderr ---", as_text(stderr),
    ]
    if validation is not None:
        lines.extend(["--- validation ---", json.dumps(validation, sort_keys=True)])
    if error:
        lines.extend(["--- error ---", str(error)])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_one(fiji_exe, script, source_dir, output_dir, scenario, timeout):
    params = (f"framesDir='{source_dir.as_posix()}',"
              f"outputDir='{output_dir.as_posix()}',detectorChoice='threshold'")
    command = [str(fiji_exe), "--headless", "--run", str(script), params]
    start = time.monotonic()
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                timeout=timeout, check=False)
        returncode, stdout, stderr = result.returncode, result.stdout, result.stderr
        if returncode != 0:
            raise RuntimeError(f"Fiji launcher exited {returncode}")
        wait_for_outputs(output_dir, scenario, timeout=max(1, timeout - (time.monotonic() - start)))
        validation = validate_scenario(output_dir, scenario, "8.1.6")
        write_run_log(output_dir / "run.log", scenario, command, returncode, stdout, stderr,
                      source_dir, output_dir, current_commit(), validation)
        return validation
    except Exception as error:
        code = locals().get("returncode", "not-returned")
        stdout = locals().get("stdout", "")
        stderr = locals().get("stderr", "")
        write_run_log(output_dir / "run.log", scenario, command, code, stdout, stderr,
                      source_dir, output_dir, current_commit(), None, error)
        raise


def current_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def current_branch():
    try:
        return subprocess.run(["git", "branch", "--show-current"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fiji", type=Path, default=DEFAULT_FIJI,
                        help="path to Fiji's native Windows launcher")
    parser.add_argument("--script", type=Path, default=ROOT / "TrackMate_Nhom9.groovy")
    parser.add_argument("--manifest", type=Path, default=ROOT / "output/person1/stress_manifest.csv")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--protected-separate", type=Path,
                        default=DEFAULT_OUTPUT / "separate_seed0",
                        help="existing separate_seed0 output to validate without writing")
    parser.add_argument("--timeout", type=int, default=600,
                        help="maximum seconds per scenario")
    parser.add_argument("--trackmate-version", default="8.1.6")
    parser.add_argument("--scenarios", nargs="+", choices=DEFAULT_SCENARIOS,
                        default=list(DEFAULT_SCENARIOS),
                        help="seed0 runs only; separate_seed0 is protected/excluded")
    args = parser.parse_args(argv)
    fiji_exe = args.fiji.resolve()
    script = args.script.resolve()
    output_root = args.output_root.resolve()
    protected_path = args.protected_separate.resolve()
    manifest = args.manifest.resolve()
    try:
        if args.timeout <= 0:
            raise ValueError("timeout must be positive")
        if not fiji_exe.is_file() or not script.is_file() or not manifest.is_file():
            raise FileNotFoundError("Fiji launcher, Groovy script, or P3 manifest is missing")
        metadata = fiji_metadata(fiji_exe.parent)
        if metadata["trackmate_version_expected"] != args.trackmate_version:
            raise ValueError("Runner TrackMate version does not match the installed jar")
        output_root.mkdir(parents=True, exist_ok=True)
        for control_file in ("runner.log", "validation_summary.csv"):
            if (output_root / control_file).exists():
                raise FileExistsError(f"Refusing to overwrite existing run artifact: {output_root / control_file}")

        # The already completed separate_seed0 is read-only and must be valid.
        protected = protected_path
        if not protected.is_dir():
            raise FileNotFoundError(f"Protected separate_seed0 output is missing: {protected}")
        protected_summary = validate_scenario(protected, "separate_seed0", args.trackmate_version)

        prepared = []
        for scenario in args.scenarios:
            source = (ROOT / "data/stress" / scenario).resolve()
            output = (output_root / scenario).resolve()
            if not source.is_dir():
                raise FileNotFoundError(f"Source directory missing for {scenario}")
            output.mkdir(parents=True, exist_ok=True)
            verify_source_manifest(manifest, scenario)
            previous = complete_or_empty(output, scenario, args.trackmate_version)
            prepared.append((scenario, source, output, previous))

        metadata.update({"fiji_root": str(fiji_exe.parent), "fiji_launcher": str(fiji_exe),
                         "fiji_build": "portable distribution (no single Fiji release tag in launcher)",
                         "branch": current_branch(), "commit": current_commit(), "script": str(script),
                         "p3_manifest": str(manifest), "source_sha256_manifest_verified": True,
                         "protected_separate_output": str(protected),
                         "source_paths": {scenario: str((ROOT / "data/stress" / scenario).resolve())
                                          for scenario in ALL_SCENARIOS},
                         "parameters": {"detector": "threshold", "threshold": 110,
                            "quality_min": 35, "quality_max": 240,
                            "linking_max_distance_px": 24,
                            "simple_lap_gap_closing_max_distance_px": 36,
                            "simple_lap_max_frame_gap": 6,
                            "kalman_search_radius_px": 24,
                            "kalman_max_frame_gap": 6}})
        metadata_path = output_root / "run_metadata.json"
        if metadata_path.exists():
            previous_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if previous_metadata != metadata:
                raise FileExistsError(f"Refusing to overwrite different run metadata: {metadata_path}")
        else:
            metadata_path.write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        log_lines = [f"run_started_utc: {datetime.now(timezone.utc).isoformat()}",
                     f"commit: {metadata['commit']}", f"fiji_launcher: {fiji_exe}",
                     f"trackmate_version: {args.trackmate_version}",
                     f"protected_separate_seed0: validated_read_only csv=3 xml=3",
                     f"selected_scenarios: {','.join(args.scenarios)}"]
        results = []
        for scenario, source, output, previous in prepared:
            if previous is not None:
                log_lines.append(f"{scenario}: pre-existing complete output validated; skipped")
                results.append(previous)
                continue
            verify_source_manifest(manifest, scenario)
            validation = run_one(fiji_exe, script, source, output, scenario, args.timeout)
            log_lines.append(f"{scenario}: launcher exit=0; validated csv=3 xml=3")
            results.append(validation)

        # Include all five scenarios when available. Never write inside separate_seed0.
        all_summaries = [protected_summary]
        for scenario in DEFAULT_SCENARIOS:
            directory = output_root / scenario
            if directory.is_dir() and all((directory / f"{scenario}_{m}.{ext}").is_file()
                                          for m in METHODS for ext in ("csv", "xml")):
                all_summaries.append(validate_scenario(directory, scenario, args.trackmate_version))
        total_csv = sum(row["csv_count"] for row in all_summaries)
        total_xml = sum(row["xml_count"] for row in all_summaries)
        summary_path = output_root / "validation_summary.csv"
        with summary_path.open("w", newline="", encoding="utf-8") as stream:
            fields = ("scenario", "tracker", "csv_rows", "csv_frames", "csv_frame_min",
                      "csv_frame_max", "csv_missing_frames", "csv_track_ids",
                      "trackmate_version", "tracker_factory", "xml_frames", "xml_spot_frames")
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for entry in all_summaries:
                for tracker, values in entry["trackers"].items():
                    writer.writerow({"scenario": entry["scenario"], "tracker": tracker,
                        "csv_rows": values["rows"], "csv_frames": values["frames"],
                        "csv_frame_min": values["frame_min"], "csv_frame_max": values["frame_max"],
                        "csv_missing_frames": ";".join(map(str, values["missing_frames"])),
                        "csv_track_ids": values["track_ids"],
                        "trackmate_version": values["trackmate_version"],
                        "tracker_factory": values["tracker_factory"],
                        "xml_frames": values["xml_frames"],
                        "xml_spot_frames": values["xml_spot_frames"]})
        log_lines.extend([f"total_validated_csv={total_csv}", f"total_validated_xml={total_xml}",
                          f"validation_summary: {summary_path}"])
        if total_csv == 15 and total_xml == 15:
            log_lines.append("status: PASS; all five scenarios validated (3 CSV + 3 XML each)")
        else:
            log_lines.append("status: PARTIAL; one or more scenarios remain incomplete")
        (output_root / "runner.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        print("\n".join(log_lines[-5:]))
        if total_csv != 15 or total_xml != 15:
            return 1
        return 0
    except Exception as error:
        print(f"BLOCKED/FAILED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
