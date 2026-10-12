# Phase B2 Failure Diagnosis

At K=20, Page→Region has 38 incomplete-evidence failures among 93 DEV QA.

- Page localization/pruning: 32
- Page pruning miss (gold page within Top-100 but outside Top-10): 26
- Page retrieval miss beyond Top-100: 6
- Candidate mapping: 0
- Region ranking after complete candidate coverage: 6
- Cross-document failures: 2
- Table-involving failures: 19

Oracle gold-page diagnostics recover All R@10=1.0000 and All R@20=1.0000. The oracle is diagnostic only and is not a deployable baseline.

Main bottleneck: **PAGE_LOCALIZATION**.

Recommended Phase C direction: Prioritize page localization and cross-document page candidate recall before region reranking.
