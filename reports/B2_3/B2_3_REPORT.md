# VietIrr-RAG Phase B2.3 — Rank Stability and Zero-shot Reranking

## 1. Modality evaluation correction

The evaluator now reads validated `modality` first and uses validated `qa_type` only as a fallback. It never infers modality from question keywords. Coverage is 93/93 exactly once: TEXT_ONLY=29, TABLE_ONLY=39, TEXT_TABLE=22, TABLE_TABLE=3. B2.2 subgroup metrics were recomputed from the existing rankings; no old retrieval experiment was rerun.

## 2. M0 versus M1 on identical pools

| Method | B | Coverage | All R@10 | All R@20 | MRR | nDCG@10 | ms/query |
|---|---:|---:|---:|---:|---:|---:|---:|
| M0 | 50 | 0.7527 | 0.4516 | 0.6237 | 0.2996 | 0.3257 | 31.92 |
| M0 | 100 | 0.7742 | 0.4516 | 0.6129 | 0.2988 | 0.3244 | 32.54 |
| M1 | 50 | 0.7527 | 0.4624 | 0.6237 | 0.2852 | 0.3195 | 23.93 |
| M1 | 100 | 0.7742 | 0.4624 | 0.6237 | 0.2855 | 0.3195 | 24.15 |
| M2 | 100 | 0.7742 | 0.5484 | 0.6452 | 0.3490 | 0.3842 | 752.41 |

M0 recomputes BM25/E5 ranks inside each pool. M1 uses exact full-corpus ranks; no missing candidate is assigned a synthetic rank. Candidate IDs and coverage are identical between M0 and M1 at each budget. From B50 to B100, M0 recovers 2 and regresses 3 QA; M1 recovers 0 and regresses 0.

## 3. Zero-shot cross-encoder

M2 uses `BAAI/bge-reranker-v2-m3` revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`, max_length=512, FP16, batch=16. It scored 9300 fixed query-candidate pairs; 98 (1.05%) exceeded max_length before truncation. Model loading took 4.74s and inference took 69.97s (752.41 ms/query). Scores are cached for evaluation-only reruns.

## 4. Candidate ceiling versus final ranking

Coverage@100 is 0.7742 for all three methods. All R@20 is M0=0.6129, M1=0.6237, M2=0.6452. Candidate misses affect 21 QA and cannot be repaired by reranking.

## 5. Recovery and regression

- M1 vs M0: recovered=3, regressed=2, absolute gain=+0.0108.
- M2 vs M0: recovered=9, regressed=6, absolute gain=+0.0323.
- Original 15 ranking failures remaining: M1=12, M2=6.

## 6. Statistical uncertainty

- M1 Δ All R@20 95% CI [-0.0323, +0.0538].
- M2 Δ All R@20 95% CI [-0.0538, +0.1075].
- M1 supported: false; M2 supported: false. No superiority claim is made when zero is inside the CI.

## 7. Remaining bottleneck

Neither pointwise ranking change has established a reliable complete-evidence gain. At B100, the diagnosis separates 21 candidate misses from 12 M2 ranking misses.

## 8. One Phase C recommendation

Study Complete Evidence Set Selection at fixed P0/S1/B100 while retaining a parallel candidate-miss track.
