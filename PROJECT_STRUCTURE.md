# VIETIRR-RAG PROJECT STRUCTURE & REPOSITORY GUIDE

**Document Version:** 1.0.0  
**Date:** 2026-10-30  
**Maintainer:** Senior Software Architect & Repository Maintenance Auditor  

---

## 1. Top-Level Directory Organization

```text
VietIRR-RAG/
│
├── README.md                           # Master project documentation
├── PROJECT_STRUCTURE.md                # This directory guide
├── pyproject.toml                      # Project metadata and dependencies
├── .env.example                        # Example environment variables
├── .gitignore                          # Clean Git ignore rules
├── .gitattributes                      # Git line-ending normalization
├── vietirr.db                          # Active SQLite operational database
├── docker-compose.yml                  # Docker deployment orchestrator
├── Dockerfile                          # Production container specification
│
├── src/                                # Active Production Python Source
│   ├── viirr_api/                      # FastAPI backend application
│   │   ├── app.py                      # Application entrypoint & routes
│   │   ├── database.py                 # SQLAlchemy DB session management
│   │   ├── models.py                   # ORM data models
│   │   ├── repository.py               # Database queries and repositories
│   │   ├── r6_service.py               # R6 retrieval service integration
│   │   ├── schemas.py                  # Pydantic v2 API schemas
│   │   └── settings.py                 # Application configuration & env vars
│   ├── viirr_rag/                      # RAG orchestration & LLM generation
│   │   ├── pipeline.py                 # End-to-end RAG query pipeline
│   │   ├── provider.py                 # Qwen2.5:7B LLM provider
│   │   └── retrieval.py                # Retrieval orchestrator
│   ├── viirr_retrieval/                # R6 Hybrid Retrieval Engine
│   │   ├── bm25.py                     # BM25 sparse indexer
│   │   ├── dense.py                    # BGE-M3 dense retriever
│   │   ├── rrf.py                      # Reciprocal Rank Fusion
│   │   ├── reranker.py                 # BGE-Reranker cross-encoder
│   │   ├── table_aware.py              # Table cell extraction & routing
│   │   └── evidence_allocator.py       # Context budget evidence packer
│   └── viirr_ontology/                 # Ontology Verification & Shadow Mode
│       ├── schema/                     # TechnicalClaim & EvidenceSet models
│       ├── domain/                     # Hydraulic domain constraint rules
│       ├── evaluation/                 # Claim extractor & fact matcher
│       └── adapters/                   # Non-blocking shadow mode adapter
│
├── frontend/                           # Active Vue / React Frontend Web App
│   ├── src/                            # UI components, pages, topo view, PDF viewer
│   ├── public/                         # Static assets and council demo resources
│   ├── package.json                    # NPM dependencies & scripts
│   └── vite.config.ts                  # Vite build configuration
│
├── data/                               # Authoritative Corpus & Datasets
│   ├── v4_corpus/                      # Active V4 corpus manifests and source files
│   ├── raw/                            # Original third-party PDF documents
│   ├── manifests/                      # Document catalogs and migration mappings
│   ├── benchmark/                      # DEV-93 and ALL-QA benchmark datasets
│   └── tables.jsonl                    # Structured table extraction data
│
├── outputs/                            # Active & Historical Index Artifacts
│   ├── V4_EXPERIMENT/                  # Authoritative V4 experiment outputs
│   │   ├── index/                      # pages_v4.jsonl, evidence_units_v4.jsonl
│   │   └── eval/                       # V4 evaluation metric records
│   └── MASH_ER/                        # Multi-aspect retrieval cache & views
│
├── ontology/                           # Static Ontology Schema & Constraints
│   ├── domain_constraints_v0_1.json    # 45 verified hydraulic domain constraints
│   ├── constraints_v0_1.ttl            # Turtle syntax constraint definitions
│   └── viirr_hydraulic_v0_1.ttl        # Core hydraulic ontology OWL/TTL
│
├── tests/                              # Comprehensive Automated Test Suite
│   ├── test_r6_security.py             # R6 security and prompt injection tests
│   ├── test_r6_web_integration.py     # End-to-end API and search tests
│   ├── test_stage2_s2_4_verifier.py    # Ontology claim verifier tests
│   ├── test_p4_rag.py                  # Generation and citation tests
│   └── ... (51 test files, 585 passing unit & integration tests)
│
├── configs/                            # System & Experiment Configuration Files
│   ├── phase_b2_3.json                 # Active R6 production retrieval config
│   ├── v4_experiment.json              # V4 experiment parameters
│   └── prompts/                        # System prompts for generation & guard
│
├── scripts/                            # Operational & Verification Scripts
│   ├── verify_integrity.py             # Dataset and workspace integrity checks
│   ├── validate_dataset.py             # JSON schema validation
│   ├── seed_production.py              # Database seeding tool
│   └── start_production.py             # Production startup launcher
│
├── research/                           # Research Prototypes & Ablation Studies
│   ├── baselines/                      # R5 and sparse baseline comparisons
│   ├── car_evidence_views/             # Context-Aware Routing experiments
│   ├── edr_discriminative_reranking/   # Evidence-Discriminative reranker study
│   ├── ontology_final_consistency/     # Shadow mode vs. enforcement ablation
│   └── r7_constraint_evidence/         # R7 constraint validation study
│
├── reports/                            # Scientific Reports & Traces
│   ├── EXPERIMENTS/                    # Frozen R6 baseline metrics & diagnostic traces
│   ├── human_review_sample/            # Human review annotation packets
│   └── stage1/                         # Early freeze verification reports
│
├── deliverables/                       # Formal Release Packages
│   ├── course_project_final/           # Final course project submission package
│   ├── github_dataset_release/         # Standalone open dataset repository
│   └── website_final_correction/       # Website correction handover bundle
│
├── archive/                            # Historical Archive & Handover Storage
│   └── handovers/                      # 75 historical Gemini/Codex handover ZIPs
│
└── docs/                               # Project Documentation
    ├── architecture/                   # Architecture and pipeline specifications
    └── workspace_maintenance/          # Maintenance inventory, registries & plans
        ├── WORKSPACE_INVENTORY.csv     # Complete inventory of 9,310 files
        ├── CLEANUP_PLAN.md             # Reorganization and preservation plan
        ├── FILE_RELOCATION_MAP.csv     # Exact mapping of all file movements
        ├── VERSION_REGISTRY.md         # Comprehensive version and baseline ledger
        ├── RESEARCH_INDEX.md           # Master experiment and ablation index
        ├── ARCHIVE_INDEX.md            # Catalog of all 85 historical ZIPs
        ├── RESTORE_GUIDE.md            # Reversible rollback instructions
        ├── CLEANUP_VALIDATION.md       # Pre/post regression test report
        ├── PENDING_DELETION_REVIEW.md  # Proposed future candidate cleanups
        └── FINAL_WORKSPACE_SUMMARY.md  # Executive maintenance report
```

