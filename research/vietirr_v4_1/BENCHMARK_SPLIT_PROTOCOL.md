# VietIrr-RAG V4 — Benchmark Split Protocol (design only)

## Release condition

No official V4 Test is created in V4.1. Candidate Test V3.2 remains sealed and cannot be reused. Splitting starts only after source, evidence tuple, relation and QA review is complete and every released item is `HUMAN_ACCEPTED`.

## Dependency graph and split unit

Construct a graph whose nodes are documents, document families, systems/facilities, legal versions and QA. Edges include `same_family`, `part_of_system`, `amends/replaces`, `same_event_or_period`, `derived_table`, and every required evidence relation. The atomic split unit is a connected component of this graph, not an individual QA or page. Components with a shared facility, version chain, replicated PDF or evidence dependency cannot cross splits.

## Stratification target

Report, but do not force-fill, the matrix:

`Domain × Use case × Competency × Evidence pattern × Geography × Difficulty`.

Balance constraints are soft and documented. Do not manufacture multi-evidence or assign a fixed count per PDF. Preserve single-fact items with real utility and true multi-evidence items. Distinguish same-page, cross-page and cross-document; multi-fact and multi-hop; observed, forecast, plan, rule and draft-rule; and positive versus abstention.

## Proposed sequence

1. Freeze the human-accepted V4 item set and dependency graph.
2. Reserve 15–20% of dependency components for Test using a preregistered seed; never inspect answer distribution to choose components.
3. Reserve 10–15% for Dev from the remaining components; Train receives the rest.
4. Run zero-overlap checks on document ID, checksum, family, system/facility, event/time-series family, legal-version chain and near-duplicate question clusters.
5. Audit coverage drift. Report cells that disappear from a split instead of moving linked QA across boundaries.
6. Seal Test with size/mtime and access policy before any method development; compute an encrypted or independently held checksum only if governance approves.

## Negative and abstention items

Negatives must be source-grounded and tied to a missing or contradicted evidence condition. Abstention QA must name the dependency that is absent. Do not create a negative by swapping arbitrary entities/numbers unless the mutation is clearly labelled as validator test data and excluded from the benchmark.

## Leakage gates

- No Candidate Test V3.2 content, hashes, templates or IDs.
- No V3.2 QA is renamed as V4.
- No DEV-exposed retrieval output selects V4 Test questions.
- No gold evidence or answers are used at inference.
- Paraphrase clusters stay in one split.
- Any unresolved relation blocks all dependent QA from Test.

## V4.1 status

The protocol is ready for review, but splitting is blocked: 0/10 pilot QA are human accepted and 0 cross-document relations are verified for gold.
