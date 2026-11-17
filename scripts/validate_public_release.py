"""Validate or refresh public evidence from the future Git tree (the index)."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "output/person1/public_release/public_evidence_manifest.json"
SIDECAR = ROOT / "output/person1/public_release/public_evidence_manifest.sha256"
PERSONAL_PATH = re.compile(r"(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\s<>\"']+")
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)|!\[[^\]]*\]\(([^)]+)\)")
EXCLUDED_PREFIXES = (
    "data/real/", "output/real_suitability/", "output/person1/real_video_tracking/_samples/",
)
ALLOWED_REAL_EXACT = {
    "data/real/scene02_ground_truth_manual.csv",
    "data/real/scene02_manifest.json",
}
EXCLUDED_NAMES = {
    "raw_scene01.mp4", "raw_scene02.mp4", "scene01_lossless.mkv", "scene02_lossless.mkv",
    "scene01_manifest.json", "evidence_manifest.json", "overlay_samples.png",
}
EXCLUDED_EXACT = {"output/person1/final/report.md"}
TEXT_SUFFIXES = {".md", ".py", ".json", ".csv", ".xml", ".txt", ".yml", ".yaml", ".log", ".groovy"}


def is_allowed_public_path(path: str) -> bool:
    """Return True only if path is permitted in the public release allowlist."""
    p = Path(path)
    if p.is_absolute() or ".." in p.parts:
        return False
    if path in EXCLUDED_EXACT or p.name in EXCLUDED_NAMES:
        return False
    if path.startswith(EXCLUDED_PREFIXES) and path not in ALLOWED_REAL_EXACT:
        return False
    return True


def digest(data):
    return hashlib.sha256(data).hexdigest()


_INDEX_BLOBS = None


def index_blob(path):
    """Return Git stage-0 bytes through one binary cat-file batch."""
    global _INDEX_BLOBS
    if _INDEX_BLOBS is None:
        entries = {}
        records = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=ROOT)
        for record in records.split(b"\0"):
            if not record:
                continue
            metadata, raw_path = record.split(b"\t", 1)
            _, oid, stage = metadata.decode("ascii").split()
            assert stage == "0", raw_path
            entries[raw_path.decode("utf-8")] = oid
        request = "".join(oid + "\n" for oid in entries.values()).encode("ascii")
        process = subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        output, _ = process.communicate(request)
        assert process.returncode == 0, "git cat-file failed"
        blobs, offset = {}, 0
        for indexed_path, expected_oid in entries.items():
            end = output.find(b"\n", offset)
            assert end >= 0, indexed_path
            oid, kind, raw_size = output[offset:end].decode("ascii").split()
            size = int(raw_size)
            assert oid == expected_oid and kind == "blob", indexed_path
            blob = output[end + 1:end + 1 + size]
            assert len(blob) == size and output[end + 1 + size:end + 2 + size] == b"\n", indexed_path
            blobs[indexed_path] = blob
            offset = end + 2 + size
        assert offset == len(output), "unexpected cat-file output"
        _INDEX_BLOBS = blobs
    return _INDEX_BLOBS[path]


def refresh_index_manifest():
    """Rewrite only manifest metadata and its detached hash from index bytes."""
    manifest = json.loads(MANIFEST.read_bytes())
    for row in manifest["files"]:
        data = index_blob(row["path"])
        row["size_bytes"] = len(data)
        row["sha256"] = digest(data)
    manifest["total_bytes"] = sum(row["size_bytes"] for row in manifest["files"])
    raw = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    MANIFEST.write_bytes(raw)
    SIDECAR.write_bytes(f"{digest(raw)}  public_evidence_manifest.json\n".encode("ascii"))
    print(json.dumps({"refreshed_entries": len(manifest["files"]),
                      "payload_bytes": manifest["total_bytes"]}, sort_keys=True))


def main():
    manifest_bytes = index_blob(MANIFEST.relative_to(ROOT).as_posix())
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    sidecar = index_blob(SIDECAR.relative_to(ROOT).as_posix()).decode("ascii").strip().split()
    assert sidecar == [digest(manifest_bytes), MANIFEST.name], "detached manifest checksum mismatch"
    assert manifest["format"] == "public-experiment-evidence-v1"
    rows = manifest["files"]
    paths = {row["path"] for row in rows}
    assert len(paths) == len(rows) == manifest["file_count"], "duplicate/count mismatch"
    assert sum(row["size_bytes"] for row in rows) == manifest["total_bytes"], "size total mismatch"
    assert "output/person1/public_release/public_evidence_manifest.json" not in paths
    assert "output/person1/public_release/public_evidence_manifest.sha256" not in paths

    # Every future-tree file is accounted for. The two metadata files are
    # tracked but deliberately excluded from the payload array.
    tracked = set(subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")) - {""}
    reserved = {MANIFEST.relative_to(ROOT).as_posix(), SIDECAR.relative_to(ROOT).as_posix()}
    assert tracked == paths | reserved, f"future Git tree/allowlist mismatch: {sorted(tracked ^ (paths | reserved))[:10]}"

    total, content_by_path = 0, {}
    for row in rows:
        path = row["path"]
        assert not Path(path).is_absolute() and ".." not in Path(path).parts, path
        assert is_allowed_public_path(path), path
        data = index_blob(path)
        assert digest(data) == row["sha256"], f"checksum mismatch: {path}"
        assert len(data) == row["size_bytes"], f"size mismatch: {path}"
        total += len(data)
        if Path(path).suffix.lower() in TEXT_SUFFIXES:
            text = data.decode("utf-8", errors="replace")
            assert not PERSONAL_PATH.search(text), f"personal absolute path in {path}"
            content_by_path[path] = text
    assert total == manifest["total_bytes"]

    # All local Markdown links resolve to another allowlisted package file or
    # a directory containing allowlisted files. The public index is a declared
    # special self-reference and is checksum-verified above.
    for source, text in content_by_path.items():
        if not source.lower().endswith(".md"):
            continue
        for match in LINK.finditer(text):
            target = match.group(1) or match.group(2)
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            raw = unquote(target.split("#", 1)[0])
            if not raw:
                continue
            resolved = (ROOT / source).parent.joinpath(raw).resolve()
            rel = resolved.relative_to(ROOT.resolve()).as_posix()
            if rel == "output/person1/public_release/public_evidence_manifest.json":
                assert rel in tracked
                continue
            if rel == "output/person1/public_release/public_evidence_manifest.sha256":
                assert rel in tracked
                continue
            if rel in paths:
                continue
            assert any(item.startswith(rel.rstrip("/") + "/") for item in paths), (source, target, rel)

    stage_paths = set(index_blob(manifest["stage_paths_file"]).decode("utf-8-sig").splitlines())
    assert len(stage_paths) == manifest["stage_path_count"]
    assert stage_paths == {row["path"] for row in rows if row["origin"] == "working_tree"} | reserved
    assert "data/real/scene01_lossless.mkv" not in paths
    assert not any(p.startswith("output/person1/final/figures/d1_06") or
                   p.endswith("p5_real_overlay_samples.png") or
                   (p.startswith("output/person1/real_video_tracking/") and
                    Path(p).suffix.lower() in {".mp4", ".png", ".jpg", ".jpeg"})
                   for p in paths)
    for metadata_path in reserved:
        assert not PERSONAL_PATH.search(index_blob(metadata_path).decode("utf-8", errors="replace")), metadata_path
    print(json.dumps({"status": "PASS", "files": len(rows), "bytes": total,
                      "metadata_tracked": len(reserved), "mismatches": 0, "missing": 0,
                      "stage_paths": len(stage_paths), "markdown_files": sum(p.endswith(".md") for p in content_by_path),
                      "local_links_checked": sum(len(LINK.findall(content_by_path[p]))
                                                  for p in content_by_path if p.endswith(".md"))}, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-index-manifest", action="store_true")
    args = parser.parse_args()
    if args.refresh_index_manifest:
        refresh_index_manifest()
    else:
        main()
