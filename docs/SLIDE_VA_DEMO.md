# Nội dung slide và kịch bản demo — Nhóm 9

Đây là nội dung để đưa vào PowerPoint/Canva, chưa phải tệp PPTX. Phân công người nói theo phần nhóm thực tế đã làm.

| Slide | Nội dung | Minh chứng |
|---|---|---|
| 1 | Đề tài, Nhóm 9, tên/MSSV | Bìa báo cáo |
| 2 | Bài toán và giả thiết vật sáng/nền tối; vật đứng yên vẫn được detect | Mẫu input |
| 3 | Threshold/Otsu → opening → components → centroid | d1_01_detection_steps |
| 4 | Nearest tham lam và Hungarian toàn cục; cả hai một-một | Ma trận chi phí nhỏ và d1_02 |
| 5 | Kalman predict/update, mất quan sát, states khác detections | d1_04_occlusion_kalman_prediction |
| 6 | Fiji/TrackMate: cấu hình, CSV/XML; LAP khác Hungarian online | Ảnh wizard thật |
| 7 | Thiết kế 150 Python / 15 Fiji seed0 / 30 runtime | Bảng giao thức |
| 8 | Metric: FN/FP/IDSW, MOTA nội bộ, IDF1 centroid, matched RMSE | METRICS.md |
| 9 | Kết quả chính; overlap và illumination | Bảng F4, d1_03, d1_05 |
| 10 | Tối ưu code và nhiễu; runtime có phạm vi đo cụ thể | noise CSV, runtime chart |
| 11 | Demo Python + Fiji | crossing/dense và XML |
| 12 | Đóng góp, giới hạn, hướng tiếp | Không tuyên bố accuracy video thật |

Hình nằm trong [figures](../output/person1/public_release/figures); số liệu và chú thích lấy từ [báo cáo](BAO_CAO_NHOM9.md). Dưới biểu đồ MOTA ghi “ghép centroid từng frame, không phải CLEAR chuẩn”.

## Demo khoảng 3–4 phút

1. Mở input crossing; chỉ rõ lúc mất quan sát.
2. Mở nearest và kalman overlay đã lưu trong [results/crossing](../results/crossing); giải thích ID/quỹ đạo, không dùng mỗi video làm chứng minh định lượng.
3. Mở [results/dense](../results/dense), giải thích tối ưu toàn cục so với tham lam.
4. Trong Fiji, import PNG và chạy hoặc nạp phiên XML đã kiểm tra đường dẫn. Chỉ detector, tracker, bảng spots/tracks.
5. Mở một CSV evaluation và bảng F4 để nối sự kiện nhìn thấy với số liệu.

Chạy thử trước trên đúng máy trình bày; chuẩn bị video đã lưu phòng khi Fiji khởi động lâu. Không đưa screenshot giả thay cho chạy Fiji.

## Câu hỏi dễ gặp

- **Đóng góp gì?** Cài đặt và đối chiếu thuật toán, bộ dữ liệu có GT, khảo sát có kiểm soát, phân tích lỗi và tối ưu kỹ thuật; không nhận là thuật toán mới.
- **Vì sao Hungarian vẫn sai?** Nó tối ưu chi phí khoảng cách, không biết danh tính thật; detector sai/thiếu hoặc chuyển động mơ hồ vẫn gây lỗi.
- **Vì sao Kalman không xử lý hết che khuất?** Mô hình vận tốc và thời gian sống có giới hạn; vùng gộp không tạo đủ measurements.
- **Vì sao gọi MOTA nội bộ?** Công thức giống nhưng quy tắc ghép không ưu tiên cặp frame trước như CLEAR.
- **Video thật tốt không?** Chưa có GT nên chưa trả lời accuracy; chỉ có output và runtime.
- **Fiji và Python có giống nhau?** Không: khác detector và nối đoạn; đối chiếu pipeline, chưa cô lập tracker.
