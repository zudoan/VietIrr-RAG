# VietIrr-RAG Phase B2 — Retrieval Baselines

## DEV results

| Method | Any R@10 | All R@10 | All R@20 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|
| Bm25 | 0.2688 | 0.1720 | 0.2796 | 0.0950 | 0.1128 |
| E5 | 0.5161 | 0.3978 | 0.5484 | 0.2736 | 0.2937 |
| Hybrid | 0.4839 | 0.3548 | 0.4946 | 0.2627 | 0.2767 |
| Page Region | 0.6452 | 0.4839 | 0.5914 | 0.2997 | 0.3412 |

All 93 DEV QA are evaluated against `retrieval_evidence_ids`. Candidate Test remains sealed. Index text comes only from frozen source regions/tables and never from QA, answers, or gold annotations.

## Research questions

1. **Method differences.** BM25 is lexical Unicode retrieval; E5 is fixed multilingual dense inference; Hybrid combines complete rankings with RRF(k=60); Page→Region first retrieves pages using source page text, hard-prunes to Top-10 pages, then applies the same region Hybrid.
2. **Best All-Evidence Recall.** `page_region` has the highest DEV All R@20 (0.5914).
3. **Page→Region advantage.** Its All R@20 is 0.5914, versus Flat Hybrid 0.4946; no Finance result is reused.
4. **Table retrieval.** For the best method, TABLE_ONLY has n=39, All R@20=0.8718. Small subgroups are descriptive, not conclusive.
5. **Multi/cross-document.** RETRIEVAL_MULTI All R@20=0.4400; CROSS_DOCUMENT All R@20=0.3333. Page→Region cross-document failures at K=20: 2.
6. **Main bottleneck.** `PAGE_LOCALIZATION`, based on {'PAGE_LOCALIZATION': 32, 'CANDIDATE_MAPPING': 0, 'REGION_RANKING': 6} at K=20.
7. **Phase C priority.** Prioritize page localization and cross-document page candidate recall before region reranking.

## Candidate ceiling

Complete-coverage values at budgets 20/50/100/200 are recorded in `B2_CANDIDATE_CEILING.json`. The BM25+E5 union is a bounded, deduplicated diagnostic baseline, not a proposed method.

## Reproducibility boundaries

- E5 model: `intfloat/multilingual-e5-large` revision `3d7cfbdacd47fdda877c5cd8a79fbcc4f2a574f3`, query/passages prefixes enabled, max length 512, L2 normalization.
- Region truncation: 280/27045 (1.04%).
- Page truncation: 1652/2479 (66.64%).
- GPU and CPU timings are stored separately in the experiment manifest.
- `HUMAN_VALIDATED=false`.
