# Hướng dẫn human review V4.3

1. Chạy `python QA_REVIEW_TOOL/serve.py` từ thư mục `research/vietirr_v4_3` rồi mở URL được in ra.
2. Chọn QA theo priority. Đối chiếu PDF đúng checksum/trang trước khi xem machine finding.
3. Với bảng, kiểm tra ảnh trang, tiêu đề cột, hàng, đơn vị và chú thích; OCR/text chỉ là trợ giúp.
4. Đánh giá độc lập 10 tiêu chí bằng `PASS`, `FAIL`, `UNCERTAIN` hoặc `NOT_APPLICABLE`.
5. Không chọn `REVIEWED_*` nếu chưa nhập reviewer ID và chưa xác nhận đã trực tiếp đọc nguồn.
6. Export JSONL sau mỗi phiên. Không ghi đè ledger của reviewer khác; adjudicator lưu verdict riêng.
7. Machine status không phải gold. Revision chỉ là đề xuất cho đến khi có human acceptance.

Điểm bắt buộc: QA-016 (dấu “hơn”), QA-026 (đủ 15 hàng), QA-031/032 (phiên bản/hiệu lực), QA-034–038 (mâu thuẫn thời gian trên trang 8), và V4.1 QA-008 (không suy diễn hồi tố).
