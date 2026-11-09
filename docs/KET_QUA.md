# Kết quả và phân tích thực nghiệm

Bản chụp kết quả chạy ngày 09/11/2026. Nguồn: `results/stress/per_run.csv`, `aggregate.csv`, `solver_timing.csv` và `environment.json`. Đây là thí nghiệm tổng hợp trong môi trường kiểm tra, không phải video thật. Nếu chạy lại với code/cấu hình khác cần cập nhật tài liệu này.

## 1. Phát hiện và giữ ID

Mỗi giá trị là trung bình 5 seed; số đếm thập phân là trung bình, không phải một phần của đối tượng. Tổng GT thấy được là 240/cảnh, riêng occlusion là 236. CSV aggregate có độ lệch chuẩn mẫu. Seed chỉ thay nhiễu, không thay quỹ đạo.

| Cảnh | Detector | Tracker | Matched | FN | FP | ID switches |
|---|---|---|---:|---:|---:|---:|
| separate | fixed | nearest | 240.0 | 0.0 | 0.0 | 0.0 |
| separate | fixed | hungarian | 240.0 | 0.0 | 0.0 | 0.0 |
| separate | fixed | kalman | 240.0 | 0.0 | 0.0 | 0.0 |
| separate | otsu | nearest | 240.0 | 0.0 | 0.0 | 0.0 |
| separate | otsu | hungarian | 240.0 | 0.0 | 0.0 | 0.0 |
| separate | otsu | kalman | 240.0 | 0.0 | 0.0 | 0.0 |
| occlusion | fixed | nearest | 236.0 | 0.0 | 0.0 | 0.0 |
| occlusion | fixed | hungarian | 236.0 | 0.0 | 0.0 | 0.0 |
| occlusion | fixed | kalman | 236.0 | 0.0 | 0.0 | 0.0 |
| occlusion | otsu | nearest | 236.0 | 0.0 | 0.0 | 0.0 |
| occlusion | otsu | hungarian | 236.0 | 0.0 | 0.0 | 0.0 |
| occlusion | otsu | kalman | 236.0 | 0.0 | 0.0 | 0.0 |
| overlap | fixed | nearest | 234.0 | 6.0 | 0.0 | 2.0 |
| overlap | fixed | hungarian | 234.0 | 6.0 | 0.0 | 2.0 |
| overlap | fixed | kalman | 234.0 | 6.0 | 0.0 | 2.0 |
| overlap | otsu | nearest | 234.0 | 6.0 | 0.0 | 2.0 |
| overlap | otsu | hungarian | 234.0 | 6.0 | 0.0 | 2.0 |
| overlap | otsu | kalman | 234.0 | 6.0 | 0.0 | 2.0 |
| turn | fixed | nearest | 240.0 | 0.0 | 0.0 | 0.0 |
| turn | fixed | hungarian | 240.0 | 0.0 | 0.0 | 0.0 |
| turn | fixed | kalman | 240.0 | 0.0 | 0.0 | 0.0 |
| turn | otsu | nearest | 240.0 | 0.0 | 0.0 | 0.0 |
| turn | otsu | hungarian | 240.0 | 0.0 | 0.0 | 0.0 |
| turn | otsu | kalman | 240.0 | 0.0 | 0.0 | 0.0 |
| illumination | fixed | nearest | 159.8 | 80.2 | 344.0 | 0.2 |
| illumination | fixed | hungarian | 159.8 | 80.2 | 344.0 | 0.2 |
| illumination | fixed | kalman | 159.8 | 80.2 | 344.0 | 0.2 |
| illumination | otsu | nearest | 240.0 | 0.0 | 0.0 | 0.0 |
| illumination | otsu | hungarian | 240.0 | 0.0 | 0.0 | 0.0 |
| illumination | otsu | kalman | 240.0 | 0.0 | 0.0 | 0.0 |

### Diễn giải

- Separate: cả ba tracker giữ ID trên dữ liệu dễ. Không dùng cảnh này để tuyên bố ưu thế của thuật toán.
- Overlap: cả ba phương pháp đều trung bình 6 FN và 2 ID switch. Một vùng gộp không thể cung cấp hai centroid đúng; Kalman không tự giải quyết được phân đoạn sai.
- Illumination: Otsu khôi phục recall trong cảnh ánh sáng được thiết kế này; ngưỡng 110 bỏ vật tối lúc đầu và tạo vùng nhiễu khi nền vượt ngưỡng. Đây là kết quả có điều kiện, không khẳng định Otsu tốt với mọi nền.
- RMSE chỉ trên cặp đã ghép có thể thấp dù bỏ nhiều vật. Khi so fixed/Otsu phải đọc cùng FN/FP, không chỉ so RMSE.

## 2. Đánh giá riêng trạng thái

