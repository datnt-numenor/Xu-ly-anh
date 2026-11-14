<!-- Sanitized public copy; original F3 report is preserved locally. -->

# F3 Fiji TrackMate execution report

**Status: PASS ? all five P3 stress scenarios were processed by Fiji/TrackMate and all 15 CSV/XML pairs passed validation.** This is an experiment output validation, not a claim that any tracker is accurate. No ground-truth metrics were computed here.

- Branch/commit recorded: `experiment/person1` / `fed20818b9ff1688db89e25e8c882b0d74f00c83`.
- Fiji: portable Windows Fiji under `$FIJI`; native launcher `fiji-windows-x64.exe` (SHA256 in `metadata/fiji_run_metadata.json`); ImageJ 1.54p; TrackMate 8.1.6; bundled OpenJDK 21.0.7.
- Groovy script: `TrackMate_Nhom9.groovy`; detector threshold 110, quality 35..240, nearest link 24 px, Simple LAP gap distance 36 px/max gap 6, Kalman search radius 24 px/max gap 6. Simple LAP is not Python Hungarian.
- Input: the original P3 PNG sequences under `data/stress/{scenario}_seed0`; all 400 hashes verified against `output/person1/stress_manifest.csv`.
- The runner successfully launched headless Fiji for the initial `turn_seed0` probe, then `occlusion_seed0`, `overlap_seed0`, and `illumination_seed0`, with process exit code 0. `separate_seed0` was pre-existing and only validated read-only; it was not overwritten. Each produced 3 CSV and 3 XML artifacts at `output/person1/fiji_stress/{scenario}_seed0/`.

## CSV coverage and track counts

| Scenario | Rows per method | Emitted frames | Distinct IDs (nearest / LAP / Kalman) |
|---|---:|---|---|
| separate | 240 | 0..79 | 3 / 3 / 3 |
| occlusion | 236 | 0..79 | 4 / 3 / 3 |
| overlap | 234 | 0..79 | 6 / 3 / 3 |
| turn | 240 | 0..79 | 3 / 3 / 3 |
| illumination | 529 | 12..64 | 179 / 175 / 178 |

Illumination CSVs contain no rows in frames 0..11 or 65..79; these gaps are retained as observed detector/tracker output, not treated as a run failure. Each XML nevertheless describes the full 80-frame stack (frames 0..79), and its visible spot count agrees with the corresponding CSV row count.

## Validation

- 15 CSVs have exact header `frame,track_id,x,y`, nonempty rows, integer frame/track IDs, unique frame/ID pairs, finite in-bounds coordinates, and all emitted frames within 0..79.
- 15 XMLs parse, report TrackMate 8.1.6, full 320?180?80 image metadata at 1/15 s, threshold=110, quality filters 35/240 and the requested tracker factories/settings. All XML frame nodes 0..79 are present. CSV row counts match XML visible spots.
- P3 input SHA256s were verified before execution. Per-scenario logs record command, timestamp, commit and process exit status. The pre-existing `separate_seed0` has no historical per-run log; it was validated read-only, and no historical execution details were fabricated.

## Artifacts and rerun

- Runner: `scripts/run_fiji_stress.py`
- Summary: `output/person1/fiji_stress/validation_summary.csv`
- Environment/config: `output/person1/fiji_stress/run_metadata.json`
- Overall log: `output/person1/fiji_stress/runner.log`; actual scenario logs are each scenario's `run.log`.
- To reproduce without touching the completed result directory, choose a new output root: `python scripts/run_fiji_stress.py --output-root output/person1/fiji_stress_rerun --protected-separate output/person1/fiji_stress/separate_seed0 --timeout 600`. The runner uses the existing Groovy script and refuses overwrite/partial outputs.

No tracking algorithm or GT was modified. No P4/F4/P7 run, no commit.
