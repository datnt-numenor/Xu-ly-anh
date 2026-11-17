# F2A Scene02 — Ground Truth Pilot Report (Frames 65–84)

## 1. Summary & Current Status

- **Status:** `PILOT_VERIFIED_PASS` (`20 / 20` frames human-verified; `129` `VERIFIED` rows exported to `ground_truth_manual.csv`).
- **Source Video:** `data/real/raw_scene02.mp4` (Pexels ID `6253870`, 3840×2160 @ 25 FPS, 124 normalized frames @ 15 FPS).
- **Selected 20-Frame Pilot Segment:** **Frames `65–84` inclusive** (`frame_065.png` .. `frame_084.png`).
  - Target timestamps (15 FPS): **`4.3333s` – `5.6000s`**.
  - Nearest source timestamps (25 FPS): **`4.3200s` – `5.6000s`**.
- **Verified Labels (`reviewed_gt.csv` & `ground_truth_manual.csv`):** **`129` rows across `10` distinct billiard balls (`object_id = 1..10`)**.
  - `VERIFIED`: **`129` rows** (`100%`).
  - `UNREVIEWED`: **`0` rows**.
  - `UNCERTAIN`: **`0` rows** (all `23` cases resolved as `RESOLVED_VERIFIED`).

## 2. Object Identity Catalog (`object_id = 1..10`)

| Object ID | Ball Identity (Color / Stripe / Number) | Observed Frame Span | Total Frames | Notes |
|---:|---|---|---:|---|
| `1` | Solid Purple (#4) — near upper-center | `65–84` | 20 | Uncertain at frames: `none` |
| `2` | Solid Black (#8) — near lower-center | `65–84` | 20 | Uncertain at frames: `none` |
| `3` | Solid Maroon/Brown-Red (#7) — rolling right toward cushion (f065-f078) | `65–78` | 14 | Uncertain at frames: `[77, 78]` |
| `4` | Red-Stripe (#11) — lower-left, collides with #13 at f066-f069 then rolls left (f065-f078) | `65–79` | 15 | Uncertain at frames: `[66, 67, 68, 69, 78, 79]` |
| `5` | Solid Dark Blue (#2) — exiting right border (f065-f067) | `65–67` | 3 | Uncertain at frames: `[67]` |
| `6` | Orange-Stripe (#13) — enters lower-left, collides with #11 at f066-f069 then rolls up-right (f065-f084) | `65–84` | 20 | Uncertain at frames: `[66, 67, 68, 69]` |
| `7` | Solid Yellow (#1) — enters bottom-left at f073 and rolls upward (f073-f084) | `73–84` | 12 | Uncertain at frames: `[73]` |
| `8` | Yellow-Stripe (#9) — enters right border at f076 and rolls up-left (f076-f084) | `76–84` | 9 | Uncertain at frames: `[76, 84]` |
| `9` | Solid Red (#3) — enters bottom-right at f077 and rolls up-right (f077-f084) | `77–84` | 8 | Uncertain at frames: `[77, 78, 80, 82, 83]` |
| `10` | White Cue Ball — enters bottom-center at f078 and rolls up-right near #8 (f078-f084) | `77–84` | 8 | Uncertain at frames: `[77, 78]` |

## 3. Flagged Uncertain Cases Requiring Human Verification (`25` cases)

1. **Collision / Contact (`TOUCHING_COLLISION_SPLIT`, frames `66–69`):** `ID 4` (Red-Stripe `#11`) and `ID 6` (Orange-Stripe `#13`) collide in the lower-left (`x ≈ 41..62, y ≈ 133..163`). Sphere centers were separated via Voronoi distance transform; verify exact geometric centers during contact.
2. **Border Entry / Exit (`BORDER_PARTIAL_SPHERE`, frames `67, 73, 76, 77, 78, 84`):** Balls partially clipped by the border (`ID 5` exiting right at `f067`, `ID 7` entering bottom at `f073`, `ID 8` entering right at `f076` and exiting top at `f084`, `ID 3` & `ID 4` exiting right/left at `f077–f078`, `ID 9` & `ID 10` entering bottom at `f077–f078`). Centers were compensated by sphere radius `R = 9.2 px`; verify whether to keep or adjust edge frames.
3. **Close Pass (`CLOSE_PROXIMITY_PASS`, frames `83–84`):** `ID 10` (White Cue Ball) rolls upward past `ID 2` (Black `#8`) within `<= 23 px`.
