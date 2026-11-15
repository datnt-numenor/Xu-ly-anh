# P6 measured throughput

One warm-up and five measured runs per configuration. Throughput uses decoded frame count / wall-clock seconds for decode + detection + tracker update; overlay rendering/encoding is excluded. Source: `../data/runtime_per_run.csv` and `../data/runtime_summary.csv`.

| Detector | Tracker | Measured runs | P25 s | Median s | P75 s | P25 fps | Median fps | P75 fps |
|---|---|---|---|---|---|---|---|---|
| fixed_110 | nearest | 5 | 0.771 | 0.933 | 0.965 | 155.39 | 160.86 | 194.45 |
| otsu | nearest | 5 | 1.014 | 1.040 | 1.109 | 135.24 | 144.23 | 147.92 |
| fixed_110 | hungarian | 5 | 0.817 | 0.876 | 0.956 | 156.85 | 171.14 | 183.63 |
| otsu | hungarian | 5 | 0.848 | 0.860 | 0.915 | 163.98 | 174.46 | 176.88 |
| fixed_110 | kalman | 5 | 0.939 | 1.031 | 1.185 | 126.57 | 145.45 | 159.76 |
| otsu | kalman | 5 | 0.954 | 0.988 | 1.201 | 124.93 | 151.78 | 157.23 |
