# Fiji versus Python: seed0, fixed 110, evaluation gate 8 px

Fiji Simple LAP and Python Hungarian are distinct methods. RMSE N/A means no matched pair. Source: `../../f4/comparison.csv`. All metrics use this repository's definitions.

| Scenario | Fiji | Python | Fiji matched | Fiji missed | Fiji false_positive | Fiji id_switches | Fiji track_ids | Fiji matched_detection_rmse_px | Fiji mota | Fiji idf1 | Python matched | Python missed | Python false_positive | Python id_switches | Python track_ids | Python matched_detection_rmse_px | Python mota | Python idf1 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| separate | nearest | nearest | 240 | 0 | 0 | 0 | 3 | 0.0667 | 1.0 | 1.0 | 240 | 0 | 0 | 0 | 3 | 0.0653 | 1.0 | 1.0 |
| separate | lap | hungarian | 240 | 0 | 0 | 0 | 3 | 0.0667 | 1.0 | 1.0 | 240 | 0 | 0 | 0 | 3 | 0.0653 | 1.0 | 1.0 |
| separate | kalman | kalman | 240 | 0 | 0 | 0 | 3 | 0.0667 | 1.0 | 1.0 | 240 | 0 | 0 | 0 | 3 | 0.0653 | 1.0 | 1.0 |
| occlusion | nearest | nearest | 236 | 0 | 0 | 1 | 4 | 0.0666 | 0.9958 | 0.8475 | 236 | 0 | 0 | 0 | 3 | 0.0652 | 1.0 | 1.0 |
| occlusion | lap | hungarian | 236 | 0 | 0 | 0 | 3 | 0.0666 | 1.0 | 1.0 | 236 | 0 | 0 | 0 | 3 | 0.0652 | 1.0 | 1.0 |
| occlusion | kalman | kalman | 236 | 0 | 0 | 0 | 3 | 0.0666 | 1.0 | 1.0 | 236 | 0 | 0 | 0 | 3 | 0.0652 | 1.0 | 1.0 |
| overlap | nearest | nearest | 234 | 6 | 0 | 3 | 6 | 0.1557 | 0.9625 | 0.6582 | 234 | 6 | 0 | 2 | 3 | 0.1549 | 0.9667 | 0.6667 |
| overlap | lap | hungarian | 234 | 6 | 0 | 2 | 3 | 0.1557 | 0.9667 | 0.6667 | 234 | 6 | 0 | 2 | 3 | 0.1549 | 0.9667 | 0.6667 |
| overlap | kalman | kalman | 234 | 6 | 0 | 2 | 3 | 0.1557 | 0.9667 | 0.9873 | 234 | 6 | 0 | 2 | 3 | 0.1549 | 0.9667 | 0.9873 |
| turn | nearest | nearest | 240 | 0 | 0 | 0 | 3 | 0.0667 | 1.0 | 1.0 | 240 | 0 | 0 | 0 | 3 | 0.0653 | 1.0 | 1.0 |
| turn | lap | hungarian | 240 | 0 | 0 | 0 | 3 | 0.0667 | 1.0 | 1.0 | 240 | 0 | 0 | 0 | 3 | 0.0653 | 1.0 | 1.0 |
| turn | kalman | kalman | 240 | 0 | 0 | 0 | 3 | 0.0667 | 1.0 | 1.0 | 240 | 0 | 0 | 0 | 3 | 0.0653 | 1.0 | 1.0 |
| illumination | nearest | nearest | 147 | 93 | 382 | 0 | 179 | 0.1783 | -0.9792 | 0.3823 | 160 | 80 | 337 | 1 | 161 | 0.1903 | -0.7417 | 0.4315 |
| illumination | lap | hungarian | 147 | 93 | 382 | 0 | 175 | 0.1783 | -0.9792 | 0.3823 | 160 | 80 | 337 | 1 | 153 | 0.1903 | -0.7417 | 0.4315 |
| illumination | kalman | kalman | 147 | 93 | 382 | 0 | 178 | 0.1783 | -0.9792 | 0.3823 | 160 | 80 | 337 | 1 | 156 | 0.1903 | -0.7417 | 0.4315 |
