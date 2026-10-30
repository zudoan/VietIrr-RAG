# VERSION REGISTRY: VIETIRR-RAG RESEARCH & DEPLOYMENT COHORTS

**Document Version:** 1.0.0  
**Date:** 2026-10-30  
**Repository:** VietIRR-RAG  
**Curators:** Research Data Engineering & System Architecture Team  

---

## 1. Retrieval Baselines & Pipelines

| Version Identifier | Architecture & Components | Source Location | Config / Artifacts | Status | Primary Metrics |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **R5 Baseline** | Sparse BM25 + Dense BGE-M3 hybrid retrieval with early RRF fusion | `src/viirr_retrieval/bm25.py`, `dense.py` | `reports/EXPERIMENTS/R5_RETRIEVAL_BENCHMARK.json` | Historical Baseline | Hit@3: 81.2%, MRR@5: 0.742 |
| **R6 Frozen Baseline** | BM25 + BGE-M3 + RRF + BGE-Reranker-0.6B + Page→Region + Context Allocator | `src/viirr_retrieval/`, `src/viirr_rag/` | `configs/phase_b2_3.json`, `reports/EXPERIMENTS/R6_RETRIEVAL_FROZEN_METRICS.json` | **Active Production** | **Hit@3: 94.6%, MRR@5: 0.891, Zero Leakage** |
| **AMEN-RAG** | Active Memory Evidence Navigation prototype | `src/viirr_retrieval/amen_navigation.py` | `reports/EXPERIMENTS/AMEN_RAG_RESEARCH_REPORT.md` | Research Prototype | Specialized multi-hop exploration |
| **EDR Reranking** | Evidence-Discriminative Re-ranking prototype | `src/viirr_retrieval/edr_discriminator.py` | `reports/EXPERIMENTS/EDR_DISCRIMINATIVE_RERANKING_REPORT.md` | Research Prototype | Precision-oriented ablation |

---

## 2. Corpus & Knowledge Manifest Versions

| Corpus Cohort | Document Count | Total Pages | Evidence Units | Source Paths | Status | Description |
| :--- | :---: | :---: | :---: | :--- | :---: | :--- |
| **V3.2 Final Semantic** | 89 PDFs | 2,479 | 27,045 units | `data/raw/v3_official/`, `data/v3_2_final_semantic/` | Historical Baseline | Initial standardized evaluation corpus |
| **V4.1 Frozen Corpus** | **93 PDFs** | **2,578** | **27,144 units** | `data/v4_corpus/metadata/v4_corpus_manifest.jsonl`, `outputs/V4_EXPERIMENT/index/` | **Active Operational** | Authoritative frozen corpus (+4 expansion docs: Bắc Nam Hưng, Cầu Cung, CT02, Water Plan) |

---

## 3. Ontology Verification Engine Versions

| Ontology Version | Core Components | Source Path | Constraint Specs | Operational Mode | Notes |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **V0.1 Schema** | Domain OWL/Turtle ontology and hydraulic constraint JSON | `ontology/` | `ontology/domain_constraints_v0_1.json`, `constraints_v0_1.ttl` | Static Registry | 45 hydraulic domain rules |
| **Stage 2 S2.3/S2.4** | TechnicalClaim models, Atomic Claim Extractor, Evidence Matcher, Verifier | `src/viirr_ontology/` | `tests/test_stage2_s2_4_verifier.py` | Unit Tested | Full fact-level verification engine |
| **Stage 3 Shadow Mode** | Non-blocking runtime shadow adapter auditing Qwen responses | `src/viirr_ontology/adapters/`, `src/viirr_api/r6_service.py` | `scripts/run_final_ontology_shadow_ablation.py` | **Active Shadow** | Audits claims in background without blocking generation |

---

## 4. Evaluation Benchmark Suites (VietIrrDocBench)

| Benchmark Split | Item Count | Modality | Source Location | Ground Truth Integrity |
| :--- | :---: | :--- | :--- | :---: |
| **DEV-93** | 93 | Multi-evidence (cross-page / cross-doc) | `data/benchmark/dev.jsonl`, `benchmarks/qa/dev_93.jsonl` | 100% verified against V4 index |
| **ALL-QA-545** | 545 | Comprehensive pool (core, challenge, pilot) | `data/benchmark/all_qa.jsonl` | Human validated split |
| **E2E 24 Traces** | 24 | R6 retrieval + Qwen generation diagnostic traces | `reports/EXPERIMENTS/CAR_E2E_R6_24_TRACES.jsonl` | Multi-stage pipeline diagnostics |

---

## 5. Web Platform & Course Deliverables

| Platform Component | Technology Stack | Entrypoint | Ports / URLs | Status |
| :--- | :--- | :--- | :--- | :---: |
| **Backend REST API** | FastAPI, SQLAlchemy, SQLite, Pydantic v2 | `src/viirr_api/app.py` | Port 8000 (`http://localhost:8000`) | Operational |
| **Frontend Web App** | React, TypeScript, Vite, TailwindCSS, PDF.js | `frontend/src/main.tsx` | Port 5173 (`http://localhost:5173`) | Operational |
| **Course Project Package** | Complete final submission bundle | `deliverables/course_project_final/` | N/A | Completed |
| **Open Dataset Release** | Standalone GitHub repository package | `deliverables/github_dataset_release/vietirr-rag-dataset/` | Remote: `vietirr-rag-dataset.git` | Staged & Verified |
