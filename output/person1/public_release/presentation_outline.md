# Public presentation outline

1. Problem and scope: synthetic GT supports accuracy; real video is qualitative only.
2. Synthetic scenarios and GT schema.
3. Threshold, segmentation and centroid: `figures/d1_01_detection_steps.png`.
4. Nearest and Hungarian: `figures/d1_02_association_nearest_hungarian.png`.
5. Demo using a tracked synthetic input/overlay; show frame-level CSV output.
6. Kalman prediction versus observation: `figures/d1_04_occlusion_kalman_prediction.png`.
7. Five-seed results: `summary_tables/synthetic_5seed.md`.
8. Fiji versus Python with Simple LAP/Hungarian distinction: `summary_tables/fiji_python_seed0.md`.
9. Failure cases and runtime: overlap/illumination figures and `figures/p6_runtime_throughput.png`.
10. Limits: no real-video GT; public release omits the real source media and overlays.
