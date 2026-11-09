# Phát hiện và theo dõi đối tượng chuyển động trong video

Nhóm 9 · Xử lý ảnh · PTIT

Ba video tổng hợp 320 × 180, 15 fps, nền tối có nhiễu và vật thể sáng. Mỗi kịch bản kiểm tra một điểm yếu riêng:

| Kịch bản | Frame | Nội dung | Thuật toán cần có |
|---|---|---|---|
| `separate` | 43 | 3 vật đi tách nhau | Nearest neighbor là đủ |
| `crossing` | 43 | 2 vật đi ngược chiều, vật 1 bị ẩn ở frame 20–23 (đánh số từ 0) đúng lúc giao nhau | Kalman (dự đoán khi mất quan sát) |
| `dense` | 30 | 2 đoàn 3 vật nối đuôi, cách nhau 16 px. Đoàn trên tăng tốc từ 6 lên 11 px/frame | Hungarian (ghép tối ưu toàn cục) |

Trong `dense`, khi bước di chuyển vượt nửa khoảng cách (8 px, từ frame 16), spot gần nhất của mỗi track lại là vật đi sau. Cách ghép tham lam đổi ID liên tục, còn Hungarian vẫn đúng vì ràng buộc mỗi spot chỉ gán cho một track. Cột `visible` trong `*_truth.csv` đánh dấu khi vật thể xuất hiện trong ảnh.

## Xem demo ngay

- `data/separate.mp4` và `data/crossing.mp4` là video đầu vào.
- `results/crossing/nearest.mp4`, `hungarian.mp4` và `kalman.mp4` là video gắn ID và vệt quỹ đạo. Tua đến khoảng giây 1,6 để xem lúc hai vật thể đổi phía.
- `results/dense/nearest.mp4` và `hungarian.mp4` cho thấy đoàn trên bị đổi ID khi tăng tốc.
- `results/figures/` chứa 3 biểu đồ cho báo cáo, sinh bằng `python plots.py`.
- `results/summary.csv` chứa số liệu Python. CSV đánh giá từng phương pháp chỉ rõ frame và vật thể đổi ID. Video đầu ra hiển thị các quan sát đã gán ID, nên vệt được ngắt qua khung hình vắng mặt.

## Chạy bằng Fiji TrackMate

Tải [Fiji](https://fiji.sc/) và dùng TrackMate 8.x. Các kết quả trong results/fiji được chạy headless từ TrackMate 8.1.6 và ImageJ trong bộ Fiji (Java 21). Quy trình bấm GUI dưới đây dùng để tái hiện và trình diễn.

### Chạy bằng giao diện

1. Chọn **File › Import › Image Sequence…**, mở ảnh đầu tiên trong `data/crossing/` và kiểm tra 43 ảnh theo thứ tự tên. Có thể lặp lại với `data/separate/`.
2. Chọn **Image › Hyperstacks › Stack to Hyperstack…**, đặt Channels = 1, Slices = 1, Frames = 43. Đặt Frame Interval = 0,066667 s ở **Image › Properties…**, với kích thước pixel 1 × 1 và đơn vị pixel. Kiểm tra thanh trượt **T**.
3. Chọn **Plugins › Tracking › TrackMate**. Chọn **Thresholding detector**, kênh 1, ngưỡng 110. Bỏ Simplify contours nếu cần đối chiếu script. Ở bước lọc spot, dùng Quality 35–240 để loại chấm nhiễu theo diện tích. Bước Preview ở frame đánh số 21 có hai vật thể hiện.
4. Chạy riêng từng tracker trên cùng stack. Nearest-Neighbor dùng bán kính ghép 24 px. Simple LAP dùng Linking 24 px, Gap-closing 36 px, Max frame gap 6 và bật Allow gap closing. Kalman dùng Initial search radius 24 px, Kalman search radius 24 px và Max frame gap 6. Đây là tham số khởi đầu, dùng hai bộ video để kiểm tra ảnh hưởng của việc nối đoạn và dự đoán.
5. Hiển thị spots và tracks, tô màu theo ID. Dùng **Tracks** để xuất bảng Spots và Tracks, lưu phiên TrackMate XML, dùng **Capture overlay** nếu cần video minh họa. Ghi lại phiên bản Fiji/TrackMate, cấu hình và kết quả thực tế.

### Chạy tự động và chấm điểm CSV

Mở `TrackMate_Nhom9.groovy` trong Fiji Script Editor, chọn **Groovy**, nhấn **Run**, chọn thư mục `data/crossing` (lặp lại với `data/separate` và `data/dense`) và thư mục đích `results/fiji`. Script tạo XML và CSV cho 3 tracker, với frame tính từ 0. Mỗi spot hiện nhưng không được nối được xem là một quỹ đạo đơn khi chấm. Mở XML bằng **Plugins › Tracking › Load a TrackMate file** nếu stack nguồn khả dụng, hoặc chạy GUI để tạo overlay.

Sau khi cài các gói Python ở phần dưới, chấm một CSV hoặc cả thư mục (ghi lại `results/fiji/summary.csv` và các `*_evaluation.csv`), rồi vẽ lại biểu đồ:

```powershell
python score_trackmate.py data/crossing_truth.csv results/fiji/crossing_kalman.csv
python score_trackmate.py --folder results/fiji
python plots.py
```

Kết quả Fiji hiện có gồm `separate` và `crossing`. Kịch bản `dense` cần chạy script Groovy trên `data/dense` rồi chấm lại như trên, biểu đồ sẽ tự thêm cột.

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
| dense (IDF1) | 0,77 | 1,00 | 1,00 | chưa chạy | chưa chạy | chưa chạy |

Thí nghiệm nhiễu (`results/noise_sweep.csv`, hình `noise_robustness.png`) cộng nhiễu Gauss σ = 0–140 lên toàn bộ video `crossing`, lấy trung bình 3 seed. Không làm mượt, pipeline bắt đầu bỏ sót vật từ σ ≈ 80 và IDF1 của Kalman còn 0,44 ở σ = 140. Làm mượt Gauss σ = 1,5 trước khi phân ngưỡng giữ IDF1 = 1,00 và RMSE dưới 0,5 px trên toàn dải. Ý tưởng này tương tự detector LoG/DoG của TrackMate, vốn lọc ảnh trước khi tìm spot.

## Số liệu đối chiếu

- `results/summary_png.csv` và `results/fiji/summary.csv` so sánh trên chính các PNG gốc.
- `results/noise_sweep.csv` ghi kết quả thí nghiệm nhiễu, có cột `blur` (0 hoặc 1,5).
- `results/sweep_png.csv` khảo sát từng tham số, `results/timing_png.csv` ghi trung vị 9 lần theo từng công đoạn, bỏ đọc ảnh và dựng video.
- CSV và XML trong `results/fiji/` là đầu ra từ TrackMate 8.1.6. Bảng `*_evaluation.csv` đánh dấu lần đổi ID bằng cột `id_switch`. Thêm `--details chi_tiet.csv` khi chạy score_trackmate.py để xuất bảng này.
- Nếu XML hỏi vị trí ảnh, mở chuỗi PNG thành hyperstack, lưu TIFF rồi nạp XML với stack đó. Có thể chạy lại script để tạo CSV mà không cần mở lại XML.
