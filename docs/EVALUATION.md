# Evaluation Protocols and Benchmarks

## 1. Evaluation Datasets

The primary benchmark for VietIrr-RAG is **VietIrrDocBench**, designed specifically for complex multi-evidence retrieval and question answering:

| Dataset Split | File Location | Sample Size | Modality Focus | Description |
| :--- | :--- | :---: | :--- | :--- |
| **DEV-93** | `data/benchmark/dev.jsonl` | 93 | Cross-page / Cross-document | Frozen benchmark testing multi-hop reasoning over dense Vietnamese hydraulic texts and tables |
| **ALL-QA-545** | `data/benchmark/all_qa.jsonl` | 545 | Comprehensive pool | Complete curated question-answering pool covering core, challenge, and pilot sets |
| **E2E 24 Traces** | `reports/EXPERIMENTS/CAR_E2E_R6_24_TRACES.jsonl` | 24 | R6 Retrieval + Generation | Multi-stage diagnostic traces capturing candidate retrieval and generation behavior |

## 2. Evaluation Metrics Definition

To maintain scientific precision, metrics are defined strictly as retrieval and localization indicators:

- **Candidate Hit@100**: Proportion of evaluation questions where at least one supporting document appears within the top 100 candidate pool.
- **Page Hit@5**: Proportion of questions where the ground-truth page is ranked within the top 5 localized pages.
- **Evidence Page Hit@5**: Proportion of questions where the specific evidence-bearing page containing the required answer facts is within the top 5 localized pages.
- **Mean Reciprocal Rank (MRR@5)**: The reciprocal rank of the first relevant page among the top 5 localized pages.
- **Normalized Discounted Cumulative Gain (nDCG@5)**: Evaluates page ranking quality with logarithmic position discounting.

> **Important Distinction:** Hit@K measures the availability of supporting source evidence within the top-ranked context. It is **not** an answer accuracy metric. End-to-end answer correctness has not yet been established by a comprehensive independent evaluation.

## 3. Verified Experimental Results (DEV-93)

The following metrics are derived directly from the immutable evaluation artifact `reports/EXPERIMENTS/R6_RETRIEVAL_DEV93_METRICS.json`:

| Metric Category | Baseline R5 | Frozen R6 | Delta (R6 vs R5) |
| :--- | :---: | :---: | :---: |
| **Candidate Hit@100** | 76.34% (71/93) | **91.40% (85/93)** | +15.06% |
| **Page Hit@5** | 63.44% (59/93) | **67.74% (63/93)** | +4.30% |
| **Evidence Page Hit@5** | 58.06% (54/93) | **61.29% (57/93)** | +3.23% |
| **MRR@5** | 0.4579 | **0.4511** | -0.0068 |
| **nDCG@5** | 0.4894 | **0.5077** | +0.0183 |
| **Table Region Recovery** | 0.00% (0/93) | **17.20% (16/93)** | +17.20% |
| **Median Latency (p50)** | 4,505 ms | **4,401 ms** | -104 ms |
| **95th Percentile Latency (p95)**| 5,963 ms | **5,564 ms** | -399 ms |

### Paired Comparison on Page Hit@5:
- **R6 Wins**: 10 questions
- **R6 Losses**: 6 questions
- **Ties**: 77 questions

## 4. Reproducing Evaluation Locally

Evaluation benchmarks can be executed using the verified evaluation scripts:

```bash
# Set PYTHONPATH to project root
export PYTHONPATH="."  # On Linux / macOS
$env:PYTHONPATH="."    # On Windows PowerShell

# Run R6 retrieval benchmark against DEV-93
python scripts/run_r6_retrieval_benchmark.py
```