---

## 2. Directory Roles & Preservation Policies

| Directory | Primary Function | Preservation Policy |
| :--- | :--- | :---: |
| `src/` | Active backend API, RAG pipeline, and retrieval engine | **STRICTLY PROTECTED** |
| `frontend/` | React/TypeScript user interface and PDF viewer | **STRICTLY PROTECTED** |
| `data/` | Original PDFs, manifests, and benchmark questions | **STRICTLY PROTECTED** |
| `outputs/` | Pre-computed embeddings and evidence index | **STRICTLY PROTECTED** |
| `ontology/` | Hydraulic rules and OWL/TTL domain constraints | **STRICTLY PROTECTED** |
| `tests/` | Automated test suite (585 tests) | **STRICTLY PROTECTED** |
| `configs/` | Runtime configurations and prompts | **STRICTLY PROTECTED** |
| `research/` | Ablation experiments and negative results | **PRESERVED IN PLACE** |
| `reports/` | Frozen baseline evaluation metrics | **PRESERVED IN PLACE** |
| `deliverables/` | Course submission and open dataset packages | **PRESERVED IN PLACE** |
| `archive/` | Historical ZIP bundles and handover snapshots | **ARCHIVED & INDEXED** |
| `docs/` | System documentation and maintenance records | **ACTIVE DOCUMENTATION** |
