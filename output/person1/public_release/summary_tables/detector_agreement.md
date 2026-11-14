# F4 detector agreement

This compares Fiji XML spots to Python fixed-110 detector centroids at the F4 agreement gate; it is not accuracy against GT. Source: `../../f4/detector_comparison/summary.csv`.

| Scenario | Fiji spots | Python spots | Matched | Unmatched Fiji | Unmatched Python | Matched centroid RMSE px |
|---|---|---|---|---|---|---|
| separate | 240 | 240 | 240 | 0 | 0 | 0.035 |
| occlusion | 236 | 236 | 236 | 0 | 0 | 0.0353 |
| overlap | 234 | 234 | 234 | 0 | 0 | 0.0351 |
| turn | 240 | 240 | 240 | 0 | 0 | 0.0347 |
| illumination | 529 | 497 | 147 | 382 | 350 | 0.1643 |
