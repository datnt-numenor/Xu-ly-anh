# Python synthetic stress: five-seed means

Each row averages five seed-level results for one scenario/detector/tracker. Seed variation changes image noise; it does not create independent motion trajectories. RMSE is conditional on matched pairs. Source: `../../stress_full/per_run.csv`.

| Scenario | Detector | Python tracker | Seeds | Matched mean | Missed mean | FP mean | ID switches mean | Track IDs mean | Matched RMSE px mean |
|---|---|---|---|---|---|---|---|---|---|
| separate | fixed | nearest | 5 | 240.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| separate | fixed | hungarian | 5 | 240.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| separate | fixed | kalman | 5 | 240.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| separate | otsu | nearest | 5 | 240.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| separate | otsu | hungarian | 5 | 240.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| separate | otsu | kalman | 5 | 240.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| occlusion | fixed | nearest | 5 | 236.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| occlusion | fixed | hungarian | 5 | 236.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| occlusion | fixed | kalman | 5 | 236.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| occlusion | otsu | nearest | 5 | 236.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| occlusion | otsu | hungarian | 5 | 236.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| occlusion | otsu | kalman | 5 | 236.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| overlap | fixed | nearest | 5 | 234.00 | 6.00 | 0.00 | 2.00 | 3.00 | 0.15 |
| overlap | fixed | hungarian | 5 | 234.00 | 6.00 | 0.00 | 2.00 | 3.00 | 0.15 |
| overlap | fixed | kalman | 5 | 234.00 | 6.00 | 0.00 | 2.00 | 3.00 | 0.15 |
| overlap | otsu | nearest | 5 | 234.00 | 6.00 | 0.00 | 2.00 | 3.00 | 0.15 |
| overlap | otsu | hungarian | 5 | 234.00 | 6.00 | 0.00 | 2.00 | 3.00 | 0.15 |
| overlap | otsu | kalman | 5 | 234.00 | 6.00 | 0.00 | 2.00 | 3.00 | 0.15 |
| turn | fixed | nearest | 5 | 240.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| turn | fixed | hungarian | 5 | 240.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| turn | fixed | kalman | 5 | 240.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| turn | otsu | nearest | 5 | 240.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| turn | otsu | hungarian | 5 | 240.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| turn | otsu | kalman | 5 | 240.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.07 |
| illumination | fixed | nearest | 5 | 159.80 | 80.20 | 344.00 | 0.20 | 164.00 | 0.19 |
| illumination | fixed | hungarian | 5 | 159.80 | 80.20 | 344.00 | 0.20 | 154.80 | 0.19 |
| illumination | fixed | kalman | 5 | 159.80 | 80.20 | 344.00 | 0.20 | 156.20 | 0.19 |
| illumination | otsu | nearest | 5 | 240.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.24 |
| illumination | otsu | hungarian | 5 | 240.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.24 |
| illumination | otsu | kalman | 5 | 240.00 | 0.00 | 0.00 | 0.00 | 3.00 | 0.24 |
