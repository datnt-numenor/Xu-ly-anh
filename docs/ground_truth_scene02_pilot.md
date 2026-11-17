# Ground Truth Pilot — `scene02` (Frames 65–84)

## 1. Phạm vi dữ liệu và đoạn frame được chọn

- **Video nguồn:** `data/real/raw_scene02.mp4` (Pexels ID `6253870` — *Snooker balls spreading on the billiard table*, `3840×2160` @ `25 FPS`, SHA256 `933f1e2da638e1ea5d8e217b83cfc528f2c618f14767331d6a209fc8da57ba22`).
- **Chuỗi frame chuẩn hóa chấm điểm:** `data/real/scene02/frame_000.png` .. `frame_123.png` (`124` frame tổng cộng, `320×180` grayscale `mode L`, `15 FPS`, không lặp frame) và `data/real/scene02_lossless.mkv` (FFV1 lossless), kiểm chứng qua `data/real/scene02_manifest.json`.
- **Phạm vi Ground Truth Pilot (F2A):** **20 frame liên tiếp từ `frame 65` đến `frame 84`** (`frame_065.png` .. `frame_084.png`, chỉ số 0-based).
  - **Timestamp mục tiêu (`15 FPS`):** `4.3333s` – `5.6000s`.
  - **Timestamp frame nguồn gần nhất (`25 FPS`):** `4.3200s` – `5.6000s`.
  - **Lý do chọn đoạn `65–84`:** Đoạn này nằm sau cú phá bi (`frames 46–51`), các quả bi đã tách khỏi cụm tam giác ban đầu nhưng vẫn đang lăn tích cực trên mặt bàn trước khi dừng hẳn ở cuối video (`frames 95–123`). Đoạn bao gồm 1 pha va chạm trực tiếp giữa hai bi (`ID 4` và `ID 6` tại `frames 66–69`), 4 quả bi dội băng đi vào khung hình (`ID 7, 8, 9, 10`), và 1 pha lăn cắt mặt gần (`ID 10` đi qua gần `ID 2`).

---

## 2. Quy trình Pre-Annotation + Human Review

Ground Truth pilot của `scene02` được xây dựng theo quy trình **bán tự động có kiểm chứng thủ công (Assisted Pre-Annotation + Human-in-the-Loop Verification)**, **không phải** gán tay từ CSV trắng và **tuyệt đối không** sử dụng kết quả của các detector/tracker đang được đánh giá (`Fixed-110`, `Otsu`, `Nearest`, `Hungarian`, `Kalman`, `Fiji TrackMate`):

1. **Bước 1 — Khởi tạo nhãn gợi ý độc lập trên ảnh màu (`scripts/prepare_scene02_gt.py`):**
   - Trích xuất chuỗi ảnh màu đồng bộ thời gian và hình học (`data/real/scene02_color/` ở `320×180` và `data/real/scene02_color_2x/` ở `640×360`).
   - Phân đoạn từng quả bi trên không gian màu BGR/HSV bằng cách loại bỏ nền nỉ xanh, bóng đổ hướng Tây-Nam trên mặt bàn và chấm điểm mốc trắng cố định tại `(162, 53)`.
   - Ước lượng **tâm hình học của cả quả bi cầu** (bán kính chuẩn $R \approx 8.5\text{ px}$ trên ảnh `320×180`), tách các quả bi chạm nhau bằng biến đổi khoảng cách (Voronoi distance transform) và bù bán kính cầu khi quả bi bị cắt một phần ở mép biên ảnh.
   - Gán `object_id` (`1..10`) và đánh dấu tự động `23` trường hợp rủi ro (`TOUCHING_COLLISION_SPLIT`, `BORDER_PARTIAL_SPHERE`, `FAST_MOTION_STEP`) vào `uncertain_cases.csv` ở trạng thái `OPEN_HUMAN_REVIEW_REQUIRED`.
