# WORKSPACE CLEANUP PLAN: VIETIRR-RAG

**Document Version:** 1.0.0  
**Date:** 2026-10-30  
**Author:** Senior Software Architect & Repository Maintenance Auditor  
**Guiding Principle:** **PRESERVATION FIRST — CLEANUP SECOND**  
**Policy Setting:** `DELETION_ALLOWED = FALSE` (Zero permanent deletions)

---

## 1. Executive Summary & Problem Statement

Over several months of intensive scientific development across multiple LLM reasoning platforms (Gemini, Codex) and research sprints, the VietIRR-RAG workspace accumulated:
- **9,310 files** totaling **5.07 GB**.
- **75 historical ZIP handover packages** occupying **601.34 MB** directly in the project root directory.
- **88 loose markdown reports, CSV audits, SHA-256 manifests, and batch JSONL files** in the root.
- Unpacked historical audit snapshots (`VR4.4_new/`, `VR4_4_COMPLETE_AUDIT_HANDOFF/`, `snapshots/`).

While the underlying engineering pipeline (FastAPI, R6 Retrieval, Qwen 2.5:7B, Citation Guard, Ontology Shadow, and Vue/React frontend) is operational and passes **585/586 unit tests**, the clutter in the workspace root creates confusion for new developers, course instructors, and academic reviewers.

This Cleanup Plan outlines a **safe, zero-destructive, reversible, and traceable** strategy to de-clutter the workspace.

---

## 2. Workspace Classification Matrix

All 9,310 files have been audited and cataloged in [`WORKSPACE_INVENTORY.csv`](WORKSPACE_INVENTORY.csv) across 10 official categories:

| Category | File Count | Description & Policy |
| :--- | :---: | :--- |
| **CACHE_OR_GENERATED** | 4,338 | Pycache `.pyc`, `.pytest_cache`, `.model_cache`, `.tmp`, and build outputs. Retained locally, ignored by Git. |
| **REPORT_AND_PRESENTATION** | 1,696 | Deliverables, course presentation slides, UI snapshots, and scientific reports. Preserved in `reports/` and `deliverables/`. |
| **RESEARCH_EXPERIMENT** | 1,500 | Historical experiment scripts, ablations, candidate rankings, and diagnostic traces. Preserved in `research/` and `scripts/`. |
| **HISTORICAL_HANDOVER** | 1,072 | 85 handover ZIP files and unpacked audit snapshot directories. Archived into `archive/handovers/`. |
| **DATA_AND_INDEX** | 340 | Official corpus PDFs, OCR layout text, structured tables, BM25/BGE-M3 indexes, and manifests. Strict immutability. |
| **ACTIVE_RUNTIME** | 192 | Active backend modules (`src/viirr_api/`), pipeline (`src/viirr_rag/`), retrieval (`src/viirr_retrieval/`), ontology shadow (`src/viirr_ontology/`), frontend (`frontend/`), and database (`vietirr.db`). Strict preservation. |
| **PROJECT_DOCUMENTATION** | 100 | Master documentation, architecture guides, licenses, and handover notes. Preserved in `docs/` and root. |
| **ACTIVE_TESTS** | 51 | Unit, integration, and regression test suites in `tests/`. Strict preservation. |
| **RESEARCH_BASELINE** | 12 | Frozen R6 baseline metrics, R5 retrieval benchmarks, and DEV-93 evaluation sets. Strict immutability. |
| **UNKNOWN** | 9 | Miscellaneous configuration dotfiles (.dockerignore, etc.). Preserved in place. |
| **Total Files** | **9,310** | **100% of workspace files accounted for** |

---

## 3. Relocation & Archival Strategy

### 3.1 Tier 1: Low-Risk Reversible Moves (Executed)
- **Target:** 75 historical handover ZIP files currently residing in workspace root `.` (totaling 601.34 MB).
- **Destination:** `archive/handovers/`
- **Rationale:** These ZIPs were created as snapshot outputs by packaging scripts during earlier development cycles. Relocating them to `archive/handovers/` reduces root files from 163 to 88 without modifying any code, breaking any tests, or deleting any data.
- **Verification:** Every ZIP has its CRC32 and SHA-256 fingerprint verified and indexed in [`ARCHIVE_INDEX.md`](ARCHIVE_INDEX.md).

### 3.2 Tier 2: Medium-Risk Files (Preserved in Place)
- **Target:** Loose root audit reports, evaluation manifests, and batch JSONLs (`READINESS_COUNTS.json`, `READINESS_DATA_SNAPSHOT.md`, `PRODUCTION_DEPLOYMENT_GUIDE.md`, `FINAL_E0_E4_*.jsonl`, `VIETIRR_NEW_QA_BATCH_*.jsonl`).
- **Policy:** **PRESERVE IN PLACE**. Code audit revealed that `src/viirr_api/app.py` directly references `READINESS_COUNTS.json` and `READINESS_DATA_SNAPSHOT.md`, while `seed.py` references `PRODUCTION_DEPLOYMENT_GUIDE.md`. To guarantee zero runtime breakage and 100% test passing, these files remain in root.

### 3.3 Tier 3: High-Risk Core Assets (Strictly Protected)
- **Target:** `src/`, `tests/`, `frontend/`, `configs/`, `data/`, `ontology/`, `vietirr.db`.
- **Policy:** **NO MODIFICATION / NO RELOCATION**. Zero changes to import paths, database URLs, or index paths.

---

## 4. Deletion Policy (`DELETION_ALLOWED = FALSE`)
In strict adherence to the project prompt:
- **Number of permanently deleted files:** **0**
- Any temporary artifact or duplicate file identified during the audit is documented in [`PENDING_DELETION_REVIEW.md`](PENDING_DELETION_REVIEW.md) for future user review.

---

## 5. Rollback & Recovery Mechanism
A comprehensive rollback procedure is documented in [`RESTORE_GUIDE.md`](RESTORE_GUIDE.md). If needed, all archived handover files can be returned to root in a single command.
