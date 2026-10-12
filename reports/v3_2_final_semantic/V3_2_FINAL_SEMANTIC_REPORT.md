# VietIrrDocBench V3.2 Final Semantic Freeze Report

## Scope and result

The patch reopened 545 accepted QA without rebuilding or expanding the corpus. It repaired 42 temporal QA, 3 Core topic QA, and normalized entity/metric OCR in 18 QA. No replacement QA was generated.

## Final dataset

- Accepted QA: 545 (378 Core, 167 Challenge)
- Rejected in this patch: 0
- Source-grounded negatives: 704 (373 minimal, 331 hard nonminimal)
- Invalid negatives removed: 62
- Dev: 93 QA, 25 Challenge, 25 retrieval-multi
- Candidate test: 109 QA; this is a series/family holdout-heavy evaluation split, not a universally representative benchmark test.
- Document/family leakage: 0

## Semantic gates

All required semantic red flags are zero. Temporal evidence dates come from metric/header or explicit evidence periods, not bulletin publication dates. Generic elevations are not accepted as water-level evidence. Raw OCR provenance is retained beside controlled normalized/canonical values.

`HUMAN_VALIDATED=false`. No baseline, training, RAG build, corpus expansion, or new-QA generation was run.

## Freeze decision

`DATASET_FROZEN=true` and `READY_FOR_BASELINE_EXPERIMENTS=true`.
