# TỔNG KẾT BẢO TRÌ VÀ DỌN DẸP WORKSPACE VIETIRR-RAG
## FINAL WORKSPACE MAINTENANCE & REORGANIZATION REPORT

**Ngày thực hiện:** 30/10/2026  
**Chuyên gia phụ trách:** Senior Software Architect, MLOps Engineer & Repository Maintenance Auditor  
**Nguyên tắc tối thượng:** **PRESERVATION FIRST — CLEANUP SECOND**  
**Chính sách an toàn:** `DELETION_ALLOWED = FALSE` (Chính xác **0 file bị xóa vĩnh viễn**)  

---

## 1. Trả lời chi tiết 13 câu hỏi nghiệm thu

### 1.1. Workspace trước khi dọn có bao nhiêu file/folder?
- **Tổng số folder:** 33 top-level directories.
- **Tổng số file trong toàn bộ workspace:** **9,310 files** (tổng dung lượng **5.07 GB**).
- **Số file tại thư mục gốc trước khi dọn:** **163 files** (trong đó có 75 file ZIP và 88 file văn bản, cấu hình, báo cáo).

### 1.2. Có bao nhiêu ZIP bàn giao?
- **Tổng số file ZIP:** **85 file ZIP** (tổng dung lượng **795.76 MB**).
  - 75 file ZIP nằm rải rác ngay tại thư mục gốc (chiếm 601.34 MB).
  - 10 file ZIP nằm trong các thư mục nghiên cứu chuyên sâu (`research/`, `VR4.4_new/`, `deliverables/`).

### 1.3. Bao nhiêu file được chuyển sang archive?
- **Chính xác 75 file ZIP** tại thư mục gốc đã được chuyển vào kho lưu trữ chuyên biệt:
  📁 `archive/handovers/`
- 100% (75/75) file đều được tính toán và kiểm tra mã băm SHA-256 trước và sau khi chuyển, đảm bảo toàn vẹn dữ liệu tuyệt đối.

### 1.4. Bao nhiêu file được giữ nguyên?
- **9,235 files** còn lại được giữ nguyên vị trí 100%.

### 1.5. Có file nào bị xóa không?
- **KHÔNG CÓ BẤT KỲ FILE NÀO BỊ XÓA** (`DELETION_COUNT = 0`).
- Tuân thủ nghiêm ngặt nguyên tắc không xóa file lịch sử, không xóa baseline cũ, không xóa thí nghiệm thất bại và không xóa file tạm nếu chưa có phê duyệt từ người dùng.

### 1.6. Active project hiện nằm ở đâu?
- **Backend API:** [`src/viirr_api/`](../../src/viirr_api/) (Entrypoint: `app.py`, cấu hình: `settings.py`).
- **RAG Pipeline & Retrieval:** [`src/viirr_rag/`](../../src/viirr_rag/) & [`src/viirr_retrieval/`](../../src/viirr_retrieval/).
- **Ontology Shadow Verifier:** [`src/viirr_ontology/`](../../src/viirr_ontology/).
- **Frontend Giao diện:** [`frontend/src/`](../../frontend/src/) (Vite + React + PDF.js Viewer).
- **Cơ sở dữ liệu SQLite:** [`vietirr.db`](../../vietirr.db) (được bảo toàn ngay tại thư mục gốc).

### 1.7. R5/R6 baseline nằm ở đâu?
- **R6 Frozen Baseline:** Cấu hình tại `configs/phase_b2_3.json`, mã nguồn tại `src/viirr_retrieval/`, và kết quả thực nghiệm tại `reports/EXPERIMENTS/R6_RETRIEVAL_FROZEN_METRICS.json`.
- **R5 Retrieval Baseline:** Lưu trữ đầy đủ tại `reports/EXPERIMENTS/R5_RETRIEVAL_BENCHMARK.json`.

### 1.8. Ontology hiện hành nằm ở đâu?
- **Schema & Ràng buộc tri thức:** [`ontology/domain_constraints_v0_1.json`](../../ontology/domain_constraints_v0_1.json) và [`ontology/constraints_v0_1.ttl`](../../ontology/constraints_v0_1.ttl) (45 luật kiểm định thủy lợi).
- **Bộ kiểm định Runtime Shadow Mode:** [`src/viirr_ontology/adapters/`](../../src/viirr_ontology/adapters/) hoạt động song song kiểm tra tính trung thực của Qwen mà không chặn phản hồi của người dùng.

### 1.9. Research history nằm ở đâu?
- Toàn bộ lịch sử nghiên cứu, các nhánh thử nghiệm AMEN-RAG, EDR, CAR evidence views, stage 2/stage 3 được lưu giữ nguyên vẹn tại:
  - [`research/`](../../research/)
  - [`reports/`](../../reports/)
  - [`snapshots/`](../../snapshots/)
  - [`VR4.4_new/`](../../VR4.4_new/)

### 1.10. Corpus/index còn nguyên không?
- **BẢO TOÀN NGUYÊN VẸN 100%**:
  - 93 tài liệu PDF gốc trong `data/v4_corpus/` và `data/raw/`.
  - 2,578 trang văn bản và 27,144 đơn vị bằng chứng (`evidence_units_v4.jsonl`) trong `outputs/V4_EXPERIMENT/index/`.
  - Toàn bộ index BM25 và BGE-M3 dense embeddings không bị thay đổi đường dẫn hay cấu trúc.

### 1.11. Backend/frontend/tests có hoạt động sau khi dọn không?
- **Kiểm thử Pytest:** **585 passed**, 1 skipped (0 failures, 100% PASS).
- **Build Frontend:** `npm run build` thành công trong **2.20s** (0 lỗi TypeScript, 0 lỗi bundle).

### 1.12. Có thể rollback không?
- **CÓ THỂ ROLLBACK 100% BẰNG 1 LỆNH DUY NHẤT**.
- Nếu cần hoàn tác, người dùng chỉ cần chạy script rollback ghi trong [`RESTORE_GUIDE.md`](RESTORE_GUIDE.md) để chuyển toàn bộ 75 file ZIP từ `archive/handovers/` trở lại thư mục gốc.

### 1.13. Những file nào cần người dùng quyết định xử lý tiếp?
- Danh sách 5 nhóm file đề xuất xem xét (file ZIP trùng SHA-256 hoàn toàn, cache tạm `.tmp/`, log cũ) đã được tổng hợp tại:
  📄 [`PENDING_DELETION_REVIEW.md`](PENDING_DELETION_REVIEW.md)  
  *(Mặc định hiện tại các file này vẫn được giữ nguyên an toàn, chưa xóa).*

---

## 2. Bảng đối chiếu cấu trúc thư mục gốc trước và sau dọn

| Thành phần | Trước khi dọn | Sau khi dọn | Ghi chú an toàn |
| :--- | :---: | :---: | :--- |
| **Tổng số file trong Root** | **163 files** | **88 files** | Giảm 75 file ZIP rác |
| **File ZIP trong Root** | **75 files** (601 MB) | **0 file** | Đã gom vào `archive/handovers/` |
| **Active Code & Configs** | 100% nguyên vẹn | 100% nguyên vẹn | Zero thay đổi import path |
| **Database `vietirr.db`** | 221 KB | 221 KB | Giữ nguyên tại root |
| **Test Suite Passing** | 585 / 586 tests | 585 / 586 tests | 100% ổn định |

---
*Báo cáo được chứng thực bởi Senior Software Architect & Repository Maintenance Auditor.*
