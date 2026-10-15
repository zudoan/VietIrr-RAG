# VietIrrDocBench — Q&A Analysis Package

Thư mục này là bản sao phục vụ kiểm tra, không di chuyển hoặc thay đổi các file phân tích gốc.

## Nội dung

- `outputs/QA_DISTRIBUTION_ANALYSIS.md`: báo cáo tổng hợp về split, nhóm câu hỏi, modality, topic, độ phân tán theo tài liệu/lĩnh vực và các rủi ro.
- `outputs/QA_ANALYSIS_SUMMARY.json`: thống kê tổng hợp dạng máy đọc.
- `outputs/QA_ANALYSIS_RECORDS.csv`: 436 Q&A TRAIN+DEV cùng nhãn phân tích.
- `outputs/QA_PER_DOCUMENT.csv`: phân bố Q&A trên toàn bộ 89 tài liệu ACCEPT.
- `outputs/QA_PER_DOMAIN.csv`: phân bố theo lĩnh vực tài liệu.
- `outputs/QA_PER_TOPIC.csv`: phân bố theo chủ đề câu hỏi.
- `outputs/QA_NEAR_DUPLICATES.csv`: các cặp câu có token-set Jaccard từ 0.80 trở lên.
- `code/build_qa_distribution_analysis.py`: script tái tạo toàn bộ báo cáo.

## Phạm vi

- Nội dung được đọc và phân tích: 343 TRAIN + 93 DEV = 436 Q&A.
- Tổng benchmark theo thống kê frozen: 545 Q&A.
- Candidate Test: 109 Q&A, vẫn niêm phong; script chỉ sử dụng aggregate đã tồn tại trong manifest/report và không đọc nội dung Candidate Test.
- Human-validated TRAIN+DEV: 0/436.

## Kết quả đáng chú ý

- 57/89 tài liệu ACCEPT có Q&A TRAIN/DEV; 32 tài liệu không có câu nào.
- Hai lĩnh vực dự báo nguồn nước và chất lượng nước chiếm khoảng 89.5% TRAIN+DEV.
- Toàn bộ 7 quy trình vận hành liên hồ ACCEPT không có QA TRAIN/DEV.
- Candidate Test có 109/109 câu thuộc một document family theo metadata frozen.
