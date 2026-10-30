# RESEARCH INDEX: EXPERIMENTAL ABLATIONS & SCIENTIFIC ARTIFACTS

**VietIRR-RAG Project**  
**Audit Date:** 2026-10-30  
**Curator:** Senior Research Software Engineer & MLOps Team  

---

## 1. Overview
This index catalogs all major experimental tracks, ablation studies, and evaluation protocols conducted during the development of VietIRR-RAG. In accordance with open science standards, both successful pipeline improvements and negative/non-promoted experiments are systematically documented.

---

## 2. Master Experiment Registry

| Experiment ID | Topic & Objective | Primary Artifacts | Status | Outcome / Metrics |
| :--- | :--- | :--- | :---: | :--- |
| **EXP-R6-BASE** | R6 Frozen Retrieval Baseline (BM25 + BGE-M3 + RRF + BGE Reranker) | `reports/EXPERIMENTS/R6_RETRIEVAL_FROZEN_METRICS.json` | **PROMOTED** | Hit@3: 94.6%, MRR@5: 0.891; selected as authoritative production retriever |
| **EXP-R6-TABLE** | Table-aware structure retrieval pilot | `reports/EXPERIMENTS/R6_RETRIEVAL_TABLE_PILOT_METRICS.json` | **PROMOTED** | Table cell retrieval accuracy improved by +18.4% |
| **EXP-EDR** | Evidence-Discriminative Re-ranking (EDR) | `research/edr_discriminative_reranking/` | Historical Ablation | High precision but increased latency by 240ms; kept as ablation |
| **EXP-CAR** | Context-Aware Routing (CAR) for evidence view generation | `research/car_evidence_views/` | Historical Ablation | Valuable multi-hop routing insights; core logic merged into R6 |
| **EXP-AMEN** | Active Memory Evidence Navigation (AMEN-RAG) | `src/viirr_retrieval/amen_navigation.py` | Research Prototype | Explores recursive graph traversal across inter-reservoir networks |
| **EXP-ONT-A0-A3** | Ontology Verifier Shadow Ablation (A0: No Guard, A1: Citation Only, A2: Full Shadow, A3: Enforced) | `research/ontology_final_consistency/` | **PROMOTED (SHADOW)** | Proved Shadow Mode achieves zero false rejections while auditing 100% of telemetry numbers |
| **EXP-STAGE3** | Stage 3 Page-Aware & Scope-Aware evidence assembly | `scripts/run_stage3_page_aware_experiment.py` | **PROMOTED** | Eliminated oracle leakage and ensured strict provenance binding |
| **EXP-E0-E4** | Unified E0-E4 pipeline comparison across 5 model configurations | `FINAL_E0_E4_METRICS.json`, `FINAL_E0_E4_TRACES.jsonl` | Historical Baseline | Established definitive performance trade-offs between speed and faithfulness |

---

## 3. Negative & Non-Promoted Experiments (Preservation Rationale)

1. **EDR Heavy Discriminator**:
   - *Hypothesis*: Adding a second-stage cross-encoder discriminator would filter spurious text regions.
   - *Finding*: While precision on table cells increased by +2.1%, latency jumped from 180ms to 420ms per query.
   - *Decision*: Not promoted to production. Retained in `research/edr_discriminative_reranking/` as an important scientific baseline.
2. **Ontology Strict Enforcement (Mode A3)**:
   - *Hypothesis*: Blocking any answer that does not strictly conform to OWL ontology constraints.
   - *Finding*: Caused 8.3% false rejections on colloquial expressions and valid approximations.
   - *Decision*: Adopted **Shadow Mode (A2)** instead, which provides full diagnostic telemetry without user-facing disruption.

---
*Certified by VietIRR-RAG Research Engineering Team.*
