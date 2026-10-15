# VietIrr-RAG V4.4 Scientific Deep Audit

This directory contains a content-grounded audit of the canonical 93-PDF corpus, three linked evidence packs, the immutable 48-QA inventory, and an eight-question controlled expansion.

## Reproduce

```powershell
python research/vietirr_v4_4_deep_audit/build_deep_audit.py
python research/vietirr_v4_4_deep_audit/V4_4_DEEP_AUDIT_INDEPENDENT_AUDIT.py
```

Inputs are read from the V4.4 complete handoff and explicit V4.2--V4.4 research files. Original PDFs and raw QA are never modified. Candidate Test is neither required nor accessed.

Read `V4_4_DEEP_AUDIT_EXECUTIVE_REPORT.md`, then the corpus, pack, and QA reports. Machine support is not human gold verification.
