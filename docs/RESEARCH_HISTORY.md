# Research History and Experimental Lineage

## Overview

The VietIrr-RAG system evolved across several experimental generations, transitioning from an initial semantic evidence search prototype to a hierarchical, table-aware retrieval-augmented generation system with factual ontology monitoring.

---

## Experimental Milestones

### 1. Milestone B2 & Dataset V3.2 (Baseline Search Prototype)
- **Objective**: Establish baseline evidence retrieval over Vietnamese hydraulic documentation.
- **Corpus**: `V3.2_FINAL_SEMANTIC` (89 documents, 2,479 pages, 27,045 evidence units).
- **Architecture**: Single-stage dense retrieval utilizing `multilingual-e5-large`. Flat paragraph segmentation without explicit layout hierarchy.
- **Generation**: Search-only interface; no generative LLM integrated.
- **Preserved Artifacts**: Documented in `docs/B2_WINDOWS_REPRO.md`.

### 2. Milestone C1 & R1 (Hybrid Retrieval Foundations)
- **Objective**: Evaluate whether sparse lexical matching (BM25) mitigates vocabulary mismatch on technical hydraulic codes and exact reservoir names.
- **Key Findings**: Sparse BM25 demonstrated superior recall on exact proper nouns and legal decisions, while dense embeddings excelled at thematic hydrology concepts.

### 3. Milestone R5 (Early Fusion & Cross-Encoder Reranking)
- **Objective**: Combine sparse and dense candidate pools via Reciprocal Rank Fusion (RRF) and evaluate cross-encoder reranking (`BGE-Reranker-0.6B`).
- **Benchmark Evaluation (DEV-93)**:
  - Candidate Hit@100: 76.34% (71/93)
  - Page Hit@5: 63.44% (59/93)
  - Evidence Page Hit@5: 58.06% (54/93)
  - Table Region Recovery: 0.00% (tables were treated as flattened plain text).

### 4. Milestone R6 (Hierarchical Page-to-Region & Table Awareness)
- **Objective**: Overcome context dilution in multi-page engineering reports through hierarchical pruning and structured table extraction.
- **Corpus**: Expanded and frozen as `V4_R6_FROZEN` (93 documents, 2,578 pages, 27,144 evidence units).
- **Core Innovations**:
  - Two-stage localization: prune document candidates to high-relevance pages, then isolate specific bounding boxes (`TEXT_REGION` or `TABLE_REGION`).
  - Table-aware cell parser: preserves numerical matrices for elevation-capacity relationships and telemetry monitoring bulletins.
- **Benchmark Evaluation (DEV-93)**:
  - Candidate Hit@100: **91.40%** (85/93, +15.06% absolute improvement over R5)
  - Page Hit@5: **67.74%** (63/93, +4.30% over R5)
  - Evidence Page Hit@5: **61.29%** (57/93, +3.23% over R5)
  - Table Region Recovery: **17.20%** (16/93, up from 0%)
  - Paired comparison: 10 wins, 6 losses, 77 ties.
- **Preserved Artifact**: `reports/EXPERIMENTS/R6_RETRIEVAL_DEV93_METRICS.json`.

### 5. Milestone Phase E & Full-Stack Integration
- **Objective**: Deliver an end-to-end user workspace integrating generation, verification, and visual auditability.
- **Generative Component**: Local `Qwen2.5:7B` serving with numerical precision prompts and Citation Guard grounding.
- **User Interface**: React/Vite single-page application with interactive evidence cards, source bounding box highlights, and inline PDF.js document viewer.

### 6. Ontology Verification & Shadow Mode Ablation
- **Objective**: Evaluate formal constraint checking against generative hallucination.
- **Ablation Studies (A0–A3)**: Tested hard enforcement (abstaining or rejecting answers when formal claim verification failed).
- **Findings**: Hard enforcement caused an 8.3% false rejection rate due to natural language paraphrasing limitations in automated claim extraction.
- **Architectural Decision**: Integrated ontology verification in **Shadow Mode**—claim extraction and constraint verification execute asynchronously in the background, logging diagnostic metrics without interrupting user-facing answers.
