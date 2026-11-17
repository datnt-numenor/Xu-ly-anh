# Quy ước chỉ số: centroid-distance-framewise-v1

Áp dụng cho `evaluation.py`, các bảng CSV lịch sử và báo cáo. Tên cột `mota`, `idf1` được giữ nguyên để đọc lại bằng chứng cũ. Khi đặt tên bảng/slide ghi **MOTA nội bộ** và **IDF1 theo centroid**.

## Ghép và đếm lỗi

Từng frame: lấy GT có visible=1 và observations; ghép một-một trong gate Euclidean 8 px, tối đa số cặp hợp lệ rồi tối thiểu tổng khoảng cách. Không ưu tiên cặp ở frame trước. Chấm hợp các frame GT/prediction; frame rỗng prediction vẫn tạo FN, prediction-only frame vẫn tạo FP. GT vô hình không tạo FN. Dự đoán Kalman không được chấm như detection.

- TP = matched; FN = missed; FP = false_positive.
- IDSW: ID vừa ghép khác ID ghép gần nhất trước đó của cùng GT, kể cả qua gap.
- MOTA nội bộ = 1 − (FN + FP + IDSW) / số observations GT thấy được. Mẫu số 0: để trống.
- IDTP: tổng số frame nằm trong gate của phép ghép một-một tối ưu giữa các GT ID và track ID trên toàn video. IDF1 = 2 IDTP / (số GT thấy được + số predictions). Mẫu số 0: để trống.
- RMSE = căn trung bình bình phương sai số **các cặp đã ghép**; không có cặp: để trống. Không suy ra recall từ RMSE.
- track_ids: số ID sinh ra, không phải số vật thật, số IDSW hay độ chính xác.

## Vì sao không gọi đây là CLEAR chuẩn?

Cùng công thức MOTA không đủ để bảo đảm cùng metric: cách tạo cặp cũng quyết định FP/FN/IDSW. CLEAR trong TrackEval ưu tiên giữ cặp hợp lệ từ frame trước; evaluator của nhóm tối thiểu khoảng cách độc lập từng frame.

Ví dụ hai GT tại x=0,6 trong cả hai frame. Frame 0: ID1 tại 0, ID2 tại 6; frame 1: ID1 tại 4, ID2 tại 2; y=0, gate=8. Bộ chấm hiện tại đổi hai cặp để giảm khoảng cách, ghi 2 IDSW và MOTA nội bộ=0,5. Giữ cặp cũ vẫn trong gate sẽ ghi 0 IDSW. IDF1 theo centroid của ví dụ vẫn là 1 vì tất cả vị trí đều nằm trong gate của ánh xạ ID toàn cục. Đây là giới hạn của gate rộng, không phải mâu thuẫn số học.

Tham khảo triển khai gốc: [TrackEval CLEAR](https://github.com/JonathonLuiten/TrackEval/blob/master/trackeval/metrics/clear.py), [TrackEval Identity](https://github.com/JonathonLuiten/TrackEval/blob/master/trackeval/metrics/identity.py).

Không đổi quy tắc ghép rồi giữ nguyên bảng/biểu đồ cũ. Nếu bổ sung bộ chấm chuẩn, xuất bộ kết quả và tên giao thức riêng, chấm lại cả Python và Fiji. Test hồi quy hiện bảo vệ định nghĩa nội bộ và các trường hợp tính tay, không phải chứng nhận MOTChallenge.

## Phạm vi kết luận

Fiji seed0 và Python fixed seed0 được chấm chung evaluator nhưng detector và tracker khác nhau; không cô lập riêng chất lượng tracker. Simple LAP không đồng nhất với Hungarian online. Video thật chưa có GT: chỉ báo cáo số đầu ra và thời gian, không báo cáo accuracy/MOTA/IDF1.
