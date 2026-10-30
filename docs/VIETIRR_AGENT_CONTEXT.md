# VIETIRR-RAG AGENT CONTEXT & RESEARCH FREEZE HANDOVER
**Last updated:** 2026-10-30 (Sprint: Website Content & Data Synchronization)  
**Author:** Senior Full-Stack Engineer, RAG Engineer, Evaluation Auditor & QA Reviewer  
**Thesis Deadline:** 02/11/2026  
**Status:** `WEBSITE_SYNCED_DEMO_READY` — METRICS UNIFIED, DEMO SUITE VERIFIED, REPORT UPDATED, FROZEN  

---

## 1. Project Identity & Environment
- **Project Name:** VietIRR-RAG — Vietnamese Irrigation Document Retrieval-Augmented Generation.
- **Operational Corpus Version:** `V4_R6_FROZEN` (93 PDFs, 2,578 pages, 27,144 evidence units: 27,053 text + 91 table).
- **Historical Baseline Corpus:** `V3.2_FINAL_SEMANTIC` (89 PDFs, 2,479 pages, 27,045 units). Stage P2 Recall@20 = 74.23%.
- **Git Branch:** `sync/v4-research-artifacts`
- **Environment:** Windows, NVIDIA GPU 16 GB VRAM, local Ollama `qwen2.5:7b`, PyTorch 2.1+, Python 3.10 (`.venv_b2`), FastAPI backend (port 8000), React/TypeScript/Vite frontend (port 5173).
- **Core Research Policy:** Frozen R6 Retrieval Baseline. Deny-by-default on public V4 PDF redistribution. Zero paid APIs. No GraphRAG. Ontology operates strictly in **Shadow Mode** (`verification_mode = "shadow"`).

---

## 2. Audited & Stabilized Components Map

| Thành phần | Đường dẫn thực tế | Trạng thái | Chi tiết kỹ thuật |
| :--- | :--- | :--- | :--- |
| **Single Source of Truth** | [`frontend/src/config/systemMetrics.ts`](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/frontend/src/config/systemMetrics.ts) | **VERIFIED** | Đồng bộ toàn bộ số liệu: 93 PDF, 27.144 units, Hit@100 = 91.40%, Page Hit@5 = 67.74%, Leakage = 0.00%. |
| **Demo Questions Suite** | [`frontend/src/config/demoQuestions.ts`](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/frontend/src/config/demoQuestions.ts) | **VERIFIED** | 8 câu hỏi thử nghiệm thực tế phân 4 nhóm, có tab lọc, click điền input và nút chạy ngay. |
| **Hero Trust Cards** | [`frontend/src/components/hero/CleanEngineeringHero.tsx`](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/frontend/src/components/hero/CleanEngineeringHero.tsx) | **VERIFIED** | Hiển thị 93 PDF, 27.144 units, 91.40% Hit@100, 0.00% Leakage (Phân tách Train/Dev). |
| **Navigation Header** | [`frontend/src/pages/HydraulicAppPage.tsx`](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/frontend/src/pages/HydraulicAppPage.tsx) | **VERIFIED** | Loại bỏ "Báo cáo Nghiên cứu", chỉ giữ "Không gian Tra cứu" và "Báo cáo Khoa học", giữ nút 16:9. |
| **Scientific Report** | [`frontend/src/components/storytelling/ScientificScrollReport.tsx`](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/frontend/src/components/storytelling/ScientificScrollReport.tsx) | **VERIFIED** | Giữ nguyên template 10 section, cập nhật số liệu R6 DEV-93, phân biệt rõ V4 vs V3.2, mô tả đúng Shadow Ontology. |
| **API Response Contract** | [`viirr_api/schemas.py`](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/viirr_api/schemas.py), [`viirr_api/r6_service.py`](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/viirr_api/r6_service.py) | **VERIFIED** | Chuẩn hóa các trường top-level: `abstained`, `abstention_type`, `guard_verdict`, `model_generated_answer`, `final_status`. |
| **R6 Retrieval Core** | [`viirr_retrieval/high_perf_retriever.py`](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/viirr_retrieval/high_perf_retriever.py) | **VERIFIED (Frozen)** | Dual-variant BM25 + Dense BGE-M3 -> Reranker BGE-v2-m3 -> Budget B (5 units). |
| **Citation Guard** | [`viirr_rag/pipeline.py`](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/viirr_rag/pipeline.py) | **VERIFIED** | Nhận diện mệnh đề đẳng lập liên từ ` và ` và dấu phẩy `,`; giữ đủ 2/2 citations, ngăn chặn trích dẫn giả. |
| **PDF Viewer API** | [`viirr_api/app.py`](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/viirr_api/app.py) | **VERIFIED** | Serving file PDF trực tiếp qua HTTP: `/api/v1/documents/{doc_id}/pdf?page={p}`. |
| **Frontend Production Build** | [`frontend/dist/`](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/frontend/dist/) | **VERIFIED** | `npm run build` thành công mã thoát 0, không có lỗi TypeScript hay bundle size warning. |

---

## 3. Test Suites Status
1. `tests/test_qa_canonical_contract.py`: **6 / 6 PASS**.
2. `tests/test_citation_guard_repair.py`: **5 / 5 PASS**.
3. `tests/test_answer_evaluator.py`: **17 / 17 PASS**.
4. Grounding suites (`test_p5_grounding.py`, `test_p5_round2_relations.py`, `test_p5_round3_grounding_safety.py`): **54 / 54 PASS**.
5. **Tổng số unit/regression tests:** **82 / 82 PASS (100% trong ~0.35s)**.
6. **E2E Demo Questions Verification:** 8 / 8 tested on live local GPU API with recorded traces.

---

## 4. Deliverables Package
Tập hợp hồ sơ bàn giao đồng bộ tại [`deliverables/website_sync_final/`](file:///d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag/deliverables/website_sync_final/):
- `WEBSITE_UPDATE_SUMMARY.md`: Tổng hợp toàn bộ thay đổi frontend, backend và styling.
- `METRICS_SOURCE_AUDIT.md`: Kiểm toán nguồn số liệu, đối chiếu V4 vs V3.2, phân tích leakage.
- `DEMO_QUESTIONS.json`: Bộ câu hỏi demo đã kiểm thử có latency, citation count và target doc/page.
- `DEMO_E2E_RESULTS.md`: Chi tiết trace từng câu hỏi thực tế qua GPU pipeline.
- `SCIENTIFIC_REPORT_UPDATE.md`: Bản cập nhật nội dung chuẩn khoa học cho Báo cáo Khoa học.
- `FINAL_WEB_ACCEPTANCE.md`: Biên bản nghiệm thu đầy đủ 14 tiêu chí kỹ thuật.
