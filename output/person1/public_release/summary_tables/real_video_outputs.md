# P5 revised real-video outputs

Counts describe generated output only. The video has no ground truth, so they are not accuracy scores. Source: `../../real_video_tracking/tracking_summary.csv`.

| Configuration | Frames | Detection rows | Detections/frame mean | Track rows | Distinct output IDs | Max active IDs | Overlay frames |
|---|---|---|---|---|---|---|---|
| fixed_110_nearest | 150 | 2054 | 13.69 | 2054 | 524 | 62 | 150 |
| fixed_110_hungarian | 150 | 2054 | 13.69 | 2054 | 481 | 60 | 150 |
| fixed_110_kalman | 150 | 2054 | 13.69 | 2054 | 563 | 62 | 150 |
| otsu_nearest | 150 | 2548 | 16.99 | 2548 | 557 | 73 | 150 |
| otsu_hungarian | 150 | 2548 | 16.99 | 2548 | 498 | 67 | 150 |
| otsu_kalman | 150 | 2548 | 16.99 | 2548 | 637 | 74 | 150 |
