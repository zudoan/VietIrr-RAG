# MASH-ER method specification

## Scope

MASH-ER is a deterministic, zero-shot evidence retriever for long Vietnamese irrigation PDFs. It preserves all Phase-A evidence IDs and uses no question labels, answers, gold evidence, fine-tuning, LLM generation, or synthetic evidence during indexing and retrieval.

## Representations

- `TEXT_RAW`: original evidence `index_text`.
- `TEXT_CONTEXT`: raw text with source-verified document title, section, page number, and local heading from R1. Missing metadata is omitted.
- `TABLE_RAW`: original table evidence `index_text`.
- `TABLE_STRUCT`: source-verified caption, headers, row labels, rows/values, and units. It is enabled only when both semantic and structural quality are `GOOD`; otherwise the evidence uses only `TABLE_RAW`.

Each view maps to one immutable source evidence ID. All views use `intfloat/multilingual-e5-large` revision `3d7cfbdacd47fdda877c5cd8a79fbcc4f2a574f3`, 384-token content windows, 128-token overlap, normalized embeddings, and max window pooling back to the source ID.

## Scoring

Ranks are global over the full evidence universe. With `k=60`, raw scoring is:

`S_raw = 1/(60+r_bm25) + 1/(60+r_raw)`.

Multi-view scoring fixes total dense weight at one:

`S_multi = 1/(60+r_bm25) + 0.5/(60+r_raw) + 0.5/(60+r_alt)`.

If the alternate table view is invalid, its contribution is zero and raw dense weight becomes one; the fallback is never counted twice. The soft page prior is:

`S_page = 0.25/(60+r_page)` for pages present in fixed P0 Top-100, otherwise zero.

`S_final = S_view + S_page`. An unranked page is not filtered. A0/A2 restrict selection to P0 Top-20 pages; A1/A3 select globally. Every method returns exactly 100 unique candidates and evaluates the first 20. Ties are broken lexicographically by evidence ID.

## Pseudocode

```text
index each source evidence as RAW
if TEXT: add verified CONTEXT view
if TABLE and structure is verified: add STRUCT view else keep RAW only
for each query:
    compute global BM25, RAW-dense, and alternate-dense ranks
    fuse ranks with fixed view weights
    optionally add the P0 page-rank prior without filtering
    optionally restrict to P0 Top-20 pages for hard-hierarchy ablations
    stable-sort by (-score, evidence_id), keep B=100, evaluate K=20
```

## Complexity

For `N` evidence units, `W` windows, `D` embedding dimensions and `P` ranked pages, dense scoring is `O(WD)`, rank sorting is `O(N log N)`, page-prior lookup is `O(N+P)`, and storage is `O(WD)`. Multi-view storage adds contextual text windows plus only verified table-structure windows.

## Prior-art gap and novelty limitations

- [Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval): Chunk-specific context is prepended before embedding and BM25 indexing. Difference: MASH-ER uses only verified source metadata, keeps raw and contextual dense views separate, and does not generate context with an LLM.
- [TreeRAG](https://aclanthology.org/2025.findings-acl.20/): Tree-structured chunk storage with bidirectional hierarchical traversal. Difference: MASH-ER does not construct a tree or traverse it; an existing page rank is a non-exclusive additive prior over flat evidence retrieval.
- [LongRefiner](https://arxiv.org/abs/2505.10413): Learned hierarchical document refinement with dual-level query analysis and adaptive refinement. Difference: MASH-ER is zero-shot retrieval-only and performs no learned refinement or generation.
- [TableRAG](https://arxiv.org/abs/2506.10380): Iterative heterogeneous-document reasoning combining text retrieval and SQL execution. Difference: MASH-ER only indexes verified table serialization as an alternate retrieval view; it performs no SQL or iterative reasoning.
- [OTTeR mixed-modality retrieval](https://arxiv.org/abs/2210.05197): Learned modality-enhanced representations and synthetic pre-training for joint table-text retrieval. Difference: MASH-ER uses one frozen E5 encoder, no training or synthetic data, and preserves one source evidence ID across views.
- [Hybrid Hierarchical Retrieval](https://aclanthology.org/2023.findings-acl.679/): Two-stage document-then-passage sparse/dense hierarchical retrieval. Difference: MASH-ER explicitly avoids mandatory first-stage pruning by adding page relevance as a soft prior.

Conclusion: **NOVELTY_UNVERIFIED**. The components have clear prior art. The exact combination may be useful experimentally, but novelty is not established by this limited search. The working name must not be presented as a novel contribution without a systematic literature review and independent evaluation.
