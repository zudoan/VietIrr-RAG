# QA Generator V3 Capability Report

## Demonstrated architecture

`Coverage Cell → Evidence Search/Selection → Typed Fact Validation → Reasoning Plan → QA Draft → Validation State → Human Review Queue`

The generator contains no concrete question, answer, numeric value or evidence ID. Its input requests contain coverage, selectors, competency, operation and constraints. It currently supports deterministic `SINGLE_FACT_LOOKUP`, `MULTI_FACT_LOOKUP`, `QUANTITATIVE_COMPARISON` and `VERIFIABLE_COMPUTATION`.

## Generalization demo

Two drafts were generated from evidence never used by the original hardcoded 38-QA list: EV021/EV022 and EV042. The second request was substituted without modifying generator code.

- `GEN-DEMO-001`: `EV021,EV022`; input `e0e78888e3b2964d8e3d152adbf32636cc10b3febedb1219d16b4854b17a1d92`; output `8ef8c783f1bf83a209e948e835c1bb197719d63e553ec4da71490fbd47af01fe`.
- `GEN-DEMO-002`: `EV042`; input `8b6dc6fb0bd4e3d75aff30294c191db831c1f0f3ecda54329d5a9b3002329319`; output `28b155eea0a5e5969b425f0add386fbddc3a7b329df0fb0ffa101bf85905d69a`.

Generator tests: **24/24**, including 7 positive and 17 negative cases. Missing operands, unit/time mismatch, unverified cross-document relations, no source, conflicts, incomplete extrema domain, unsupported cells/competencies, and missing provenance fail closed.

## Limits

This demonstrates a bounded deterministic generator, not a universal QA author. It does not automatically establish semantic correctness, legal applicability, cross-document relations, causal reasoning, or human gold. LLM wording is not required or used.
