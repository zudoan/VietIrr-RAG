# Data Availability and Governance

## Overview

VietIrr-RAG evaluates retrieval-augmented generation over specialized civil engineering and water resources documentation in Vietnam. This document specifies the governance policies, dataset structure, distribution boundaries, and access mechanisms for project data.

---

## Dedicated Dataset Repository

To separate software engineering artifacts from large corpus data and adhere to academic data curation standards, the dataset is maintained in a dedicated public repository:

- **Repository**: [https://github.com/zudoan/vietirr-rag-dataset](https://github.com/zudoan/vietirr-rag-dataset)
- **Dataset Title**: VietIrrDocBench / VietIrr Corpus
- **Status**: Published / Maintained
- **Language**: Vietnamese (`vi`)
- **Domain**: Hydraulic Engineering, Reservoir Operation, Dam Safety, and Water Resources

---

## Corpus Specifications

### 1. Active Operational Corpus (`V4_R6_FROZEN`)
The primary benchmark corpus used by the active R6 pipeline comprises:
- **Total Documents**: 93 verified hydraulic technical reports and operational procedures
- **Total Document Pages**: 2,578 pages
- **Total Evidence Units**: 27,144 units (27,053 text regions and 91 structured table regions)
- **Manifest File**: `data/v4_corpus/metadata/v4_corpus_manifest.jsonl`

### 2. Historical Baseline Corpus (`V3.2_FINAL_SEMANTIC`)
- **Total Documents**: 89 documents
- **Total Document Pages**: 2,479 pages
- **Total Evidence Units**: 27,045 units
- **Usage**: Retained strictly as an immutable baseline for historical cross-evaluation (Stages B2, C1, and R1).

---

## Question Answering Benchmarks

| Benchmark Split | Path | Count | Focus |
| :--- | :--- | :---: | :--- |
| **DEV-93** | `data/benchmark/dev.jsonl` | 93 questions | Multi-hop reasoning across complex text and numerical tables; used for frozen retrieval evaluations. |
| **ALL-QA-545** | `data/benchmark/all_qa.jsonl` | 545 questions | Comprehensive curated question set covering core, challenge, and pilot hydraulic tasks. |

All QA records include canonical document citations, exact page indices, and targeted evidence bounding boxes to guarantee end-to-end traceability.

---

## Redistribution and Privacy Safeguards

The source documents comprise technical reports, reservoir operating procedures, and government decisions. In compliance with intellectual property standards and organizational data protection guidelines:

1. **Raw Document Binaries**: Direct redistribution of copyrighted raw PDF documents is restricted unless explicit redistribution clearance has been recorded in the corpus registry (`public_status = "PUBLIC"`).
2. **Derived Structured Representations**: Layout-parsed bounding boxes, anonymous text tokens, table matrices, and metadata manifests are available for scientific reproducibility within the dataset repository.
3. **Repository Protection**: The source repository employs strict `.gitignore` rules to prevent inadvertent leakage of unverified binary PDFs, raw OCR caches, internal credentials, or personal telemetry.
