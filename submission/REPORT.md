# Báo cáo Day 09 — Cao Quang Linh, 2A202603050

## 1. Kết luận trước
Sau khi chạy toàn bộ pipeline trên lô 224 ảnh thô (`data/raw`), kết quả dừng ở mức: **Hold**.

- **Dữ liệu đầu vào**: 224 ảnh.
- **Dữ liệu bị loại tại cửa tiếp nhận (intake)**: 21/224 ảnh, bao gồm:
  - 2 ảnh lỗi cấu trúc file không mở được (`CORRUPT_IMAGE`).
  - 3 ảnh cạnh ngắn dưới 250px không đạt độ phân giải tối thiểu (`BAD_SIZE`).
  - 8 ảnh trùng lặp hoàn toàn theo mã băm MD5 (`DUP_IMAGE_EXACT`).
  - 3 ảnh gần trùng theo perceptual hash (`DUP_IMAGE_NEAR`).
  - 5 ảnh trùng với kho dữ liệu kiểm tra test/gold_val (`LEAK_TEST`).
- **Dữ liệu tiếp nhận vào pipeline**: 203 ảnh.
- **Trạng thái xuất dữ liệu**: Pipeline đã xuất bản nháp tại `submission/export/clean_v1/` để phục vụ kiểm tra nội bộ, chưa phát hành chính thức.
- **Lý do đưa ra quyết định Hold**:
  Về mặt cú pháp, module autofix đã xử lý toàn bộ 36 lỗi ERROR (thực hiện 35 thay đổi trong `03_fixes.csv`, trong đó 2 lỗi tên lớp viết hoa trong `data.yaml` được gộp xử lý trong 1 lần ghi file). Ở bước duyệt người mô phỏng, cả 6 ảnh thiếu nhãn ban đầu đều đã được bổ sung đầy đủ. Tuy nhiên, hàng đợi phát sinh tới 130 ảnh mang cảnh báo ngữ nghĩa. Với ngân sách duyệt giới hạn ở mức 80 ảnh, người duyệt mới chỉ xử lý được các ca ưu tiên cao nhất, để lại **44/203 ảnh (tỉ lệ 21.67%)** vẫn còn cảnh báo chưa qua rà soát. Con số này vượt ngưỡng trần 10.00% (`warn_ratio_hold`), do đó theo đúng luật của gate, tôi giữ lô dữ liệu ở trạng thái Hold, chưa cho phép phát hành.

## 2. Lỗi và phân việc
Dưới đây là bảng thống kê các mã lỗi phát hiện từ file `02_error_list_v1.csv` (trước khi sửa):