2. **Bước 2 — Duyệt và xác nhận thủ công qua GUI (`scripts/gt_review_gui.py`):**
   - Người gán nhãn mở GUI ở `frame 65` trên nền ảnh màu phóng to `2×` (`data/real/scene02_color_2x`), duyệt tuần tự từng frame từ `65` đến `84`, kiểm tra vị trí tâm hình học, độ phủ đối tượng và tính nhất quán `object_id` qua màu sắc, sọc, số in và quỹ đạo.
   - Từng frame sau khi kiểm tra được xác nhận (`Approve Frame (VERIFIED)`) và lưu tiến độ (`Save Progress`), ghi nhận đầy đủ dấu thời gian `review_timestamp` thực tế (`2026-11-17T12:19:50Z` đến `2026-11-17T12:22:58Z`).

---

## 3. Thống kê thực tế (Frames, Labels, Object IDs, Uncertain Cases)

| Chỉ tiêu | Giá trị thực tế | Nguồn đối chiếu |
|---|---|---|
| Tổng số frame của `scene02` | `124` (`0..123`) | `data/real/scene02_manifest.json` |
| Phạm vi frame Pilot F2A | `65–84` (`20` frame liên tiếp) | `data/real/scene02_ground_truth_manual.csv` |
| Số frame đã được con người duyệt | `20 / 20` (`frame_reviewed_by_human = 1`) | `output/ground_truth_real/scene02/frame_review_status.csv` |
| Tổng số nhãn đã xác minh (`VERIFIED`) | `129` dòng (`visible = 1` cho cả `129` dòng) | `data/real/scene02_ground_truth_manual.csv` |
| Số `object_id` riêng biệt | `10` (`ID 1` .. `ID 10`) | `output/ground_truth_real/scene02/reviewed_gt.csv` |
| Số trường hợp `uncertain` đã xử lý | `23 / 23` (`RESOLVED_VERIFIED`, còn `0` open) | `output/ground_truth_real/scene02/uncertain_cases.csv` |

### Danh mục 10 Object ID trong đoạn `65–84`

| `object_id` | Mô tả quả bi | Khoảng frame xuất hiện | Số dòng nhãn |
|---:|---|---|---:|
| `1` | Bi tím trơn (`#4`) — gần giữa bàn phía trên | `65–84` | 20 |
| `2` | Bi đen (`#8`) — gần giữa bàn phía dưới | `65–84` | 20 |
| `3` | Bi đỏ sẫm / nâu đỏ (`#7`) — lăn sang băng phải | `65–78` | 14 |
| `4` | Bi sọc đỏ (`#11`) — va chạm với `#13` tại `66–69` rồi lăn sang biên trái | `65–79` | 15 |
| `5` | Bi xanh dương sẫm (`#2`) — lăn ra khỏi biên phải | `65–67` | 3 |
| `6` | Bi sọc cam (`#13`) — va chạm với `#11` tại `66–69` rồi lăn lên trên | `65–84` | 20 |
| `7` | Bi vàng trơn (`#1`) — đi vào từ biên dưới bên trái | `73–84` | 12 |
| `8` | Bi sọc vàng (`#9`) — đi vào từ biên phải, lăn lên biên trên | `76–84` | 9 |
| `9` | Bi đỏ trơn (`#3`) — đi vào từ biên dưới bên phải | `77–84` | 8 |
| `10` | Bi cái màu trắng (Cue Ball) — đi vào từ biên dưới giữa, lăn qua gần `#8` | `77–84` | 8 |

---

## 4. Vị trí CSV chính thức và bằng chứng kiểm định

- **CSV Ground Truth chính thức cho `scene02` (Pilot 65–84):**
  - `data/real/scene02_ground_truth_manual.csv` (`129` nhãn, SHA256 `f3395a19b9702a0a7f3d5523124e0b8fe49accb9d014a8279dc3021fa5ad1157`)
  - Bản đối chiếu tại thư mục review: `output/ground_truth_real/scene02/reviewed_gt.csv` và `output/ground_truth_real/scene02/ground_truth_manual.csv` (trùng khớp byte-for-byte).
