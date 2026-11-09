# Cơ sở thuật toán và liên hệ mã nguồn

Nhóm 9 – Phát hiện vật thể sáng và theo dõi chuyển động trong video.

## 1. Bài toán và giả thiết

Đầu vào: các frame xám 8 bit, camera cố định, vật sáng hơn nền. Đầu ra: tọa độ quan sát, ID và lịch sử quỹ đạo; riêng Kalman có thêm trạng thái vị trí/vận tốc. Không có bước nhận dạng ngữ nghĩa và không tự loại vật đứng yên. Một vật sáng đứng yên vẫn là detection hợp lệ.

Đơn vị trong Python: pixel và frame. `F` dùng Δt=1 frame, nên vận tốc là px/frame. Video 15 fps có thể đổi sang px/s bằng nhân 15; nếu đổi fps hoặc mô hình thời gian phải xem lại `F`, `Q`, gate và khoảng mất quan sát.

## 2. Phân đoạn và centroid (`tracking.detect`)

Ngưỡng cố định:

$$B(x,y)=\begin{cases}1&I(x,y)>T\\0&\text{ngược lại}\end{cases}.$$

Baseline T=110. Biên `>` quan trọng: pixel có giá trị đúng 110 thuộc nền. Ngưỡng toàn cục phù hợp khi phân bố mức xám vật/nền tách được; không bảo đảm trên nền phức tạp hoặc ánh sáng thay đổi.

Bản mở rộng dùng Otsu để cực đại phương sai giữa hai lớp:

$$\sigma_B^2(t)=\omega_0(t)\omega_1(t)[\mu_0(t)-\mu_1(t)]^2.$$

Histogram gồm 256 bin; bỏ điểm chia có lớp rỗng; chọn cực đại đầu tiên khi hòa. Ảnh hằng dùng chính mức xám đó, nên phép `>` cho mask rỗng. Otsu không phải giải pháp tổng quát cho mọi cảnh, nhất là nền/vật không tạo hai lớp cường độ rõ ràng.

Opening với phần tử cấu trúc vuông 3×3:

$$B\circ S=(B\ominus S)\oplus S.$$

Opening loại điểm sáng nhỏ và cầu nối mảnh nhưng có thể làm mất vật nhỏ, thay đổi biên/tâm. Tiếp theo gán nhãn liên thông 8 và giữ vùng có diện tích 35–240 pixel. Hai vật chạm nhau có thể thành một vùng; một vùng quá lớn còn bị loại hoàn toàn.

Với tập pixel vùng R, diện tích A và tâm hình học:

$$A=|R|,\quad \bar x=\frac{1}{A}\sum_{(x,y)\in R}x,\quad \bar y=\frac{1}{A}\sum_{(x,y)\in R}y.$$

`center_of_mass(mask, labels, indices)` dùng mask nhị phân, nên đây là centroid hình học, không phải tâm có trọng số theo độ sáng gốc. SciPy trả (y,x), code đảo thành (x,y). Mask trả về là mask sau opening, chưa xóa các vùng bị loại theo diện tích; tập centroid mới là detections sau lọc.

## 3. Nearest-neighbor và Hungarian (`tracking.associate`)

Với n track và m detection, tính khoảng cách từ vị trí tham chiếu track đến detection:

$$d_{ij}=\|p_i-z_j\|_2.$$

Chỉ cho phép cạnh có d≤gate. Nearest ở đây là greedy toàn cục: sắp toàn bộ cạnh hợp lệ theo khoảng cách rồi chọn cạnh nếu cả track và detection chưa được dùng. Không phải mỗi track tự chọn độc lập (cách đó có thể dùng trùng detection).

Ví dụ gate=5:

| | Detection 1 | Detection 2 |
|---|---:|---:|
| Track 1 | 2 | 3 |
| Track 2 | 4 | 9, không hợp lệ |

Greedy lấy (1,1), khiến track 2 không có detection. Hungarian với mục tiêu của repo chọn (1,2), (2,1), tạo 2 cặp, tổng 7. Bài toán có cho phép không ghép và **ưu tiên số cặp hợp lệ trước**, rồi mới tối thiểu tổng khoảng cách; không so 2 và 7 như hai nghiệm cùng số cặp.

Code thêm dummy rows/columns thành ma trận (n+m)×(n+m). Chi phí không ghép `P=(min(n,m)+1)*(gate+1)` đủ lớn so với tổng chi phí các cạnh hợp lệ; cạnh cấm lớn hơn nữa. Hungarian tự cài dùng potential và augmenting path. Độ phức tạp của solver vuông O((n+m)^3), bộ nhớ ma trận O((n+m)^2).