| Mã lỗi | Số lượng | Đơn vị xử lý | Lý do phân công |
|---|---:|---|---|
| `BAD_CLASS_ID` | 6 dòng | Máy (autofix) | ID lớp ngoài dải 0..3 (93, 7, -1). Máy không thể tự đoán nhãn nên xóa dòng lỗi (`drop_line`). |
| `BAD_CLASS_NAME` | 2 lỗi | Máy (autofix) | Tên lớp trong `data.yaml` viết hoa ('Person', 'Bus'). Máy ghi lại danh sách chuẩn theo cấu hình (`rename_classes`). |
| `BAD_FORMAT` | 3 dòng | Máy (autofix) | Dòng nhãn chứa NaN/Inf hoặc thiếu cột tọa độ. Máy xóa dòng hỏng (`drop_line`). |
| `BAD_SIZE` | 3 ảnh | Máy (autofix) | Cạnh ngắn ảnh < 250px không đủ độ phân giải để train. Loại ảnh và file nhãn (`remove_image`). |
| `BOX_OUT_OF_IMAGE` | 8 dòng | Máy (autofix) | Box tràn viền vượt dung sai `overflow_tol`. Máy cắt tọa độ về [0, 1] (`clip_box`), nếu diện tích về 0 thì xóa dòng. |
| `BOX_ZERO` | 4 dòng | Máy (autofix) | Box có chiều rộng hoặc chiều cao $\le 0$. Máy xóa dòng lỗi (`drop_line`). |
| `CORRUPT_IMAGE` | 2 ảnh | Máy (autofix) | File ảnh lỗi hoặc bị cắt cụt không load được qua PIL. Loại ảnh khỏi dataset (`remove_image`). |
| `DUP_BOX` | 7 dòng | Máy (autofix) | Hai box cùng lớp vẽ đè lên nhau với IoU > 0.9. Máy giữ box trước và xóa box lặp phía sau (`drop_line`). |
| `DUP_IMAGE_EXACT` | 8 ảnh | Máy (autofix) | Ảnh trùng mã băm MD5 với ảnh khác trong lô. Loại ảnh trùng (`remove_image`). |
| `DUP_IMAGE_NEAR` | 3 ảnh | Máy (autofix) | Ảnh tương đồng theo khoảng cách phash $\le 8$. Loại ảnh lặp (`remove_image`). |
| `LEAK_TEST` | 5 ảnh | Máy (autofix) | Ảnh trùng với kho test/val. Bắt buộc loại bỏ để tránh ô nhiễm dữ liệu kiểm tra (`remove_image`). |
| `MISSING_LABEL_FILE` | 6 ảnh | Người (review) | Ảnh chưa có file nhãn. Máy không tự tạo nhãn giả hay file rỗng, chuyển vào hàng đợi ưu tiên cao (`needs_label`). |
| `BOX_HUGE` | 3 dòng | Người (review) | Cảnh báo box chiếm > 95% diện tích ảnh. Cần người xác minh vật thể thật hay gán nhầm background. |
| `BOX_TINY` | 6 dòng | Người (review) | Cảnh báo box có cạnh < 12px. Cần người đối chiếu guideline xem có giữ lại vật thể nhỏ không. |
| `CLASS_RARE` | 4 cảnh báo | Người (review) | Cảnh báo lớp xuất hiện ít hơn 5 box trong lô để người quản lý cân nhắc phân bố lớp. |
| `EMPTY_LABEL` | 12 ảnh | Người (review) | File nhãn rỗng. Cần người kiểm tra đây là ảnh nền thật sự hay annotator bỏ quên vật thể. |
| `POSSIBLE_FALSE_POS` | 29 dòng | Người (review) | Box nhãn không khớp dự đoán nào từ model lớn. Cần người kiểm tra xem nhãn có vẽ nhầm không. |
| `POSSIBLE_LOOSE_BOX` | 31 dòng | Người (review) | Nhãn và model cùng lớp nhưng IoU thấp (0.3 đến 0.5). Cần người nắn lại viền box. |
| `POSSIBLE_MISSING` | 68 cảnh báo | Người (review) | Model dự đoán vật thể tin cậy nhưng nhãn thiếu box. Cần người vẽ bổ sung. |
| `POSSIBLE_WRONG_CLASS` | 18 cảnh báo | Người (review) | Box nhãn và dự đoán khớp vị trí nhưng khác tên lớp. Cần người phân định lại ngữ nghĩa. |

