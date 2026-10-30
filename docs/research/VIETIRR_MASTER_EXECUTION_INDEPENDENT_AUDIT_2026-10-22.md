# VietIRR-RAG — Đánh giá độc lập Master Plan Execution
**Ngày:** 2026-10-22  
**Đầu vào:** `VIETIRR_MASTER_PLAN_EXECUTION_HANDOVER.zip`, `VIETIRR_DOCUMENT_TO_EVIDENCE_SOURCE_FAITHFUL_HANDOVER.zip`, Master Improvement Plan.  
**Phạm vi:** Đối chiếu mã nguồn được đóng gói, 93 QA CSV, báo cáo/trace; chưa tái chạy mô hình trên corpus/index thực tế.

## Quyết định
**KHÔNG công nhận M2 là cấu hình mới tốt nhất, KHÔNG ghi đè baseline AB1 cũ.** Cần sửa hợp đồng đánh giá và benchmark riêng cho M1/M2 trước khi quyết định KEEP/REVERT. Các con số dưới đây có thể tái tính từ CSV, nhưng có sai lệch về thiết kế so sánh.

## Các phát hiện quan trọng

1. **Mất khả năng so sánh benchmark:** Cùng 93 `qa_id` và cùng 93 bộ trang đích, AB1 trong handover trước có Hit@5 **41/93 = 44,09%**; lần này `AB1` chỉ **13/93 = 13,98%**. B1 cũng đổi từ 33/93 thành 28/93. Đây là thay đổi quy trình xếp hạng/cắt kết quả, không được gọi là chỉ “chuẩn hóa cách tính”. Trong `scripts/run_master_plan_gates.py`, nhánh AB1 duyệt trang rerank nhưng nối 5 region đầu của trang hạng cao nhất rồi dừng ngay khi `len(ab1_items)>=5`: đánh giá 5 region của ~1 trang, **không phải 5 trang duy nhất**.
2. **M2 không phải 5 trang duy nhất:** `m2_items_budget_b` chọn tối đa 3 region/trang rồi dừng ở 5 region, dẫn đến thường chỉ có 2 trang. Cả `unique_page_hit@5` lẫn `region_budget_hit@5` đều được tính từ chính danh sách `m2_items_budget_b`. `m2_items_budget_a` được dựng nhưng không chấm. Hai chỉ số M2 bằng nhau trong toàn bộ 93 QA là do cách lập input, không chứng minh region đầy đủ/đúng.
3. **So sánh M1 thiếu công bằng về k:** Candidate Recall@50 mới: AB1 **51/93=54,84%** nhưng danh sách AB1 bị cắt ở **Top-20**, trong khi M1b có **Top-100**. Ở **Candidate Recall@20**, AB1 là **51/93=54,84%** còn M1b **44/93=46,77%** (thấp hơn). So với B1 global pool Recall@50 **60/93=64,52%**, M1b đạt **65/93=69,89%** (chênh +5/93), chưa đủ để tuyên bố bước nhảy lớn +15,05 điểm % so với một AB1 có k không ngang nhau.
4. **M2 không vượt baseline cũ:** M2 ghi nhận **21/93=22,58%** Hit@5 theo cách chấm mới. Đối chiếu theo `qa_id` với AB1 cũ (41/93), M2 thắng 3 câu, mất 23 câu, 67 câu không đổi. AB1 cũ **Region-budget Page Hit@5 = 28/93 = 30,11%**, vẫn cao hơn M2 **21/93**; chưa có bằng chứng phương án mới tốt hơn dưới ngân sách thực.
5. **Không triển khai đúng reranking như mô tả:** M2 chọn **một vùng có lexical overlap cao nhất** trong mỗi trang (ưu tiên bảng bằng +2 điểm) và dùng tối đa 600 ký tự của vùng này; không dùng cross-encoder để chấm nhiều sliding windows rồi max-pool như báo cáo mô tả. Mã có `build_page_windows` nhưng dùng cho dense retrieval từ cache, không phải tính cross-encoder cho nhiều windows/trang.
6. **M3 kiểm thử không chứng minh source-faithfulness trên PDF thật:** Cả 3 bài thử dựng dữ liệu giả (`DOC_740`, `DOC_922`, `EV_TAB_01`), mỗi thử nghiệm tạo **0 relations**. Test `passed` chỉ kiểm tra không có quan hệ `verified` mang `provenance_source == 'unverified_heuristic_candidate'`; không có thử nghiệm chứng minh hệ thống tạo được *quan hệ hợp lệ* từ nguồn thật. Con số 0% false accept là quan sát trên 3 test hẹp, không phải chứng minh "bảo toàn tuyệt đối".
7. **M4 chưa chạy end-to-end mới:** Script đọc lại `reports/EXPERIMENTS/END_TO_END_TRACES.jsonl`, xuất 45 bản ghi rút gọn và ghi TIE zero admission. Không có lần chạy mới của Qwen/Ontology/Stage 3 sau M1/M2 trong script này; không thể nói M1/M2 đã cải thiện hoặc kiểm định lại RQ2/RQ3.
8. **G0 no-leak chưa kiểm chứng toàn diện:** Script lấy gold riêng để chấm và không thấy truyền gold trực tiếp cho hàm ranking, đây là dấu hiệu tốt. Nhưng G0 chỉ *ghi* `tests/test_gold_leakage_adversarial.py (100% PASSED)` mà ZIP không chứa file test hoặc log chạy đó. Chỉ nên ghi `not independently verified`.
9. **Tính tái lập còn thiếu:** ZIP có một script orchestration và CSV/tổng hợp, không đóng gói các module retriever/bundler đã sửa hay test suites được khai báo; không đủ để nghiệm thu tích hợp từ riêng archive. 12/12 đường dẫn trong manifest SHA-256 đối chiếu khớp, điều này chỉ chứng minh tính toàn vẹn file, không chứng minh khoa học.

