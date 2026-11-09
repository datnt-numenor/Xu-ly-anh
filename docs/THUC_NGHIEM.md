# Giao thức thực nghiệm và kiểm chứng Nhóm 9

## Phạm vi đã kiểm chứng

- `data/separate`, `data/crossing`: dữ liệu tổng hợp gốc, 43 frame, 15 fps.
- `results/fiji`: CSV/XML TrackMate 8.1.6 lưu từ trước. Đợt cải tiến này chấm lại CSV và đọc cấu hình XML; **không chạy lại Fiji**. Chỉ đổi tên cột RMSE trong bảng tổng hợp, không thay số liệu Fiji.
- `results/stress`: thực nghiệm Python mới, 5 kịch bản × 5 seed × 2 detector × 3 tracker = 150 cấu hình, mỗi chuỗi 80 frame. Tất cả là dữ liệu tổng hợp.
- Chưa có kết quả video thật được gán nhãn hoặc kết quả Fiji cho bộ stress. Không ghi những phần này là đã hoàn thành.

## Tái lập

Chạy từ thư mục gốc repo, Python 3.10+, cài `requirements.txt`. Hai benchmark cũ cần FFmpeg/ffprobe/libx264; bộ stress và unit test không cần FFmpeg.

```powershell
python -m unittest discover -s tests -v
python benchmark.py
python benchmark_png.py
python experiments.py
python compare_detectors.py data/crossing results/fiji/crossing_lap.csv --output results/detector_comparison/crossing
python score_trackmate.py data/crossing_truth.csv results/fiji/crossing_lap.csv --gate 8
```

`experiments.py` dùng SciPy cho ghép tối ưu để giảm thời gian chạy. CLI video và benchmark cũ mặc định dùng solver tự cài. Hai solver có cùng mục tiêu tối ưu; khi có nghiệm đồng hạng, ID cụ thể có thể khác. Các kiểm tra so cardinality và tổng chi phí, không áp đặt thứ tự ID.

Để xuất dữ liệu stress cho Fiji, dùng thư mục output khác để không ghi đè kết quả 5 seed:

```powershell
python experiments.py --seeds 0 --export-data data/stress --output output/stress_seed0
```

Trong Fiji chạy `TrackMate_Nhom9.groovy`, chọn `data/stress/overlap_seed0` và thư mục đích. Script dùng số frame thực tế của stack. Chấm với `data/stress/overlap_seed0_truth.csv`.

Cấu hình script Fiji hiện dùng ngưỡng cố định 110; không được gọi đây là bản đối chiếu Otsu theo từng frame. Bộ stress phải được chạy Fiji thực tế rồi mới đưa kết quả vào bảng.

## Định nghĩa chỉ số

- `matched`: số cặp GT thấy được – detection, khoảng cách không quá 8 px. Ghép một-một, tối đa số cặp rồi tối thiểu tổng khoảng cách.
- `missed`, `false_positive`: GT thấy được không có cặp; detection không có cặp. Chấm trên hợp các frame trong GT và dự đoán, gồm cả frame chỉ có dự đoán.
- `id_switches`: ID dự đoán khác ID từng ghép gần nhất với cùng GT, kể cả qua khoảng mất quan sát. Đây là định nghĩa nội bộ; **không tuyên bố tương đương MOTChallenge/IDF1/HOTA**.
- `track_ids`: số ID khác nhau xuất hiện trong observations; một quỹ đạo có thể chứa ID switch dù số lượng ID bằng số vật.
- `matched_detection_rmse_px`: căn trung bình bình phương khoảng cách của các cặp detection–GT đã ghép; giá trị thấp không bảo đảm recall tốt. Tên cũ là `rmse_px`, thứ tự và ý nghĩa số không đổi.
- `observed_state_rmse_px`: sai số trạng thái tại những quan sát đã được ghép. Giữ nguyên cặp xác định bằng detection, không ghép lại trạng thái để làm đẹp kết quả.
- `hidden_truth`, `hidden_predicted`, `hidden_state_rmse_px`: số GT bị ẩn, số trạng thái không có quan sát còn nối với ID trước khi ẩn, RMSE trên phần có trạng thái. Bắt buộc đọc RMSE cùng coverage `hidden_predicted/hidden_truth`. Với nearest/Hungarian, đây là giữ vị trí cuối cùng, không phải ngoại suy vận tốc.
- RMSE không xác định để trống, không điền 0. Với GT `visible=0`, không tính FN trong detection score; trạng thái dự đoán không đưa vào observations.

Nếu muốn precision/recall: `P=matched/(matched+FP)`, `R=matched/(matched+FN)`; mẫu số bằng 0 thì để trống. Không trộn `visible=0` vào recall phát hiện.

