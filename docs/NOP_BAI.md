# Hồ sơ nộp bài tập lớn — Nhóm 9

Cập nhật 17/11/2026. Đây là cách đóng gói đề xuất dựa trên yêu cầu đã cung cấp: lý thuyết đủ sâu; Fiji/ImageJ làm tham chiếu và kiểm chứng; Python cài đặt, thực nghiệm và đánh giá. **Chưa có thông tin về hạn nộp, biểu mẫu bìa, dung lượng và định dạng bắt buộc trên LMS.** Một thành viên nộp, ghi rõ Nhóm 9; kiểm tra thông báo môn học trước khi gửi.

## Nộp những gì?

| Thành phần | Tệp/nguồn để dùng | Trạng thái |
|---|---|---|
| Báo cáo chính | [BAO_CAO_NHOM9.md](BAO_CAO_NHOM9.md), bổ sung bìa rồi xuất PDF | Đã soạn nội dung tiếng Việt; nhóm xác nhận hành chính/phân công |
| Lý thuyết chi tiết | [LY_THUYET.md](LY_THUYET.md), [METRICS.md](METRICS.md) | Đưa vào báo cáo hoặc phụ lục |
| Source tái lập | Toàn bộ repo ZIP, requirements, Python, Groovy, tests, README | Có; nộp đúng commit đã kiểm tra |
| Số liệu và bằng chứng Fiji | [báo cáo thực nghiệm](../output/person1/public_release/report.md), [F4 CSV](../output/person1/f4/comparison.csv), [Fiji stress](../output/person1/fiji_stress), [ảnh GUI](../results/fiji/screenshots) | Có CSV/XML/ảnh và cấu hình |
| Demo | [crossing](../results/crossing), [dense](../results/dense), [noisy](../results/noisy) | Có video tổng hợp |
| Slide bảo vệ, nếu thầy yêu cầu | [SLIDE_VA_DEMO.md](SLIDE_VA_DEMO.md) | Nội dung từng slide và kịch bản demo; chưa phải PPTX |
| Video thật/GT | Không có media thật và GT tay trong gói công khai | Không được ghi đã đánh giá accuracy trên video thật |

Gợi ý tên: `Nhom09_BaoCao.pdf`, `Nhom09_Source.zip`, `Nhom09_Slides.pdf` (nếu có bảo vệ). Có thể để minh chứng/demo trong ZIP source, không cần nộp lặp nếu LMS giới hạn dung lượng. Không đính kèm nguyên sách giáo trình/PDF có bản quyền vào repo công khai; dẫn tài liệu tham khảo.

## Cách hoàn thiện báo cáo

1. Mở [báo cáo tiếng Việt](BAO_CAO_NHOM9.md). Điền môn/lớp, giảng viên, ngày nộp và **phân công thực tế**. Danh sách thành viên đã lấy từ đề bài, nhóm kiểm tra lại.
2. Kèm phần công thức trong [LY_THUYET.md](LY_THUYET.md) và quy ước metric. Dùng hình gốc trong `output/person1/public_release/figures`; mỗi hình phải có chú thích và nguồn CSV.
3. Chuyển sang Word/PDF bằng công cụ của nhóm, kiểm tra công thức, bảng, ngắt trang, hình và mục lục. Đây là bước xuất định dạng, không tự tạo thêm số liệu.
4. Ghi commit nguồn và môi trường của từng thí nghiệm. Báo cáo số liệu lịch sử của PR #2; sửa code ngày 17/11 không đồng nghĩa toàn bộ benchmark đã chạy lại.
5. Thêm liên kết repo/commit đã chốt. Mở PDF và thử chạy source từ thư mục sạch trước khi nộp.

## Kiểm tra source

Cài Python 3.10+, dependencies; FFmpeg/ffprobe/libx264 cần cho demo video. Fiji/TrackMate cần cho đối chiếu. Chạy từ gốc repo:

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/validate_public_release.py
python tracking.py data/crossing.mp4 --method kalman --solver scipy --output output/demo_crossing_fixed
python tracking.py data/crossing.mp4 --method kalman --threshold otsu --blur 1.5 --solver scipy --output output/demo_crossing_otsu_blur
```

Validator manifest cần checkout Git (có thư mục .git); khi tải ZIP không có .git thì bỏ lệnh validator, dùng test và demo. Lệnh demo dùng thư mục riêng từng cấu hình. Detection CSV mới: `kalman_detections.csv` hoặc `kalman_blur_detections.csv`; CSV lịch sử giữ tên cũ.

Chạy `python benchmark_png.py` để tái tạo noise sweep và lưu mean/per-run/sample-std. Lệnh này ghi lại các bảng benchmark trong `results`, vì vậy chạy trên bản sao để giữ bằng chứng cũ. Không chạy benchmark ngay trước giờ bảo vệ nếu chưa kiểm tra kết quả.

Để tái hiện Fiji, làm theo [README](../README.md) và [THUC_NGHIEM.md](THUC_NGHIEM.md). Kiểm tra XML còn tìm đúng PNG/stack trên máy thuyết trình.

## Những điều chưa thể ghi là hoàn tất

- Chưa có nhãn tay video thật; không tự dùng tracker làm GT. Nếu thầy yêu cầu đánh giá video thật, nhóm phải quay/chọn clip được phép dùng, gán nhãn và kiểm tra chéo trước khi chấm.
- Chưa chứng minh dùng chung detections giữa Fiji/Python. Không nói mọi chênh lệch là do tracker.
- Noise sweep lịch sử chỉ lưu mean 3 seed; code mới sẽ lưu per-seed và độ lệch chuẩn khi chạy lại. Không điền độ lệch chuẩn tự ước lượng.
- Cần nhóm xác nhận bìa, phân công, định dạng LMS; chưa gửi bài cho thầy.

## Checklist trước khi nhấn nộp

- [ ] Bìa ghi Nhóm 9, đủ tên/MSSV, đúng môn/lớp và giảng viên.
- [ ] Có lý thuyết, Fiji, Python, thiết kế thực nghiệm, kết quả, phân tích lỗi, kết luận và tài liệu tham khảo.
- [ ] MOTA ghi “nội bộ”, IDF1 ghi “theo centroid”; không tuyên bố đạt chuẩn MOTChallenge.
- [ ] Không gọi ID sinh ra là số vật thật; không gọi FPS đo decode/detect/track là FPS có xuất overlay.
- [ ] Source có requirements và lệnh chạy; unit tests của commit nộp đã pass.
- [ ] PDF/slide/video mở được; demo Fiji và Python thử trên máy bảo vệ.
- [ ] Một thành viên nộp đúng hạn và định dạng LMS; giữ biên nhận nộp.
