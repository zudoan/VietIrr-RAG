# VietIrr-RAG Phase C1.1 — Evidence Requirements, Provenance and Ranking Diagnosis

## 1. Baseline verification

Artifact recomputation passed for 93 DEV QA, 25 retrieval-multi QA, and 45 unique gold-evidence sets. G0 and G1 contain exactly 100 candidates per query. Phase A metadata maps every G0 candidate to a real table or text region and document. Candidate Test was byte-hashed only.

## 2. Thirteen G1 ranking regressions

All 13 E0-success/E1-failure cases were analyzed. Gold remains present in G1 and keeps its exact global-RRF fusion score; the rank changes because new G1 candidates with higher scores enter Top-20. Category counts are {'RANK_DISPLACEMENT': 13, 'COMPETING_EVIDENCE': 13, 'PROVENANCE_CONFUSION': 1}. Per-query BM25/E5 ranks, fusion scores, source provenance, competing candidates, and structured provenance evidence are stored in `RANK_REGRESSION_DIAGNOSIS.jsonl`. This supports candidate competition/rank displacement as the general cause, not a changed fusion formula.

## 3. Requirement correction

Temporal comparison falls from 91 to 6 and forecast from 65 to 16. First-evidence saturation falls from 78 to 61. V2 requires explicit question intent, exposes `UNCERTAIN`, and falls back to E0 when intent or metadata is insufficient. The 30-QA audit sample is a pending manual-review queue and is not labeled human validated.

## 4. Structured evidence and provenance coverage

The representation reads real table semantic tuples, text `region_type/index_text`, and document reporting periods. Unknown fields remain `UNKNOWN`. Entity is known in 661/9300 query-candidate representations, evidence time in 661/9300, and document reporting time in 8081/9300. Report time is never substituted for evidence time; cross-document selection remains allowed.

## 5. E4 controlled comparison

| Method | All R@20 | Multi All R@20 | MRR | ms/query |
|---|---:|---:|---:|---:|
| E0 Global RRF | 0.6237 | 0.6000 | 0.2855 | 24.15 |
| E2 Cross-Encoder | 0.6452 | 0.4400 | 0.3490 | 752.41 |
| E3 Old Set-Aware | 0.6237 | 0.6000 | 0.3513 | 94.36 |
| E4 Set-Aware V2 | 0.6559 | 0.6000 | 0.3344 | 79.22 |

E4 versus E0 recovered 3 and regressed 0 QA. On retrieval-multi it recovered 0 and regressed 0.

## 6. Statistical validity and duplicated gold sets

E4 versus E0 overall delta is +0.0323; paired-QA 95% CI [+0.0000, +0.0753], gold-set cluster-aware CI [+0.0000, +0.1012]. The QA-weighted versus signature-balanced deltas are +0.0323 and +0.0111. No superiority claim is made when zero remains in the interval.

## 7. Decision

Decision: **EVIDENCE_SET_SELECTION_NOT_PROMISING**. Do not proceed to C2; prioritize candidate/ranking diagnosis over a more complex selector.

C1.1 valid: true. Ready for C2: false. No C2 experiment, training, model inference, Candidate Test evaluation, or Agentic RAG was run.