## Kịch bản và kiểm soát biến

| Kịch bản | Thay đổi có chủ đích | Giới hạn |
|---|---|---|
| separate | Ba vật tách nhau, đi tuyến tính | Dễ; không đại diện video thật |
| occlusion | Vật 1 ẩn frame 36–39, vật khác ở hàng khác | Tách riêng mất quan sát khỏi gộp vùng |
| overlap | Hai vật cùng hiện diện, cùng hàng và giao nhau | GT có hai tâm nhưng ảnh có thể chỉ có một vùng |
| turn | Vật 1 đảo hướng ở giữa chuỗi | Cho thấy độ trễ của mô hình vận tốc hằng |
| illumination | Nền tăng 25→135, vật tăng 95→205 | Thử giới hạn ngưỡng 110, không suy rộng Otsu luôn tốt |

Mỗi cảnh 320×180, 3 đĩa bán kính 7 px, nhiễu nền Gaussian σ=8 và 25 điểm sáng ngẫu nhiên/frame. Seed 0–4 chỉ thay nhiễu; **không phải 5 tập chuyển động độc lập**. Để suy rộng cần thay cả tốc độ, hình dạng, mật độ và nền. Cùng một chuỗi và detections được dùng cho ba tracker. Giữ gate=24, max_missing=5, diện tích 35–240; không chọn tham số riêng theo kết quả test.

## Kiểm chứng Fiji theo từng tầng

1. Cùng PNG gốc, 1 channel, 1 slice, đúng T; frame bắt đầu 0; tọa độ pixel, không dùng µm khi so với GT pixel.
2. So detector trước bằng `compare_detectors.py`: matched/unmatched và sai khác tâm. Đây là độ đồng thuận với Fiji, không phải độ chính xác với GT.
3. Đọc XML để kiểm tra cấu hình. Python có opening; detector Fiji hiện không có bước tương ứng. Ghi rõ sự khác biệt, không gọi hai pipeline là đồng nhất.
4. Simple LAP có ghép frame-to-frame và nối đoạn; Python Hungarian ghép online trên active tracks. Khác khoảng cách/bình phương khoảng cách, chi phí không ghép, gate và gap.
5. Muốn cô lập tracker hoàn toàn, cần cấu hình một thí nghiệm dùng chung detections trong cả hai môi trường; repo hiện chưa cung cấp importer detections vào Fiji.
6. Lưu XML, CSV, log phiên bản và ảnh GUI. XML cũ thiếu đường dẫn ảnh đầy đủ; nên lưu stack TIFF cạnh XML và thử nạp lại trên máy khác trước buổi trình bày.

## Giao thức video thật còn cần nhóm thực hiện

Quay 10–20 giây bằng camera cố định, ba vật sáng trên nền tối, có một lần đi ngang nhau, một lần che khuất và một lần đổi hướng. Không dùng dữ liệu riêng tư hoặc gán nhãn tự động làm ground truth.

- Chọn đoạn khoảng 100–200 frame; chuyển thành PNG không mất dữ liệu, giữ tốc độ khung hình.
- Gán nhãn tay `frame,object_id,x,y,visible`, nhất quán ID; nếu bị che thì đánh dấu `visible=0` và ghi quy tắc xác định tâm. Không biết tọa độ thật khi bị che thì không chấm hidden-state RMSE.
- Một thành viên gán nhãn, thành viên khác kiểm tra các frame giao nhau/che khuất.
- Chọn threshold/gate trên đoạn phát triển riêng; khóa cấu hình trước khi chấm đoạn test.
- Chạy cả Fiji và Python, ghi FP/FN/ID switch và các frame lỗi. Không thay số liệu tổng hợp hiện có bằng số tự ước lượng.

## Đo tốc độ

`results/stress/solver_timing.csv`: chỉ đo association sau khi có ma trận khoảng cách, có một lượt warm-up, 9 lần, median/P25/P75, số vật 3/10/30/100. Kiểm tra hai solver có cùng cardinality và tổng chi phí trước khi đo. Không phải FPS end-to-end.

`results/stress/environment.json` lưu môi trường và hash mã nguồn; `base_commit` là commit nền tại lúc chạy, hash mới xác định nội dung code thực nghiệm. `results/timing_png.csv` là thời gian detection/tracker của benchmark cũ sau chạy lại, chưa bao gồm I/O.

Nguồn ngẫu nhiên, cấu hình và bảng per-run đều được lưu. Sai lệch thời gian giữa máy/container là bình thường; không sử dụng tốc độ đo ở đây như cam kết hiệu năng trên máy nhóm.