- **Các file bằng chứng review và trạng thái:**
  - `output/ground_truth_real/scene02/frame_review_status.csv`
  - `output/ground_truth_real/scene02/annotation_status.csv`
  - `output/ground_truth_real/scene02/uncertain_cases.csv`
  - `output/ground_truth_real/scene02/annotation_manifest.json`
  - `output/ground_truth_real/scene02/pilot_validation.md`
  - `output/ground_truth_real/scene02/pilot_report.md`

### Lệnh chạy kiểm định và kết quả

```powershell
python scripts/validate_ground_truth_pilot.py data/real/scene02_ground_truth_manual.csv --start 65 --end 84 --frames data/real/scene02 --manifest data/real/scene02_manifest.json --report output/ground_truth_real/scene02/pilot_validation.md
python scripts/validate_ground_truth_full.py --output-dir output/ground_truth_real/scene02 --frames data/real/scene02 --manifest data/real/scene02_manifest.json
python -m unittest discover -s tests -p test_ground_truth_annotator.py -v
```

- **Pilot Validator:** `PASS: 129 labels; 0 review flags` (`Errors: None`, `Review flags: None`, `0` khoảng trống `unlabeled_gaps`).
- **Full Bundle Validator:** `structural_pass: true`, `pilot_verified_pass: true`, `exported_scope_pass: true`, `full_gt_pass: false` (`acceptance_state = PILOT_VERIFIED_PASS__EXPORTED_SCOPE_PASS`).
- **Unit Tests:** `Ran 8 tests — OK` (`32/32` toàn bộ test trong repo `OK`).

---

## 5. Giới hạn sử dụng khi đánh giá Tracker & Hạn chế còn lại

1. **Phạm vi chỉ bao phủ 20 frame (`65–84`), chưa phải Ground Truth toàn bộ 124 frame (`0–123`):**
   - Trạng thái đạt được là **`F2A PILOT PASS` (`PILOT_VERIFIED_PASS__EXPORTED_SCOPE_PASS`)** cho đoạn `65–84`. Các frame `0–64` và `85–123` chưa được gán nhãn.
2. **Bắt buộc lọc frame của Tracker về `65..84` trước khi gọi `evaluation.py`:**
   - Hàm `evaluation.score(truth, observations, gate=8.0)` và `evaluation.score_with_identity()` trong `evaluation.py` lấy **hợp (union)** các frame có mặt trong `truth` và `observations` (`truth_by_frame.keys() | pred_by_frame.keys()`), đồng thời chưa có tham số giới hạn khoảng frame (`start_frame`/`end_frame`).
   - Nếu truyền trực tiếp danh sách dự đoán `observations` của cả video (`0..123`) vào chấm điểm với `data/real/scene02_ground_truth_manual.csv` (`65..84`), mọi phát hiện của tracker ở các frame `0..64` và `85..123` sẽ bị tính nhầm thành `false_positive` (`FP`), làm sai lệch nghiêm trọng `FP` và `MOTA`.
   - **Hướng xử lý bắt buộc khi chấm điểm:** Chỉ truyền các dòng dự đoán thỏa mãn `65 <= frame <= 84` vào `evaluation.score()` / `evaluation.score_with_identity()`.
3. **Quy ước quả bi bị cắt một phần sát mép ảnh (`Border-Sliver Convention`):**
   - Khi một quả bi mới nhô vào hoặc sắp lăn ra khỏi biên ảnh mà phần diện tích nhìn thấy nhỏ hơn nửa mặt cầu (tâm hình học thực của quả bi nằm ngoài miền `[0, 320) × [0, 180)`, ví dụ mép bi `ID 3` chạm lại biên phải ở `frame 84` hoặc mép bi ở `frame 68, 72, 74, 75, 76, 80`), quả bi đó không được đưa vào CSV ở frame đó vì schema bắt buộc `0 <= x < 320` và `0 <= y < 180`. Điều này có thể tạo ra 1 frame chênh lệch ở sát mép biên nếu bộ phát hiện của tracker bắt cả mảnh rìa nhỏ của quả bi.