`--solver scipy` giữ nguyên ma trận và mục tiêu tối ưu, thay phần giải bằng SciPy. Đây là tối ưu cài đặt, không phải thuật toán tracking mới. Hai solver có thể chọn khác khi có nghiệm đồng hạng; test so số cặp và tổng chi phí, không yêu cầu ID số giống nhau.

## 4. Kalman và ghép detection (`Track.predict`, `Track.observe`)

Trạng thái và đo lường:

$$s=[x,y,v_x,v_y]^T,\quad z=[x,y]^T,$$

$$F=\begin{bmatrix}1&0&1&0\\0&1&0&1\\0&0&1&0\\0&0&0&1\end{bmatrix},\quad
H=\begin{bmatrix}1&0&0&0\\0&1&0&0\end{bmatrix}.$$

Dự đoán:

$$\hat s_t^-=F\hat s_{t-1},\quad P_t^-=FP_{t-1}F^T+Q.$$

Ghép vị trí dự đoán với detections bằng Hungarian có gate; sau đó cập nhật:

$$K=P^-H^T(HP^-H^T+R)^{-1},\quad \hat s=\hat s^-+K(z-H\hat s^-).$$

Code dùng `solve` thay vì nghịch đảo tường minh, và dạng Joseph cho covariance:

$$P=(I-KH)P^-(I-KH)^T+KRK^T.$$

Cấu hình baseline: `Q=0.10 GGᵀ`, `G=[0.5I; I]`, `R=I`, `P0=diag(4,4,100,100)`, vận tốc đầu bằng 0. Đây là lựa chọn tham số cho demo, chưa phải tham số tối ưu đã được ước lượng từ video thật.

Không có detection: chỉ predict, tăng `misses`; loại track khi `misses > max_missing`. Phải gọi update ở **mọi frame**, kể cả frame rỗng. Với `max_missing=5`, có thể qua 5 frame vắng rồi ghép lại ở frame kế tiếp; sau frame vắng thứ 6 track bị loại. Không được suy ra tham số `MAX_FRAME_GAP` của mọi tracker Fiji có cùng ý nghĩa chỉ từ tên.

Một bước Kalman giúp dự đoán trong mất quan sát; không tự tách được vùng dính và không bảo đảm giữ ID khi detector trả tâm sai. Đảo hướng nhanh trái với giả thiết vận tốc gần hằng có thể tăng sai số vị trí đã lọc.

## 5. Quan sát, trạng thái và quỹ đạo

`method.csv` chỉ chứa observations. `method_states.csv` chứa trạng thái của active tracks, cờ `observed` và `misses`. Với Kalman, dòng `observed=0` là dự đoán; với nearest/Hungarian là vị trí cuối được giữ lại. Không dùng toàn bộ states làm detections khi chấm FP/FN.

Overlay vẫn vẽ các quan sát được gán ID và ngắt nét qua khoảng mất quan sát. Lịch sử vẽ giới hạn 30 điểm. CLI ghi CSV/video theo luồng; hàm `run_video` mặc định giữ observations để tương thích benchmark, CLI truyền `collect=False` để tránh giữ toàn bộ video trong RAM.

## 6. Tài liệu đối chiếu

Các sách dưới đây là tài liệu nguồn do nhóm cung cấp; không sao chép toàn bộ sách vào repo công khai.

1. Giáo trình Xử lý ảnh PTIT (2018): §3.4, trang 60–61 (opening/closing); §3.6.2 (thành phần liên thông); §4.3.1–4.3.2, trang 76–79 (ngưỡng mức xám/histogram).
2. Gonzalez & Woods, Digital Image Processing, 4th ed. (2018): §9.3 (opening/closing), §9.5 phần extraction of connected components, §10.3 (thresholding). Số trang PDF có thể khác trang in; ưu tiên dẫn mục.
3. Sandipan Dey, Hands-On Image Processing with Python (2018): Chương 6, trang in 225; Chương 8, trang in 285 (Otsu).
4. [TrackMate LAP trackers](https://imagej.net/plugins/trackmate/trackers/lap-trackers): ghép hai bước, squared-distance costs và gap closing. Python online Hungarian không phải bản sao Simple LAP.
5. [TrackMate Kalman tracker](https://imagej.net/plugins/trackmate/trackers/kalman-tracker): mô hình chuyển động tuyến tính, khởi tạo từ cặp spot và occlusion.
6. [Kuhn (1955)](https://doi.org/10.1002/nav.3800020109): bài toán assignment.

Sách XLA làm cơ sở cho phân đoạn/hình thái; các chi tiết triển khai TrackMate cần dẫn tài liệu TrackMate, không gán cho giáo trình PTIT. `key_xla.pdf` là tài liệu câu hỏi/ôn tập, không dùng thay nguồn lý thuyết chính.
