# VietIrr-RAG V4.4

V4.4 preserves the user-kept 38-QA pilot, audits all 93 canonical PDFs, builds three provenance-bearing evidence packs, and creates a controlled 10-QA expansion pilot. It does not change frozen parents, retrieval baselines or Candidate Test.

Run:

```powershell
python research/vietirr_v4_4/build_v4_4.py
python research/vietirr_v4_4/tests/run_all.py
python research/vietirr_v4_4/build_review_bundle.py
python research/vietirr_v4_4/V4_4_INDEPENDENT_AUDIT.py
```

Start review with `V4_4_EXECUTIVE_REPORT.md`, `V4_4_SCIENTIFIC_COMPARISON.md`, `corpus/CORPUS_COVERAGE_REPORT.md`, `packs/DOCUMENT_PACK_QUALITY_REPORT.md` and `qa/V4_4_QA_REVIEW_QUEUE.csv`.