**Nhận xét về hàng đợi duyệt `05_review_queue.csv`:**
- Khi kiểm tra file hàng đợi, tôi thấy thuật toán sắp xếp thứ tự duyệt rất hợp lý: những ảnh dính nhiều lỗi chồng chéo được đẩy lên trên cùng. Điển hình như `img_0020` (14.53 điểm) và `img_0185` (10.05 điểm) vừa bị lỗi cú pháp phải drop dòng, vừa bị nghi ngờ sai lớp và thiếu nhãn. Ngay sau hai ảnh này là 6 ảnh bị thiếu file nhãn (`NEEDS_LABEL`, 10.00 điểm). Việc ưu tiên nhóm này giúp người duyệt bắt buộc phải xử lý để cứu pipeline khỏi bị Rework.
- Với ngân sách giới hạn 80 ảnh, tôi quan sát thấy người duyệt đã gán nhãn cho toàn bộ 6/6 ảnh thiếu nhãn (100%), sửa được 14/18 lỗi nghi sai lớp (`POSSIBLE_WRONG_CLASS`, 77.8%) và 42/68 lỗi nghi thiếu nhãn (`POSSIBLE_MISSING`, 61.8%). Dù vậy, do hàng đợi có tới 130 ảnh, 50 ảnh còn lại không được duyệt tới, trong đó 44 ảnh vẫn còn cảnh báo.

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Phân tích đánh đổi |
|---|:---:|:---:|---|---|
| `duplicates.phash_dist` | 2 | **8** | DUP_IMAGE_NEAR: <br>1.00 / 0.50 / 0.67 → **1.00 / 0.67 / 0.80** | Tại ngưỡng 2, Recall chỉ đạt 0.50 (bỏ sót 3/6 ảnh gần trùng). Nâng lên 8 giúp tăng Recall lên 0.67 mà Precision trên tập calib vẫn giữ mức 1.00. |
| `second_opinion.conf` | 0.25 | **0.50** | POSSIBLE_MISSING: <br>0.50 / 1.00 / 0.67 → **0.57 / 1.00 / 0.73** <br>POSSIBLE_WRONG_CLASS: <br>0.56 / 0.83 / 0.67 → **0.56 / 0.83 / 0.67** | Tại 0.25, Precision của MISSING chỉ đạt 0.50 (cứ 2 cảnh báo thì có 1 báo động giả, làm ngợp hàng đợi). Nâng lên 0.50 giúp tăng Precision lên 0.57, F1 đạt 0.73 và vẫn giữ được Recall trọn vẹn 1.00. |

**Lưu ý trong quá trình lựa chọn ngưỡng calibration:**
Quá trình chọn ngưỡng cho tôi một bài học thực tế về việc không nên tin máy móc vào tập calibration. Tập calib chỉ có 39 ảnh với các lỗi được chèn nhân tạo khá rõ rệt. Nếu chỉ nhìn bảng sweep và chọn điểm có F1 cao nhất, tôi sẽ chọn ngay `phash_dist = 16` vì nó cho F1 = 0.91, Recall = 0.83 và Precision = 1.00.
Tuy nhiên, khi tôi áp dụng thử ngưỡng 16 vào lô 224 ảnh thật (`data/raw`), khoảng cách Hamming 16 bit (sai khác tới 25%) trở nên quá lỏng trước các ảnh đường phố phức tạp. Hậu quả là số ảnh bị loại ở bước intake vọt từ 16 lên 26 ảnh, tức là xóa nhầm mất 10 ảnh bình thường (chẳng hạn `img_0013` bị nhận nhầm là trùng với ảnh test). Vì lỗi trùng ảnh sẽ kéo theo hành động xóa hẳn ảnh khỏi dataset (`remove_image`), tôi chọn cách tiếp cận an toàn: ưu tiên Precision cao để không xóa nhầm dữ liệu tốt, chấp nhận dừng lại ở `phash_dist = 8` (trên calib đạt Precision 1.00, Recall 0.67).

Tương tự với `second_opinion.conf`, nếu tôi nâng ngưỡng lên 0.70 hay 0.80 để ép số lượng cảnh báo giảm xuống nhằm lách qua cổng Release, thì trên thực tế Recall của `POSSIBLE_MISSING` sẽ sụt từ 1.00 xuống 0.75. Nghĩa là model checker bỏ sót mất 1/4 số vật thể bị thiếu nhãn. Tôi chọn `conf = 0.50` vì nó nâng Precision từ 0.50 lên 0.57 (bớt báo động giả), mà vẫn giữ được Recall trọn vẹn 1.00.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Kiểm tra hoạt động của cơ chế gate:**
Để kiểm chứng cửa chặn có thực sự hoạt động độc lập hay không, tôi chạy thử nghiệm với cờ `--budget 0` (không cho người duyệt can thiệp):
```powershell
python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb
```
Kết quả ghi nhận: Do không có người duyệt, 6 ảnh thiếu nhãn vẫn còn nguyên ở vòng QC thứ 3. Cổng gate lập tức chặn lại với kết luận **Rework**, trả về mã thoát **20** (`Exit code: 20`) và không hề tạo thư mục xuất dataset `work/exp_nb`. Thử nghiệm này khẳng định cơ chế gate chặn lỗi bắt buộc rất chặt chẽ, không bị qua mặt và cung cấp mã lỗi rõ ràng cho CI.

