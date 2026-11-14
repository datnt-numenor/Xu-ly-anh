# Public pipeline map

This map covers the synthetic examples whose images and GT are present in this release.

| Stage | Source | Public example |
|---|---|---|
| Threshold/segmentation/centroid | `tracking.detect` in `tracking.py` | [D1 detection steps](figures/d1_01_detection_steps.png) |
| Nearest/Hungarian associations | `Tracker.update` and `associate` in `tracking.py` | [D1 association](figures/d1_02_association_nearest_hungarian.png) |
| Verified overlap misses | Existing P3 GT and F4 output | [Overlap case](figures/d1_03_overlap_verified_misses.png) |
| Kalman prediction | `Tracker.update`; prediction state is distinct from observation | [Occlusion case](figures/d1_04_occlusion_kalman_prediction.png) |
| Illumination masks | Existing P3 frames and detector | [Threshold comparison](figures/d1_05_illumination_threshold_comparison.png) |

The real-video D1 panel and P5 overlay are excluded. Do not infer identity accuracy for real video: it has no GT in the public package.
