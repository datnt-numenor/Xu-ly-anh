# F4 — Fiji versus Python on P3 seed0

**PASS: 15 Fiji outputs and 15 Python fixed=110 outputs scored on the complete 80-frame GT per scenario, with gate 8 px.**

All numbers below come from `evaluation.score_with_identity` and the original CSVs. These are repository metric definitions, not a claim of MOTChallenge compliance. `visible=0` GT is excluded from matching. Empty prediction frames remain in the GT domain.

| Scenario | Fiji / Python | Fiji matched/missed/FP/switch | Python matched/missed/FP/switch | Fiji MOTA/IDF1 | Python MOTA/IDF1 |
|---|---|---|---|---|---|
| separate | nearest / nearest | 240/0/0/0 | 240/0/0/0 | 1.0/1.0 | 1.0/1.0 |
| separate | lap / hungarian | 240/0/0/0 | 240/0/0/0 | 1.0/1.0 | 1.0/1.0 |
| separate | kalman / kalman | 240/0/0/0 | 240/0/0/0 | 1.0/1.0 | 1.0/1.0 |
| occlusion | nearest / nearest | 236/0/0/1 | 236/0/0/0 | 0.9958/0.8475 | 1.0/1.0 |
| occlusion | lap / hungarian | 236/0/0/0 | 236/0/0/0 | 1.0/1.0 | 1.0/1.0 |
| occlusion | kalman / kalman | 236/0/0/0 | 236/0/0/0 | 1.0/1.0 | 1.0/1.0 |
| overlap | nearest / nearest | 234/6/0/3 | 234/6/0/2 | 0.9625/0.6582 | 0.9667/0.6667 |
| overlap | lap / hungarian | 234/6/0/2 | 234/6/0/2 | 0.9667/0.6667 | 0.9667/0.6667 |
| overlap | kalman / kalman | 234/6/0/2 | 234/6/0/2 | 0.9667/0.9873 | 0.9667/0.9873 |
| turn | nearest / nearest | 240/0/0/0 | 240/0/0/0 | 1.0/1.0 | 1.0/1.0 |
| turn | lap / hungarian | 240/0/0/0 | 240/0/0/0 | 1.0/1.0 | 1.0/1.0 |
| turn | kalman / kalman | 240/0/0/0 | 240/0/0/0 | 1.0/1.0 | 1.0/1.0 |
| illumination | nearest / nearest | 147/93/382/0 | 160/80/337/1 | -0.9792/0.3823 | -0.7417/0.4315 |
| illumination | lap / hungarian | 147/93/382/0 | 160/80/337/1 | -0.9792/0.3823 | -0.7417/0.4315 |
| illumination | kalman / kalman | 147/93/382/0 | 160/80/337/1 | -0.9792/0.3823 | -0.7417/0.4315 |

## Detector agreement

Fiji filtered visible XML spots were compared to Python fixed=110 detector centroids on the same 400 PNGs at 2 px. Track IDs are ignored. This is detector agreement, not accuracy against GT.

| Scenario | Fiji / Python spots | Matched | Unmatched Fiji / Python | Matched centroid RMSE px |
|---|---:|---:|---:|---:|
| separate | 240 / 240 | 240 | 0 / 0 | 0.035 |
| occlusion | 236 / 236 | 236 | 0 / 0 | 0.0353 |
| overlap | 234 / 234 | 234 | 0 / 0 | 0.0351 |
| turn | 240 / 240 | 240 | 0 / 0 | 0.0347 |
| illumination | 529 / 497 | 147 | 382 / 350 | 0.1643 |

## Interpretation and traceability

- Nearest is compared with nearest and Kalman with Kalman. Fiji Simple LAP and Python Hungarian are different tracking algorithms; their rows are contextual comparisons, not algorithm equivalence.
- Occlusion contains GT object 1 with `visible=0` at frames 36–39; these four rows are excluded from visible GT. Fiji nearest has one ID switch after occlusion while Python nearest has zero. Overlap contains two GT centers even when image regions merge; both systems miss six centers at frames 38–41. Fiji nearest has three ID switches versus Python nearest's two.
- Illumination under threshold 110 has no Fiji observations in frames 0–11 or 65–79; those frames still contribute visible GT misses. Fiji has 147 matches, 93 misses and 382 false positives per tracker; Python has 160, 80 and 337. High FP counts reflect extra threshold blobs as lighting changes. Neither pipeline performs well on this scenario under the fixed threshold.
- Fiji and Python differ in detector processing and tracker linking. Detector agreement helps identify centroid differences but does not isolate tracker behavior because shared detection inputs were not enforced.
- RMSE is defined only for matched pairs. Empty values in CSV mean N/A; they are not zero. Full metric definitions and input hashes are in `evaluation.py` and `validation.json`.
- The six P2 legacy metrics were independently cross-checked against `output/person1/stress_seed0/per_run.csv` for all 15 Python rows. Figures in `figures/` plot the exact `comparison.csv` values for MOTA, IDF1, missed and ID switches. CSVs and XMLs under F3 and P2 were read only.

## Reproduce

From the repo root, run `python scripts/evaluate_fiji_stress.py --output output/person1/f4_rerun` to avoid replacing these artifacts. No P7 was run and no commit was made.
