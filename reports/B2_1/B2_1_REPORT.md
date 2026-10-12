# VietIrr-RAG B2.1 — Page Representation and Pruning

## 1. B2 verification

**PASS.** Metrics were recomputed from raw DEV rankings and retrieval gold, not copied from the B2 report. All source/parent mappings, ranking uniqueness/order, index leakage checks, and byte-hash checks passed. Candidate Test was byte-hashed only and never parsed.

## 2. P0/P1/P2 comparison (93 DEV QA)

All methods use the same page BM25, E5 model/query prefix, RRF(k=60), Region Hybrid, and final ranking budgets. Only the dense page representation differs.

| Representation | Page P | Complete Page Recall@P | All R@20 | All R@50 | Candidate Coverage@100 | Avg candidates | Latency ms/query |
|---|---:|---:|---:|---:|---:|---:|---:|
| P0 | 10 | 0.6559 | 0.5914 | 0.6452 | 0.6559 | 211.0 | 24.15 |
| P0 | 20 | 0.7849 | 0.6022 | 0.7527 | 0.7742 | 411.2 | 24.18 |
| P0 | 50 | 0.8925 | 0.5376 | 0.7312 | 0.8172 | 895.6 | 24.26 |
| P1 | 10 | 0.6237 | 0.5484 | 0.6129 | 0.6237 | 213.3 | 24.54 |
| P1 | 20 | 0.7204 | 0.5699 | 0.6989 | 0.7097 | 418.1 | 24.58 |
| P1 | 50 | 0.8602 | 0.5376 | 0.6774 | 0.7849 | 911.8 | 24.67 |
| P2 | 10 | 0.6989 | 0.6129 | 0.6882 | 0.6989 | 211.3 | 23.57 |
| P2 | 20 | 0.7957 | 0.6022 | 0.7527 | 0.7849 | 420.8 | 23.61 |
| P2 | 50 | 0.9032 | 0.5161 | 0.7312 | 0.8387 | 920.7 | 23.70 |

Fixed-P=10 selection policy chooses **P2**. P1 used 6,004 tokenizer-derived windows; maximum encoded window length was 384 tokens and no window exceeded 512. P2 pooled 27,045 source text/table units, so tables participate without QA/gold annotations.

## 3. Flat E5 ∪ Flat BM25 diagnostic

| Unique budget | Any Recall | Complete Coverage | Additional QA vs P0/P10 |
|---:|---:|---:|---:|
| 50 | 0.7527 | 0.6989 | 12 |
| 100 | 0.8280 | 0.7957 | 18 |
| 200 | 0.8602 | 0.8387 | 21 |

This is a deduplicated round-robin diagnostic, not a proposed method.

## 4. Failure transition at fixed P=10

Old page-related failures: 32; recovered by P2: 4.

- PAGE_PRUNING → PAGE_PRUNING: 20
- PAGE_PRUNING → PAGE_RETRIEVAL: 1
- PAGE_PRUNING → REGION_RANKING: 1
- PAGE_PRUNING → SUCCESS: 4
- PAGE_RETRIEVAL → PAGE_PRUNING: 4
- PAGE_RETRIEVAL → PAGE_RETRIEVAL: 2
- REGION_RANKING → REGION_RANKING: 5
- REGION_RANKING → SUCCESS: 1
- SUCCESS → PAGE_PRUNING: 1
- SUCCESS → REGION_RANKING: 2

Of the old page-related failures, 27 involved at least one missed gold page longer than 512 tokens. This is an association only; the causal conclusion is **INCONCLUSIVE**. Remaining after P2/P10: {'PAGE_PRUNING': 25, 'PAGE_RETRIEVAL': 3, 'REGION_RANKING': 8}; table-involving failures: 17/36.

## 5. Cost and confidence intervals

- P1 indexing: 145.34s (cache hit=True); embedding bytes=24,592,512.
- P2/P10 All R@20 delta: +0.0215, paired bootstrap 95% CI [-0.0323, +0.0860], regressions=3.
- P2 Complete Page Recall@10 delta: +0.0430, paired bootstrap 95% CI [+0.0000, +0.0968].
- Statistical conclusion: **INCONCLUSIVE**. No superiority claim is made when a CI includes zero.
- A cached rerun reproduced all 13 raw ranking files byte-for-byte.

## 6. Scientific conclusion

At the controlled P=10 budget, page representation changes All R@20 from 0.5914 to 0.6129; Complete Page Recall@10 changes from 0.6559 to 0.6989. The main remaining failure stage is **PAGE_PRUNING** (25 QA). Truncation causality remains inconclusive because this paired observational diagnostic does not isolate content position within missed pages.

## 7. One next priority

Prioritize **page pruning** using the frozen DEV protocol and fixed candidate budgets; do not add reranking/LLM components until this stage is isolated.
