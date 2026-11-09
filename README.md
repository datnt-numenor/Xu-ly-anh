# Phát hiện và theo dõi đối tượng chuyển động trong video

Nhóm 9 · Xử lý ảnh · PTIT

Bốn video tổng hợp 320 × 180, 15 fps, nền tối có nhiễu và vật thể sáng. Mỗi kịch bản kiểm tra một điểm yếu riêng:

| Kịch bản | Frame | Nội dung | Thuật toán cần có |
|---|---|---|---|
| `separate` | 43 | 3 vật đi tách nhau | Nearest neighbor là đủ |
| `crossing` | 43 | 2 vật đi ngược chiều, vật 1 bị ẩn ở frame 20–23 (đánh số từ 0) đúng lúc giao nhau | Kalman (dự đoán khi mất quan sát) |
| `dense` | 30 | 2 đoàn 3 vật nối đuôi, cách nhau 16 px, đoàn trên sang phải, đoàn dưới sang trái, cùng tăng tốc từ 6 lên 11 px/frame | Hungarian (ghép tối ưu toàn cục) |
| `noisy` | 43 | `crossing` cộng nhiễu Gauss σ = 100 lên mọi điểm ảnh | Detector chịu nhiễu |

Trong `dense`, khi bước di chuyển vượt nửa khoảng cách (8 px, từ frame 16), spot gần nhất của mỗi track lại là vật đi sau. Cách ghép tham lam đổi ID liên tục, còn Hungarian vẫn đúng vì ràng buộc mỗi spot chỉ gán cho một track. Cột `visible` trong `*_truth.csv` đánh dấu khi vật thể xuất hiện trong ảnh.

## Xem demo ngay

- `data/separate.mp4` và `data/crossing.mp4` là video đầu vào.
- `results/crossing/nearest.mp4`, `hungarian.mp4` và `kalman.mp4` là video gắn ID và vệt quỹ đạo. Tua đến khoảng giây 1,6 để xem lúc hai vật thể đổi phía.
- `results/dense/nearest.mp4` và `hungarian.mp4` cho thấy hai đoàn bị đổi ID khi tăng tốc.
- `results/figures/` chứa 5 hình cho báo cáo, sinh bằng `python plots.py`:
  - `trajectories.png`: quỹ đạo tĩnh (x theo frame), mỗi ID một màu, dấu x là lần đổi ID. Dùng thay video trong báo cáo in.
  - `idf1_methods.png`: IDF1 của 3 phương pháp, Python và TrackMate, 3 kịch bản.
  - `parameter_sweep.png`: ảnh hưởng của gate và max_missing.
  - `noise_robustness.png`: IDF1 và RMSE khi tăng nhiễu, có và không làm mượt.
  - `noisy_detectors.png`: so sánh detector Python với Threshold và LoG của TrackMate trên video `noisy`.
- `results/summary.csv` chứa số liệu Python. CSV đánh giá từng phương pháp chỉ rõ frame và vật thể đổi ID. Video đầu ra hiển thị các quan sát đã gán ID, nên vệt được ngắt qua khung hình vắng mặt.

## Chạy bằng Fiji TrackMate

