# Git staging plan

Do not stage with a broad directory command. Exact allowlisted new paths are in [`public_stage_paths.txt`](public_stage_paths.txt); that path list is also in the manifest and is 698 lines. The package has 1174 files, including 476 files from the base commit. Read the exact payload byte count from the public manifest's `total_bytes`; Git index blob sizes are authoritative for the staged addition size.

Stage only the explicit path list after reviewing it:

```powershell
git add --pathspec-from-file=docs/public_stage_paths.txt
git diff --cached --stat
git diff --cached --check
```

This plan intentionally excludes the working-tree diff to `docs/THUC_NGHIEM.md` because that diff contains local executable paths; the clean tracked HEAD version is included. Review current `git status` before running the command. It does not stage or commit by itself.

## Stage groups and suggested commits

1. Source, utilities and tests (`scripts/`, `tests/`, safe Fiji runner): `Add reproducible tracking experiment utilities`.
2. Synthetic inputs and results (`data/stress/`, `output/person1/stress_*`, Fiji CSV/XML, F4, timing): `Add synthetic tracking and benchmark evidence`.
3. Report, figures and release scope (`output/person1/public_release/`, `docs/PUBLIC_RELEASE_SCOPE.md`, `docs/GIT_STAGING_PLAN.md`, `docs/public_stage_paths.txt`): `Add privacy-safe public experiment report`.

The `files` array in the public manifest is the authoritative allowlist; this document groups it for review. Real media and all derived still/video imagery are excluded. Existing original data and full local manifest were not edited or deleted.
