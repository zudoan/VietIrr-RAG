# MASH-ER experiment report

## 1. Baseline and controls

The frozen inputs contain 27,045 evidence units, 93 Dev QA, 25 retrieval-multi QA, 45 unique gold sets, and 8 unique multi gold sets. Candidate Test was byte-hashed only and remained unchanged. Legacy E0 and R1-R0 rankings were recomputed, while A0 is explicitly treated as the matched baseline because it shares MASH-ER windowing and global-rank conventions.

## 2. Main ablation

| Method | Coverage@100 | All R@20 | Multi All R@20 |
|---|---:|---:|---:|
| A0 | 0.7742 | 0.6237 | 0.6000 |
| A1 | 0.8172 | 0.5376 | 0.6000 |
| A2 | 0.7849 | 0.5054 | 0.5600 |
| A3 | 0.8602 | 0.4731 | 0.5600 |

Candidate coverage and final recall are reported separately. A1 isolates soft localization, A2 isolates modality-aware views, and A3 combines both. Transition counts versus A0 are `{"A1": {"candidate_recovered": 9, "candidate_lost": 5, "all_r20_recovered": 2, "all_r20_regressed": 10, "page_pruning_avoidance": 9, "rank_displacement": 10}, "A2": {"candidate_recovered": 1, "candidate_lost": 0, "all_r20_recovered": 5, "all_r20_regressed": 16, "page_pruning_avoidance": 0, "rank_displacement": 16}, "A3": {"candidate_recovered": 9, "candidate_lost": 1, "all_r20_recovered": 4, "all_r20_regressed": 18, "page_pruning_avoidance": 9, "rank_displacement": 18}}`.

## 3. Subgroups

| Group | N | Unique gold sets | A0 All R@20 | A3 All R@20 |
|---|---:|---:|---:|---:|
| TEXT_ONLY | 29 | 29 | 0.3448 | 0.4138 |
| TABLE_ONLY | 39 | 8 | 0.8462 | 0.4615 |
| TEXT_TABLE | 22 | 7 | 0.5909 | 0.5000 |
| TABLE_TABLE | 3 | 1 | 0.6667 | 1.0000 |
| CROSS_PAGE_SAME_DOCUMENT | 22 | 7 | 0.5909 | 0.5000 |
| CROSS_DOCUMENT | 3 | 1 | 0.6667 | 1.0000 |

Complete page recall is diagnostic only and is stored in `SUBGROUPS.json`. Per-QA candidate recovery, gold-rank movement, view/page contributions, pruning avoidance, distractor displacement, and the requested historical failure subsets are stored in `FAILURE_ANALYSIS.jsonl`.

## 4. Statistical validity

A3-A0 QA bootstrap All R@20: delta=-0.1505, 95% CI [-0.2473, -0.0538]. Gold-set cluster bootstrap: [-0.3463, 0.0327]. Multi-evidence has only 8 unique gold sets and is marked inconclusive. No generalization or superiority claim is made from Dev alone.

## 5. Efficiency

Mean latency in ms/query is `{"A0": 18.162310753870116, "A1": 21.099775269601274, "A2": 26.657844087020084, "A3": 29.344982798530474}`. Peak VRAM is 2194.4169921875 MB on `cuda`. Embedding storage and cache-build timings are in `EFFICIENCY.json`; reused R1 caches are distinguished from newly built TABLE_STRUCT embeddings.

## 6. Mechanism and failures

Supported mechanism: **SOFT_LOCALIZATION_RAISES_CANDIDATE_COVERAGE_ONLY**. Remaining bottleneck: **RANK_DISPLACEMENT_AFTER_CANDIDATE_RECOVERY**. Soft page scores never exclude evidence outside P0, while hard A0/A2 intentionally reproduce the P=20 pruning condition. Full component ranks and scores are retained for every selected candidate.

## 7. Prior art and decision

The limited source check covers Contextual Retrieval, TreeRAG, LongRefiner, TableRAG, OTTeR, and hierarchical document-passage retrieval. These establish substantial prior art for every component; the exact combination is not assumed novel. Novelty status: **NOVELTY_UNVERIFIED**.

`EXPERIMENT_VALID=True`, `METHOD_PROMISING=False`, and `PAPER_READY=False`. Candidate Test remains sealed; independent benchmark validation and test evaluation are still required.