## Số liệu đã kiểm tra từ CSV
| Cấu hình trong ZIP mới | Candidate Recall@20 | Candidate Recall@50 | Page Hit@5 *như script hiện chấm* |
|---|---:|---:|---:|
| B1 | 45,16% | 64,52% | 30,11% |
| AB1 | 54,84% | 54,84% (capped at 20) | 13,98% |
| M1a | 45,16% | 62,37% | 9,68% |
| M1b | 46,77% | 69,89% | 10,75% |
| M2 | 46,77% | 69,89% | 22,58% |

## Một vòng sửa duy nhất — thứ tự tối thiểu
**P0: Sửa evaluation trước khi tối ưu.** Chạy lại 93 QA trên 4 hệ: B1 frozen nguyên mã, AB1 frozen nguyên mã, M1b+AB1-rerank, M1b+M2-rerank. Mỗi hệ có `top5_unique_pages` thật từ 5 doc/page riêng biệt; bộ `top5_regions` độc lập chứa đúng 5 region để downstream. Không dùng một danh sách region cắt ngắn để tính Page Hit@5. Candidate Recall ở k=20/50/100 phải có danh sách đủ k cho TẤT CẢ phương pháp hoặc hiển thị N/A nếu candidate pool không có đủ k. Giữ cùng 93 `qa_id`, gold page, index snapshot và ngân sách reranking. Lưu đầy đủ Top-50 với doc/page/evidence ID và per-QA win/loss.

**P1: Chỉ khi metric sạch mới đánh giá kỹ thuật M1/M2.** Với M2, chấm các cửa sổ nguồn thực sự theo query, cross-encoder tính điểm cho >1 window/trang khi có đủ windows, tổng hợp score về page. Giữ lại nếu vượt AB1 cũ (Page Hit@5 44,09%, Region-budget Page Hit@5 30,11%) hoặc cải thiện một metric chiến lược khác một cách có ý nghĩa mà không làm hỏng evidence. Nếu không, REVERT.

**P2: M3/M4 được đánh giá riêng.** M3 cần case âm tính **và dương tính** với trang/bảng thật, authentic provenance, exact region. M4 cần chạy verifier và correction thực sau sửa, không chỉ copy trace. Giữ SUPPORTED=0 và admitted=0 nếu thực sự không cải thiện.

**Quy tắc:** Đọc `docs/research/VIETIRR_RAG_MASTER_IMPROVEMENT_PLAN.md` trước khi sửa. Không sửa ngầm kết quả quá khứ, không nới rào chắn source fidelity. Thêm audit này làm ghi chú ngoài, chỉ cập nhật KEEP/REVERT trong Master Plan *sau* thực nghiệm được chuẩn hóa.
