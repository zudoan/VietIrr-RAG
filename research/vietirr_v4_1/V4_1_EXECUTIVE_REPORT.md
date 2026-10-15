# VietIrr-RAG V4.1 — Executive Report

## Executive decision

V4.1 **passes the bounded technical reconstruction gate with release blockers**. The isolated corpus expansion, first-principles QA contract, three-layer validator, adversarial suite and ground-up pilot are reproducible. The project is **not ready for a large official benchmark or method evaluation** because 0/10 pilot QA and 0 cross-document relations are human-verified for gold.

## 1. Frozen-state integrity

- The 89 accepted legacy documents remain referenced in place; no legacy source, V3.2 TRAIN/DEV artifact or frozen TCB-RR file was changed.
- All TCB-RR P2.3 code hashes match freeze `TCB_RR_P2_3_20261014`.
- Candidate Test remained `SEALED_NOT_OPENED_NOT_HASHED`; only size and modification time were recorded and independently rechecked.
- The V4.1 generation pipeline never reads V3.2 QA.

## 2. Corpus expansion

Twenty official-source candidates were screened: 4 ACCEPT, 5 REJECT, 10 REVIEW and 1 BLOCKED. ACCEPT was limited to downloaded PDFs with attributable publisher, PDF signature, unique checksum, extractable content, version/status record and a named gap. A duplicate attachment was rejected by identical SHA-256; an inaccessible standards draft remained BLOCKED.

The corpus manifest contains 93 records: 89 legacy references plus four new PDFs. New material improves, but does not close, these knowledge areas:

- current irrigation-system operation and facility inventory for Bắc Nam Hà;
- historical irrigation demand, drought scenario and release schedule for the same system;
- facility/monitoring structure for Cái Lớn–Cái Bé, explicitly restricted to a draft procedure;
- national 2025 inspection/preparedness/maintenance duties for irrigation and dike safety.

The two linked packs are real but both remain `REVIEW_REQUIRED`. Zero relation edges are eligible for gold. Major open gaps are actual water delivery/outcomes, current facility-specific safety records, applicable water-quality standard relations, comparable reviewed time series and item-level evidence review.

## 3. QA reconstruction

QA V4.1 was generated from use cases and evidence contracts, not from random chunks or V3.2 questions. The rulebook specifies ten competencies, including valid single-fact lookup, rule/version interpretation, quantitative and temporal comparison, cross-source synthesis, reproducible computation and insufficient-evidence detection.

The pilot contains 10 genuinely new `origin_type=GROUND_UP` records across D01–D06:

- 4 easy, 5 medium and 1 hard;
- 7 same-page, 2 cross-page/cross-source within a document, and 1 cross-document;
- 2 verifiable computations and 2 explicit abstention/version-safety cases;
- 0 auto-rejected, 10 pending human review, 0 human accepted.

Coverage remains intentionally incomplete. UC02, UC03, UC06, UC10 and UC12 have no positive pilot QA because the necessary reviewed clause, aligned rule/observation, comparable series, standard relation or facility inspection is missing.

## 4. Validator evidence

Layer 1 checks structure, IDs, corpus paths, locators, duplicate identifiers and Candidate leakage. Layer 2 verifies page hashes and contextual anchors; typed entity/metric/value/unit/time/source-role tuples; evidence-component coverage/minimality; operation traces; draft validity; domain/source compatibility and document-system joins. Layer 3 requires named human/domain decisions for realism, sufficiency and semantic correctness.

Pilot result: 10/10 pass Layer 1; 9/10 pass Layer 2; one is correctly `REVIEW` because its cross-document relation is not verified; 10/10 stop at Layer 3. There is no automatic `SEMANTIC_PASS`.

The adversarial suite catches 16/16 required error families with non-default evidence: five synthetic counterexamples and eleven mutations of real pilot QA. It detects shallow prompts, nonexistent numbers, wrong domain/entity/time/unit/validity, fake comparison/multi-evidence, self-declared necessity, arithmetic error, mixed systems, locator-correct/fact-wrong, near duplicates, incomplete rule gold and out-of-corpus evidence.

## 5. Independent audit and readiness

The independent audit runs 34 checks: 34 pass after bundle construction, 0 fail, 0 warn. Technical integrity is PASS; release conclusion remains NOT BENCHMARK READY.

| Readiness flag | Value | Meaning |
|---|---:|---|
| `CORPUS_EXPANSION_READY` | true | Bounded 4-source integration is reproducible |
| `QA_PIPELINE_READY` | true | Rulebook, schema, validator and pilot are reviewable |
| `QA_HUMAN_VERIFIED` | false | 0/10 QA accepted by a named reviewer |
| `BENCHMARK_READY` | false | Gold/relation review and coverage are incomplete |
| `METHOD_EVALUATION_READY` | false | No sealed official V4 Test exists |

## 6. Required next gate

Before scaling, a domain reviewer must: (1) verify all four new sources and validity/status metadata; (2) review each pilot locator, table header, typed fact and answer; (3) decide the two document-pack relations; (4) acquire evidence for the five empty high-value cells; and (5) approve the dependency-graph split protocol. Only then may accepted items be frozen and a new V4 Test be sealed.
