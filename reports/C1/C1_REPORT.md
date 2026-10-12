# VietIrr-RAG Phase C1 — High-Recall Candidates and Complete-Evidence Selection

## 1. Baseline verification

Integrity passed on 93 DEV QA, including 25 retrieval-multi QA and 45 unique gold-evidence sets. Missing retrieval gold IDs and document/family leakage are both zero. Candidate Test was byte-hashed only and remained unchanged. E0 and E2 were evaluated from the verified B2.3 rankings; E2 reused cached cross-encoder scores.

## 2. Controlled results

| Experiment | Candidates | Selection | Candidate@100 | All R@20 | Multi All R@20 |
|---|---|---|---:|---:|---:|
| E0 | G0 | Global RRF | 0.7742 | 0.6237 | 0.6000 |
| E1 | G1 | Global RRF | 0.8172 | 0.5054 | 0.5200 |
| E2 | G0 | Cross-Encoder cached | 0.7742 | 0.6452 | 0.4400 |
| E3 | G0 | Set-Aware | 0.7742 | 0.6237 | 0.6000 |

## 3. Branch A — G1 versus G0

G1 uses the fixed 60/20/10/10 quota over P0 page candidates, P2 page candidates, flat E5, and flat BM25, with deterministic deduplication and backfill. Candidate-completeness transitions are recovered=6 and regressed=2. Among the 21 prior G0 misses, G1 rescued 6. Final All R@20 is reported independently above; candidate coverage alone is not treated as success.

## 4. Branch B — Set-Aware versus pointwise baselines

R3 is deterministic and training-free. It detects question-only requirements, then greedily balances fixed global-RRF relevance, unmet requirement coverage, provenance compatibility, question overlap, and redundancy. It falls back exactly to R0 when no reliable requirement is detected. E3 versus E0 recovered=3 and regressed=3 QA. On retrieval-multi, recovered=0 and regressed=0; on single-evidence, recovered=3 and regressed=3.

## 5. Statistical validity

For E3 versus E0 overall, the QA-level delta is +0.0000, 95% CI [-0.0538, +0.0538]. The gold-signature cluster-aware delta is +0.0000, 95% CI [-0.0795, +0.0808]. No superiority claim is made unless the corresponding interval excludes zero. Document/family results are reported cautiously because only 12 family groups are available.

## 6. Failures, complexity, and decision

Failures are separated into candidate missing, ranking missing, set-selection missing, and provenance conflict in `C1_FAILURE_TRANSITIONS.jsonl`. Table-only duplication is quantified in `C1_SET_SELECTION_ANALYSIS.json`. Mean R3 selector overhead is 70.212 ms/query; this is reported separately from the cached R0 and cross-encoder runtimes.

Decision: **C1_INCONCLUSIVE**. Do not combine branches; diagnose candidate misses and selector regressions first.

C1 valid: true. No C2 experiment, training, Candidate Test evaluation, or RAG application was run.
