# Phát hiện và theo dõi đối tượng chuyển động trong video

Nhóm 9 · Xử lý ảnh · PTIT

## Bản cải tiến và tài liệu bảo vệ

- [Cơ sở thuật toán, công thức và liên hệ code](docs/LY_THUYET.md).
- [Giao thức thực nghiệm, định nghĩa metric và phần còn cần kiểm chứng](docs/THUC_NGHIEM.md).
- [Kết quả chạy mới và phân tích giới hạn](docs/KET_QUA.md).
- Bộ chấm xét toàn bộ frame; tên `rmse_px` đổi thành `matched_detection_rmse_px` để phân biệt với trạng thái Kalman.
- `--threshold otsu` bổ sung ngưỡng tự động; `--solver scipy` là lựa chọn tăng tốc solver. Mặc định vẫn giữ ngưỡng 110 và Hungarian tự cài để minh họa thuật toán.
- CSV `*_states.csv` tách vị trí đã lọc/dự đoán khỏi `method.csv` chứa detection quan sát. Không trộn dự đoán vào chỉ số phát hiện.

```powershell
python -m unittest discover -s tests -v
python experiments.py
python tracking.py data/crossing.mp4 --method kalman --threshold otsu --solver scipy --output output
```

Bộ stress gồm 150 cấu hình tổng hợp, không thay thế video thật. Kết quả Fiji cũ được chấm lại; chưa chạy Fiji trên bộ stress mới. Xem giao thức để hoàn thành hai phần này trên máy nhóm.

Hai video tổng hợp, mỗi video 43 khung hình, 320 × 180, 15 fps. Nền tối có nhiễu và vật thể sáng. Trong `crossing`, vật thể 1 được ẩn có chủ đích ở frame 20–23 (đánh số từ 0). Cột `visible` đánh dấu khi vật thể xuất hiện trong ảnh.

## Xem demo ngay

- `data/separate.mp4` và `data/crossing.mp4` là video đầu vào.
- `results/crossing/nearest.mp4`, `hungarian.mp4` và `kalman.mp4` là video gắn ID và vệt quỹ đạo. Tua đến khoảng giây 1,6 để xem lúc hai vật thể đổi phía.
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

Mở `TrackMate_Nhom9.groovy` trong Fiji Script Editor, chọn **Groovy**, nhấn **Run**, chọn thư mục `data/crossing` và thư mục đích. Script tạo XML và CSV cho 3 tracker, với frame tính từ 0. Mỗi spot hiện nhưng không được nối được xem là một quỹ đạo đơn khi chấm. Mở XML bằng **Plugins › Tracking › Load a TrackMate file** nếu stack nguồn khả dụng, hoặc chạy GUI để tạo overlay.

Sau khi cài các gói Python ở phần dưới, chấm một CSV ví dụ bằng lệnh:

```powershell
python score_trackmate.py data/crossing_truth.csv fiji_out/crossing_kalman.csv
```

Ngưỡng ghép với ground truth là 8 px. Cách xử lý khoảng trống và tính chi phí của TrackMate khác bản Python, vì vậy dùng số đo từ CSV TrackMate cho phần trình diễn Fiji.

## Chạy bản Python

Cài Python 3.10+ và FFmpeg có `ffmpeg`, `ffprobe`, encoder `libx264` trong PATH. Trên Windows, có thể mở PowerShell trong thư mục đã giải nén rồi dùng:

```powershell
python -m pip install -r requirements.txt
python benchmark.py
python benchmark_png.py
python tracking.py data/crossing.mp4 --method kalman --output output
```

`benchmark.py` tái tạo dữ liệu mẫu, chạy cả ba thuật toán và kiểm tra 240 ma trận chi phí ngẫu nhiên với SciPy. `tracking.py` nhận video riêng, hỗ trợ `--method nearest`, `--method hungarian`, `--method kalman` và các cờ `--threshold`, `--min-area`, `--max-area`, `--gate`, `--max-missing`. Demo phù hợp với video vật sáng trên nền tối, tốc độ khung hình cố định. Để thử video thật, ưu tiên camera cố định, nền trơn và vật sáng tách nhau. Ngưỡng cố định sẽ đưa cả vật sáng đứng yên vào tập phát hiện.

## Chia phần thuyết trình

1. Bài toán, dữ liệu thử, phân đoạn và centroid.
2. Nearest Neighbor, ma trận chi phí và Hungarian.
3. Kalman, dự đoán lúc mất quan sát và demo giao nhau.
4. Chạy Fiji TrackMate, trình bày kết quả và giới hạn.

## Tài liệu

- [Bài báo TrackMate 7](https://doi.org/10.1038/s41592-022-01507-1)
- [Thresholding detector](https://imagej.net/plugins/trackmate/detectors/trackmate-thresholding-detector)
- [TrackMate trackers](https://imagej.net/plugins/trackmate/trackers/)
- [LAP trackers](https://imagej.net/plugins/trackmate/trackers/lap-trackers)
- [TrackMate scripting settings](https://imagej.net/plugins/trackmate/scripting/trackmate-detectors-trackers-keys)
- [Kuhn 1955](https://doi.org/10.1002/nav.3800020109)

## Số liệu đối chiếu

- `results/summary_png.csv` và `results/fiji/summary.csv` so sánh trên chính các PNG gốc.
- `results/sweep_png.csv` khảo sát từng tham số, `results/timing_png.csv` ghi trung vị 9 lần theo từng công đoạn, bỏ đọc ảnh và dựng video.
- CSV và XML trong `results/fiji/` là đầu ra từ TrackMate 8.1.6. Bảng `*_evaluation.csv` đánh dấu lần đổi ID bằng cột `id_switch`. Thêm `--details chi_tiet.csv` khi chạy score_trackmate.py để xuất bảng này.
- Nếu XML hỏi vị trí ảnh, mở chuỗi PNG thành hyperstack, lưu TIFF rồi nạp XML với stack đó. Có thể chạy lại script để tạo CSV mà không cần mở lại XML.
