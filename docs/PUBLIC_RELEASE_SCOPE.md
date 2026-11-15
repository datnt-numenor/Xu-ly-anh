# Public release scope

The exact allowlist is the `files` array in [`public_evidence_manifest.json`](../output/person1/public_release/public_evidence_manifest.json). It contains 1172 hashed artifacts; `total_bytes` and each row's `size_bytes` describe the Git blob bytes after line-ending normalization. The manifest and its detached SHA256 sidecar are tracked release metadata outside the payload array to avoid self-reference, yielding 1174 public files. The exact new/changed staging path list is [`public_stage_paths.txt`](public_stage_paths.txt).

The package includes the tracked repository contents at HEAD (including existing synthetic videos, PNGs and historical results), synthetic P3 seed0 PNG/GT, full Python stress and seed0 CSV outputs, Fiji CSV/XML/config validation, F4 metrics, P6 timing CSV copies, selected real-video output CSVs, source/tests, public report, and 11 permitted figures.

Excluded from the public allowlist: original full `output/person1/final/report.md`/`evidence_manifest.json`, all `data/real/` files (raw video, 150 PNG, FFV1 and P4 manifest), real-video screenshots/overlays/MP4, the full P7/P4 and host-specific Fiji metadata/log copies, and files in cache/virtual-environment/temp classes. The original excluded files remain untouched in the workspace.

P5 output CSV counts and P6 numeric timing records remain, but their real source input is omitted; they cannot be rerun or visually reviewed from the public package. Synthetic GT accuracy, Fiji/Python comparisons, and synthetic frames are included. Fiji launcher paths are redacted while component versions, parameters, and executable hashes remain. No real-video accuracy claim is made because no GT exists.

Tracked historical repo files were audited as well as untracked files. One modified tracked document with a machine-specific Fiji path is represented by its clean HEAD version; its current working-tree diff is intentionally excluded from staging. No Git ignore rule is used as a substitute for the allowlist.
