# VietIrr-RAG Phase B2.2 — Candidate Coverage and Page Pruning

## 1. Metrics correction and comparability

B2.2 separates three events: raw page candidate ceiling before any region budget, complete coverage inside an explicitly bounded and deduplicated candidate pool, and final All-Evidence Recall after ranking. The B2.1 field called `candidate_coverage@B` was final All R@B, not an independently constructed candidate-pool metric. B2/B2.1 final recall values remain valid; only that historical coverage label is excluded from coverage comparisons.

All experiments use 93 DEV QA, multilingual-E5-large, the original BM25 tokenizer, and RRF(k=60). Candidate Test was byte-hashed only. The B2.2 S0 control was rerun because explicit candidate budgeting changes the scoring context relative to B2.1.

## 2. Controlled results

| Page rep | Strategy | B | Raw page ceiling | Budgeted coverage | Final All R@20 | Final All R@50 | Avg unique candidates | Candidate-stage ms/query |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| P0 | S0 | 50 | 0.6559 | 0.6452 | 0.6022 | 0.6452 | 50.0 | 31.93 |
| P0 | S0 | 100 | 0.6559 | 0.6559 | 0.5914 | 0.6452 | 99.9 | 32.51 |
| P0 | S1 | 50 | 0.7849 | 0.7527 | 0.6237 | 0.7527 | 50.0 | 31.92 |
| P0 | S1 | 100 | 0.7849 | 0.7742 | 0.6129 | 0.7527 | 100.0 | 32.54 |
| P0 | S2 | 50 | 0.6559 | 0.7312 | 0.5376 | 0.7312 | 50.0 | 36.73 |
| P0 | S2 | 100 | 0.6559 | 0.7849 | 0.5269 | 0.7527 | 100.0 | 37.36 |
| P2 | S0 | 50 | 0.6989 | 0.6882 | 0.6129 | 0.6882 | 50.0 | 31.80 |
| P2 | S0 | 100 | 0.6989 | 0.6989 | 0.6129 | 0.6882 | 99.9 | 32.42 |
| P2 | S1 | 50 | 0.7957 | 0.7527 | 0.6022 | 0.7527 | 50.0 | 31.90 |
| P2 | S1 | 100 | 0.7957 | 0.7849 | 0.6022 | 0.7634 | 100.0 | 32.52 |
| P2 | S2 | 50 | 0.6989 | 0.7527 | 0.5484 | 0.7527 | 50.0 | 36.60 |
| P2 | S2 | 100 | 0.6989 | 0.7849 | 0.5269 | 0.7204 | 100.0 | 37.21 |

S0 uses P=10, S1 uses P=20, and S2 uses P=10 plus a fixed 70% page / 30% flat-rescue quota. All candidate pools contain at most B unique evidence IDs and use the same final region RRF scorer. Latency uses cached page rankings and therefore measures query encoding, region scoring, candidate construction, and final ranking—not page-index lookup.

## 3. Candidate ceiling versus final retrieval

For P2/B100, budgeted coverage is 0.6989 (S0), 0.7849 (S1), and 0.7849 (S2). Final All R@20 is 0.6129, 0.6022, and 0.5269, respectively. Coverage and final retrieval are reported separately and are not treated as interchangeable.

## 4. Failure recovery and regression

- Among the 25 B2.1 P2 page-pruning failures, S1 recovers 6 and S2 recovers 3 at B100/Top-20.
- S1 recovers 6 DEV QA and regresses 7 versus S0.
- S2 recovers 3 DEV QA and regresses 11 versus S0.
- Under the selected fixed-budget condition (P0_S1/B100), remaining failures are {'PAGE_PRUNING': 14, 'REGION_RANKING': 15, 'PAGE_RETRIEVAL': 6, 'CANDIDATE_BUDGET_MISS': 1}.

## 5. Statistical uncertainty and latency

- P2 S1 vs S0 Δ All R@20=-0.0108, 95% CI [-0.0860, +0.0645]; Δ Coverage@100=+0.0860, 95% CI [+0.0215, +0.1505].
- P2 S2 vs S0 Δ All R@20=-0.0860, 95% CI [-0.1613, -0.0108]; Δ Coverage@100=+0.0860, 95% CI [+0.0323, +0.1505].
- Statistical conclusion for the best condition versus its S0 control: **INCONCLUSIVE**.

## 6. Main remaining bottleneck

The best fixed-B100 condition is **P0_S1**, with Coverage@100=0.7742 and All R@20=0.6129. Its largest remaining failure class is **REGION_RANKING** (15 QA). Better candidate coverage does not automatically imply proportional Top-20 recovery.

## 7. One evidence-based next step

Do not keep expanding page budgets. Isolate region ranking/evidence-set selection at fixed B100 because the paired evidence does not establish a reliable final-recall gain.