**(b) Các điểm mù mà pipeline không phát hiện được:**
Trong quá trình kiểm tra nhãn và đối chiếu ảnh qua `viz_labels.py`, tôi nhận thấy một số điểm mù mà pipeline hiện tại không bắt được:
1. **Lệch viền nhẹ (Loose box nhẹ)**: Những box vẽ thừa mép khoảng 5–10% (IoU với model trong khoảng 0.55–0.70) vượt qua cả hai ngưỡng `iou_loose` (0.50) và `iou_match` (0.50). Cả quy tắc hình học lẫn model checker đều xem đây là box chuẩn, nên lỗi này lọt lưới.
2. **Cả annotator và teacher model cùng đoán sai**: Ở những ca khó như xe bán tải lai giữa car và truck, hoặc người đi bộ bị che khuất một phần trong bóng râm, model yolo26l cũng đoán nhầm hoặc conf bị tụt xuống dưới ngưỡng lọc diện tích (`min_area_px = 600`). Khi cả hai bên cùng sai một kiểu, pipeline không có cơ sở thứ ba để phát hiện.
3. **Ảnh trùng bị xoay hoặc crop mạnh**: Thuật toán perceptual hash chỉ chịu được nén ảnh hoặc đổi kích thước nhẹ. Nếu ảnh bị crop mất hơn 30% diện tích hoặc bị biến đổi hình học lớn, khoảng cách phash sẽ vượt quá ngưỡng 8 và lọt qua khâu kiểm tra intake.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Chưa chạy: Phần huấn luyện đối chứng trên Google Colab là mục tùy chọn (chấm riêng 15 điểm). Do môi trường máy cục bộ không trang bị GPU phù hợp để chạy YOLO, tôi tập trung hoàn thiện chính xác toàn bộ phần lõi của pipeline AutoQC (được xác thực qua lệnh `python scripts/check_submission.py --no-train` đạt 0 LỖI). Dataset sạch đã được xuất khẩu sẵn tại `submission/export/clean_v1/` để phục vụ thực nghiệm khi có tài nguyên tính toán.

## 6. Quyết định và ghi chú AI
**(a) Quyết định cuối cùng:**
- Quyết định: **Hold**.
- Điều kiện để chuyển sang **Release**: Dự án cần cấp thêm ngân sách để người duyệt xử lý tiếp 44 ảnh còn tồn đọng trong hàng đợi. Cụ thể, cần xử lý dứt điểm cảnh báo trên tối thiểu 24 ảnh nữa để đưa số ảnh dính cảnh báo về mức $\le 20$ ảnh (dưới ngưỡng trần 10% của 203 ảnh). Sau đó chạy lại với `--resume-after-review` để chốt Release.

**(b) Ghi chú sử dụng AI:**
- **Prompt chính**: "Viết hàm `run(ds, cfg)` trong `label_format.py` duyệt các dòng YOLO, kiểm tra định dạng 5 cột số, dải class ID, box zero, box tràn viền so với tolerance, lọc duplicate box theo IoU và cảnh báo tiny/huge box."
- **Cách tôi kiểm tra code do AI sinh**: Tôi chạy từng bài unit test tương ứng `python -m pytest tests/test_<module>.py -q` cho từng hàm ngay sau khi viết, đồng thời mở file đọc lại từng dòng để chắc chắn script không đụng chạm hay ghi đè vào dữ liệu gốc trong `data/raw`.
- **Trường hợp AI đề xuất sai**: Trong module `autofix.py`, AI đề xuất luôn dùng hành động `clip_box` cho mọi trường hợp `BOX_OUT_OF_IMAGE`. Nhưng đối với những box nằm hoàn toàn bên ngoài khung hình (tọa độ âm hoặc > 1.0), sau khi clip thì kích thước bị đưa về 0 (box rỗng). Unit test `test_box_fully_outside_is_dropped_not_negative` đã báo đỏ ca này. Tôi phải điều chỉnh lại logic: nếu box sau khi clip có chiều rộng hoặc chiều cao $\le 0$ thì chuyển sang hành động `drop_line` thay vì tiếp tục lưu box hỏng.