Tải [Fiji](https://fiji.sc/) và dùng TrackMate 7.14 trở lên. Kết quả `separate` và `crossing` trong results/fiji được chạy headless từ TrackMate 8.1.6 (Java 21). Kết quả `dense` và `noisy` chạy headless từ TrackMate 7.14.0 (Fiji bản 2025-02-06). Chạy lại `separate` và `crossing` bằng 7.14.0 cho vị trí spot và chỉ số giống hệt 8.1.6, chỉ khác số hiệu track. Quy trình bấm GUI dưới đây dùng để tái hiện và trình diễn.

### Chạy bằng giao diện

1. Chọn **File › Import › Image Sequence…**, mở ảnh đầu tiên trong `data/crossing/` và kiểm tra 43 ảnh theo thứ tự tên. Có thể lặp lại với `data/separate/`.
2. Chọn **Image › Hyperstacks › Stack to Hyperstack…**, đặt Channels = 1, Slices = 1, Frames = 43. Đặt Frame Interval = 0,066667 s ở **Image › Properties…**, với kích thước pixel 1 × 1 và đơn vị pixel. Kiểm tra thanh trượt **T**.
3. Chọn **Plugins › Tracking › TrackMate**. Chọn **Thresholding detector**, kênh 1, ngưỡng 110. Bỏ Simplify contours nếu cần đối chiếu script. Ở bước lọc spot, dùng Quality 35–240 để loại chấm nhiễu theo diện tích. Bước Preview ở frame đánh số 21 có hai vật thể hiện.
4. Chạy riêng từng tracker trên cùng stack. Nearest-Neighbor dùng bán kính ghép 24 px. Simple LAP dùng Linking 24 px, Gap-closing 36 px, Max frame gap 6 và bật Allow gap closing. Kalman dùng Initial search radius 24 px, Kalman search radius 24 px và Max frame gap 6. Đây là tham số khởi đầu, dùng hai bộ video để kiểm tra ảnh hưởng của việc nối đoạn và dự đoán.
5. Hiển thị spots và tracks, tô màu theo ID. Dùng **Tracks** để xuất bảng Spots và Tracks, lưu phiên TrackMate XML, dùng **Capture overlay** nếu cần video minh họa. Ghi lại phiên bản Fiji/TrackMate, cấu hình và kết quả thực tế.

### Chạy tự động và chấm điểm CSV

Mở `TrackMate_Nhom9.groovy` trong Fiji Script Editor, chọn **Groovy**, nhấn **Run**, chọn thư mục `data/crossing` (lặp lại với `data/separate`, `data/dense`, `data/noisy`) và thư mục đích `results/fiji`. Ô **Detector** chọn `threshold` (mặc định), `log` hoặc `both`. Với `data/noisy` chọn `both`. Script tạo XML và CSV cho 3 tracker, với frame tính từ 0. Detector LoG dùng bán kính 7 px và ngưỡng quality 5: trên bộ thử, spot thật có quality ≥ 7, cực đại nhiễu ≤ 2,5.

Chạy headless không cần giao diện (đổi đường dẫn cho phù hợp):

```bash
ImageJ-linux64 --headless --console --run TrackMate_Nhom9.groovy 'framesDir="data/noisy",outputDir="results/fiji",detectorChoice="both"'
```

XML của `noisy` với detector threshold không được commit vì mỗi file khoảng 80 MB: TrackMate lưu cả hàng nghìn spot nhiễu trước khi lọc. CSV của chúng vẫn có trong repo. Mỗi spot hiện nhưng không được nối được xem là một quỹ đạo đơn khi chấm. Mở XML bằng **Plugins › Tracking › Load a TrackMate file** nếu stack nguồn khả dụng, hoặc chạy GUI để tạo overlay.

Sau khi cài các gói Python ở phần dưới, chấm một CSV hoặc cả thư mục (ghi lại `results/fiji/summary.csv` và các `*_evaluation.csv`), rồi vẽ lại biểu đồ:

```powershell
python score_trackmate.py data/crossing_truth.csv results/fiji/crossing_kalman.csv
python score_trackmate.py --folder results/fiji
python plots.py
```


Ngưỡng ghép với ground truth là 8 px. Cách xử lý khoảng trống và tính chi phí của TrackMate khác bản Python, vì vậy dùng số đo từ CSV TrackMate cho phần trình diễn Fiji.

## Chạy bản Python

Cài Python 3.10+ và FFmpeg có `ffmpeg`, `ffprobe`, encoder `libx264` trong PATH. Trên Windows, có thể mở PowerShell trong thư mục đã giải nén rồi dùng:

```powershell
python -m pip install -r requirements.txt
python benchmark.py
python benchmark_png.py
python plots.py
python tracking.py data/crossing.mp4 --method kalman --output output
```

`benchmark.py` tái tạo dữ liệu mẫu, chạy cả ba thuật toán và kiểm tra 240 ma trận chi phí ngẫu nhiên với SciPy. `benchmark_png.py` đo thời gian, khảo sát tham số và thí nghiệm nhiễu (khoảng 15 giây). `plots.py` vẽ biểu đồ từ các CSV. `tracking.py` nhận video riêng, hỗ trợ `--method nearest`, `--method hungarian`, `--method kalman` và các cờ `--threshold`, `--blur`, `--min-area`, `--max-area`, `--gate`, `--max-missing`. `--blur 1.5` làm mượt Gauss trước khi phân ngưỡng, nên dùng với video nhiễu. Demo phù hợp với video vật sáng trên nền tối, tốc độ khung hình cố định. Để thử video thật, ưu tiên camera cố định, nền trơn và vật sáng tách nhau. Ngưỡng cố định sẽ đưa cả vật sáng đứng yên vào tập phát hiện.

## Chia phần thuyết trình

1. Bài toán, dữ liệu thử, phân đoạn, centroid và thí nghiệm nhiễu (làm mượt Gauss).
2. Nearest Neighbor, ma trận chi phí, Hungarian và demo `dense`.
3. Kalman, dự đoán lúc mất quan sát và demo `crossing`.
4. Chạy Fiji TrackMate, chỉ số MOTA/IDF1, so sánh kết quả và giới hạn.

## Tài liệu

- [Bài báo TrackMate 7](https://doi.org/10.1038/s41592-022-01507-1)
- [Thresholding detector](https://imagej.net/plugins/trackmate/detectors/trackmate-thresholding-detector)
- [TrackMate trackers](https://imagej.net/plugins/trackmate/trackers/)
- [LAP trackers](https://imagej.net/plugins/trackmate/trackers/lap-trackers)
- [TrackMate scripting settings](https://imagej.net/plugins/trackmate/scripting/trackmate-detectors-trackers-keys)
- [Kuhn 1955](https://doi.org/10.1002/nav.3800020109)
- [Bernardin & Stiefelhagen 2008, CLEAR MOT (MOTA)](https://doi.org/10.1155/2008/246309)
- [Ristani và cộng sự 2016, IDF1](https://arxiv.org/abs/1609.01775)

## Chỉ số đánh giá

Mỗi frame, vật thật và vị trí dự đoán được ghép bằng Hungarian với bán kính 8 px.

- `matched`, `missed`, `false_positive`: số cặp khớp, số vật bị bỏ sót, số phát hiện thừa.
- `id_switches`: số lần một vật thật đổi sang ID khác so với lần khớp trước. `track_ids` là số ID đã tạo.
- `mota` = 1 − (missed + false_positive + id_switches) / số vật thật (CLEAR MOT, Bernardin & Stiefelhagen 2008).
- `idf1` = 2·IDTP / (số vật thật + số dự đoán). IDTP lấy từ cách ghép một-một tốt nhất giữa vật thật và ID trên toàn video (Ristani và cộng sự 2016). MOTA chỉ phạt khoảnh khắc đổi ID. IDF1 phạt cả quãng mang sai ID, nên `crossing` với Nearest có MOTA 0,98 nhưng IDF1 chỉ 0,69.
- `rmse_px`: sai số vị trí centroid của các cặp khớp.

## Kết quả chính

| Kịch bản | Nearest | Hungarian | Kalman | TrackMate Nearest | TrackMate LAP | TrackMate Kalman |
|---|---|---|---|---|---|---|
| separate (IDF1) | 1,00 | 1,00 | 1,00 | 1,00 | 1,00 | 1,00 |
| crossing (IDF1) | 0,69 | 0,69 | 1,00 | 0,68 | 1,00 | 1,00 |
| dense (IDF1) | 0,53 | 1,00 | 1,00 | 0,74 | 1,00 | 1,00 |

**Nearest của TrackMate khác bản Python.** Ở `dense`, Nearest Python đổi ID ở cả hai đoàn (84 lần), còn Nearest TrackMate chỉ đổi ID ở đoàn dưới (52 lần, toàn bộ ở vật 4–6). Bản Python ghép tham lam theo khoảng cách nhỏ nhất trên toàn frame. Theo tài liệu TrackMate, tracker này nối mỗi spot với spot gần nhất ở frame sau mà không giải bài toán gán toàn cục, nên kết quả phụ thuộc thứ tự duyệt spot. Nhóm suy ra (từ kết quả, chưa đọc mã nguồn) rằng spot được duyệt từ trái sang phải: với đoàn đi sang phải, vật cuối đoàn được xét trước nên chiếm đúng spot của mình; với đoàn đi sang trái, vật đầu đoàn được xét trước và lấy nhầm spot của vật phía sau. Cả hai cách đều không có ràng buộc tối ưu toàn cục, nên đều hỏng khi vật dày đặc. LAP (TrackMate) và Hungarian (Python) thì không hỏng.

**Thí nghiệm nhiễu** (`results/noise_sweep.csv`, hình `noise_robustness.png`) cộng nhiễu Gauss σ = 0–140 lên toàn bộ video `crossing`, lấy trung bình 3 seed. Không làm mượt, pipeline bắt đầu bỏ sót vật từ σ ≈ 80 và IDF1 của Kalman còn 0,44 ở σ = 140. Làm mượt Gauss σ = 1,5 trước khi phân ngưỡng giữ IDF1 = 1,00 và RMSE dưới 0,5 px trên toàn dải.

**So sánh detector với TrackMate trên `noisy`** (σ = 100, tracker Kalman, `results/detector_variants.csv`, hình `noisy_detectors.png`):

| Detector | Bỏ sót | Phát hiện thừa | IDF1 | RMSE (px) |
|---|---|---|---|---|
| Python: ngưỡng + opening 3×3, liên thông 8 hướng (mặc định) | 16 | 1 | 0,93 | 1,66 |
| Python: ngưỡng, không opening, liên thông 4 hướng | 0 | 0 | 1,00 | 0,31 |
| Python: lọc Gauss σ = 1,5 rồi ngưỡng + opening | 0 | 0 | 1,00 | 0,28 |
| TrackMate Threshold | 0 | 0 | 1,00 | 0,30 |
| TrackMate LoG (bán kính 7, quality ≥ 5) | 0 | 0 | 1,00 | 0,45 |

Với nhiễu dày, vật thể sau phân ngưỡng bị thủng lỗ. Phép opening ăn mòn vật thủng lỗ xuống dưới diện tích tối thiểu, còn liên thông 8 hướng nối các điểm nhiễu thành cụm lớn. TrackMate Threshold không dùng opening, và bản Python bỏ opening, dùng liên thông 4 hướng cho kết quả gần như trùng TrackMate (RMSE 0,31 so với 0,30). Làm mượt trước (Gauss ở Python, LoG ở TrackMate) cũng giải quyết được. Opening vẫn hữu ích với nhiễu muối (điểm sáng đơn lẻ) như ở các video gốc. `detect()` có tham số `opening` và `connectivity` để tái hiện các biến thể này.

## Số liệu đối chiếu

- `results/summary_png.csv` và `results/fiji/summary.csv` so sánh trên chính các PNG gốc.
- `results/noise_sweep.csv` ghi kết quả thí nghiệm nhiễu, có cột `blur` (0 hoặc 1,5).
- `results/detector_variants.csv` so sánh 3 biến thể detector Python trên `crossing` và `noisy`.
- Với `noisy`, `summary*.csv` có thêm các dòng `*_blur` (làm mượt σ = 1,5 trước khi phân ngưỡng). `summary.csv` đọc lại từ mp4 nén H.264, quá trình nén làm thay đổi nhiễu nên số liệu `noisy` ở đó hơi khác PNG. Khi so với Fiji, dùng `summary_png.csv`.
- `results/sweep_png.csv` khảo sát từng tham số, `results/timing_png.csv` ghi trung vị 9 lần theo từng công đoạn, bỏ đọc ảnh và dựng video.
- CSV và XML trong `results/fiji/` là đầu ra từ TrackMate (phiên bản ghi ở phần Fiji). Bảng `*_evaluation.csv` đánh dấu lần đổi ID bằng cột `id_switch`. Thêm `--details chi_tiet.csv` khi chạy score_trackmate.py để xuất bảng này.
- Nếu XML hỏi vị trí ảnh, mở chuỗi PNG thành hyperstack, lưu TIFF rồi nạp XML với stack đó. Có thể chạy lại script để tạo CSV mà không cần mở lại XML.