| Cảnh, detector fixed | Tracker | RMSE trạng thái có quan sát (px) | Coverage lúc ẩn | RMSE trạng thái lúc ẩn (px) |
|---|---|---:|---:|---:|
| separate | nearest | 0.0652 | 0/0 | không áp dụng |
| separate | hungarian | 0.0652 | 0/0 | không áp dụng |
| separate | kalman | 0.0539 | 0/0 | không áp dụng |
| occlusion | nearest | 0.0651 | 20/20 | 8.2060 |
| occlusion | hungarian | 0.0651 | 20/20 | 8.2060 |
| occlusion | kalman | 0.0532 | 20/20 | 0.1061 |
| turn | nearest | 0.0651 | 0/0 | không áp dụng |
| turn | hungarian | 0.0651 | 0/0 | không áp dụng |
| turn | kalman | 0.3818 | 0/0 | không áp dụng |

Sai số trong bảng là trung bình RMSE từng seed, không phải pooled RMSE. Khi ẩn, nearest/Hungarian giữ vị trí cũ; Kalman dự đoán bằng vận tốc. Lợi ích thấy rõ ở occlusion, còn turn cho thấy độ trễ khi đảo hướng. Bộ này không có benchmark IDF1/HOTA.

## 3. Kiểm chứng đầu ra TrackMate đã lưu

| Cảnh | Matched centroid | Không ghép được ở Fiji/Python | RMSE sai khác tâm (px) |
|---|---:|---:|---:|
| separate | 129 | 0 / 0 | 0.0042 |
| crossing | 125 | 0 / 0 | 0.0042 |

Nguồn: `results/detector_comparison/*/summary.json`, gate 2 px. Đây là độ đồng thuận detector trên PNG gốc, không phải RMSE với ground truth. Hai pipeline vẫn khác opening/cách biểu diễn vùng. CSV/XML Fiji được lưu từ trước và chưa chạy lại trong lần cải tiến này.

Bộ gốc crossing: Python nearest/Hungarian có 2 ID switch, Kalman có 0; TrackMate nearest có 2, Simple LAP/Kalman có 0. Simple LAP có gap-closing và chi phí khác; không diễn giải thành lỗi của Hungarian hoặc bằng chứng bắt buộc phải có Kalman.

## 4. Tối ưu cài đặt assignment

| Số vật | Solver | Median (ms) | P25 (ms) | P75 (ms) |
|---:|---|---:|---:|---:|
| 3 | educational | 0.124187 | 0.120872 | 0.134213 |
| 3 | scipy | 0.00647 | 0.00629 | 0.00687 |
| 10 | educational | 0.856422 | 0.812766 | 0.879458 |
| 10 | scipy | 0.010806 | 0.010576 | 0.011377 |
| 30 | educational | 6.221481 | 6.060567 | 6.270414 |
| 30 | scipy | 0.032268 | 0.031788 | 0.033171 |
| 100 | educational | 72.993346 | 71.862589 | 77.447639 |
| 100 | scipy | 0.204679 | 0.201314 | 0.213082 |

Mỗi cấu hình warm-up một lần, đo 9 lần; chỉ đo association, bao gồm tạo ma trận dummy nhưng không gồm tính ma trận khoảng cách, detection hay đọc/ghi video. Không gọi các số này là FPS toàn hệ thống. Xem cấu hình CPU/thư viện ở `environment.json`.

Đóng góp cài đặt: solver SciPy giữ cùng mục tiêu tối ưu, cache detections khi sweep tham số, lưu vệt vẽ tối đa 30 điểm và ghi CSV theo luồng ở CLI. Bản Hungarian tự cài vẫn được giữ để học và đối chiếu.

## 5. Bằng chứng kiểm tra

- 14 unit tests: frame >42, frame chỉ có dự đoán, dữ liệu rỗng/không hợp lệ, gate boundary, ID switch qua gap, vòng đời track, bộ nhớ lịch sử, trạng thái Kalman, coverage, Otsu và giới hạn overlap.
- 240 ma trận vuông so Hungarian với SciPy; 125 ma trận chữ nhật/rỗng/có gate so cả hai solver với vét cạn trong unit test.
- 18 hàng kết quả cũ Python/Fiji được chấm lại với evaluator độc lập (SciPy).
- Chạy lại benchmark video và PNG; các chỉ số cơ bản giữ nguyên, cột RMSE đổi tên. Thứ tự dòng chi tiết có thể thay đổi theo thứ tự assignment.

## 6. Phần nhóm cần hoàn tất trước khi nộp

1. Chạy lại Fiji trên máy trình diễn, lưu ảnh GUI/log phiên bản và kiểm tra nạp XML cùng stack.
2. Chạy Fiji trên PNG stress xuất bằng `--export-data`; hiện chưa có kết quả này.
3. Thu video thật và gán nhãn theo `THUC_NGHIEM.md`; hiện chưa có dữ liệu để thực hiện phần đó.
4. Đưa lý thuyết, bảng kết quả và phân tích lỗi vào báo cáo/slide chính thức, bổ sung thông tin thành viên và phân công đã thực hiện.

Các kết quả đã có hỗ trợ một kết luận giới hạn: dự đoán vận tốc giúp khi mất quan sát tuyến tính; ngưỡng tự động hữu ích trên cảnh ánh sáng thay đổi đang xét; phân đoạn gộp vùng và đảo hướng vẫn là hạn chế. Không kết luận hệ thống tổng quát hoặc đã giải quyết mọi che khuất.
