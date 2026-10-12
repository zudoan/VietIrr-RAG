# VietIrr-RAG R1 — Contextualized Parent–Child Representation

## 1. Source and context coverage

The audit covers 27,045 immutable evidence IDs (26,954 text and 91 table). Document title and page context are taken from Phase A source records. Section and local-parent context are used only when verified; missing fields are omitted and raw content remains unchanged. No QA, gold, or answer content enters representation construction.

## 2. Representation and embedding controls

R1 enriches 27,045 units and falls back to raw for 0. R2 changes serialization for 91 table units and leaves every text unit identical to R1. All methods use E5 revision `3d7cfbdacd47fdda877c5cd8a79fbcc4f2a574f3`, fixed 384-token windows with 128-token overlap, max pooling to the original evidence ID, and no window over 512 tokens. Pre-window truncation rates are R0=1.04%, R1=1.13%, R2=1.26%; post-window truncation is 0%.

## 3. Fixed pool and full retrieval

| Stage | Representation | Coverage@100 | All R@20 | Multi All R@20 |
|---|---|---:|---:|---:|
| Fixed | R0 | 0.7742 | 0.6237 | 0.6000 |
| Fixed | R1 | 0.7742 | 0.6667 | 0.6400 |
| Fixed | R2 | 0.7742 | 0.7097 | 0.6400 |
| Full | R0 | 0.7742 | 0.6237 | 0.6000 |
| Full | R1 | 0.7849 | 0.6452 | 0.6400 |
| Full | R2 | 0.7849 | 0.6559 | 0.6400 |

R0 comparability: {"FIXED_POOL": {"expected_all_r@20": 0.6236559139784946, "actual_all_r@20": 0.6236559139784946, "expected_multi_all_r@20": 0.6, "actual_multi_all_r@20": 0.6, "within_tolerance": true}, "FULL_RETRIEVAL": {"expected_all_r@20": 0.6236559139784946, "actual_all_r@20": 0.6236559139784946, "expected_multi_all_r@20": 0.6, "actual_multi_all_r@20": 0.6, "within_tolerance": true}}.

## 4. Failure transitions and subgroups

Transition counts are stored per QA in `FAILURE_TRANSITIONS.jsonl`, including the prior eight multi candidate misses, candidate recovery/loss, and gold-rank movement. Text/table and locality subgroup N plus unique gold-set counts are in `SUBGROUPS.json`; no page-pruning resolution is claimed because P0 Top-20 pages are fixed.

## 5. Statistical uncertainty and runtime

Paired QA and unique-gold-set cluster bootstraps use 1,000 resamples with seed 42. Full-retrieval cluster support is R1=False and R2=False; superiority is not claimed when the cluster interval includes zero. Indexing and per-query retrieval costs are reported in `RESULTS.csv` and the cache manifest.

## 6. Conclusion

Main finding: **NO_RELIABLE_CONTEXTUALIZATION_GAIN**. The main bottleneck remains fixed page localization/pruning when contextualization does not produce cluster-supported full-retrieval gains. R1 validity is True; READY_FOR_R2 is False.

## 7. One next step

Stop contextual enrichment and keep the raw representation; do not proceed without new evidence.
