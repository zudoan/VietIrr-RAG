# VietIrr-RAG V4.1 — QA Rulebook V2

## 1. Status and governing principle

This rulebook is rebuilt from operational use cases. It does not inherit a V3.2 question template or treat the V4.0 validator as proof of correctness. The required path is:

`Use case → information need → evidence contract → eligible source → QA → deterministic check → human/domain review`.

Candidate Test is outside the process. A structural pass is never a semantic pass. Machine extraction is not gold evidence. A draft legal document may support version-awareness or abstention but cannot establish an applicable duty.

## 2. Evidence contract

Every item identifies answer components, source locators, typed facts, required relations, allowed operations, minimal sufficient evidence sets, alternatives, and conditions that force abstention. Numeric facts require entity, metric, value, unit, time role/time, source role, page hash and a contextual anchor. Table evidence also requires header inheritance to be checked by a person before gold release.

Minimality is recomputed from component coverage: deleting each member of a declared minimal set must leave at least one required answer component unsupported. A self-declared `necessity_claim=true` has no evidentiary force.

## 3. Competency contracts

| Competency | Business purpose | Creation condition | Evidence requirement | Reasoning / gold | Positive example | Negative example | Reject / review rule | Validation |
|---|---|---|---|---|---|---|---|---|
| FACTUAL_LOOKUP | Retrieve one operationally useful fact | Named entity, metric and reference context | One exact locator with complete typed fact | LOOKUP; answer preserves unit/time/source role | Natural area of Bắc Nam Hà with 2025 procedure cited | “What does the document say about the system?” | Reject vague intent or missing context | L1 schema; L2 page/hash/typed fact; L3 usefulness and header context |
| DEFINITION_CONCEPT | Recover a source-defined concept | Definition has explicit scope/source | Complete definition and governing scope | LOOKUP; no generalization | Source definition of a facility class | Generic textbook definition not in corpus | Reject if scope is removed | L2 anchor; L3 completeness |
| RULE_CONDITION_INTERPRETATION | Retrieve condition, action and exception | Applicable reviewed rule exists | Signed version, clause, actor, condition, action, exception | FILTER/LOOKUP; structured condition-action gold | Operation required under named condition in current procedure | Action copied without exception/version | Block draft or unresolved effectivity for positive rule claims | L2 version/source role; mandatory L3 legal/domain review |
| QUANTITATIVE_COMPARISON | Support a real decision comparison | Same metric/unit/time role and comparable entities/periods | At least two typed operands and comparison purpose | COMPARE/SUBTRACT; operands and result retained | Difference in source-stated shortage area between Hà Nam and Nam Định | Listing unrelated numbers as “comparison” | Reject incompatible metric/unit/time | L2 compatibility and arithmetic; L3 comparison purpose |
| TEMPORAL_COMPARISON | Compare change across time | Same entity/metric/method and explicit times | Two reviewed facts with aligned time roles | TEMPORAL_ORDER/COMPARE | Same station and parameter on two sampling dates | Publication date compared with forecast target | Reject role mismatch | L2 typed time roles; L3 method comparability |
| CROSS_SOURCE_SYNTHESIS | Combine complementary sources | Verified relation joins sources for one information need | Each source uniquely supports a required component; relation evidence | LOOKUP/COMPARE; all sources cited | Current procedure plus same-system plan when applicability is established | Two independent questions joined by “and” | Pending relation means REVIEW, never semantic pass | L2 component minimality; L3 relation validity |
| RULE_OBSERVATION_ALIGNMENT | Test a stated condition against an observation | Applicable rule and compatible observation exist | Rule threshold + observation, same entity/metric/unit/time scope | COMPARE; `met/not met/insufficient`, not legal compliance | Water level tested against applicable operating trigger | Current rule applied retrospectively without authority | Reject mismatch; abstain on unresolved applicability | L2 predicate trace; L3 legal scope |
| VERIFIABLE_COMPUTATION | Derive reproducible quantity | Operation is needed by use case | Typed operands, units and explicit operation trace | ADD/SUBTRACT; exact result | 1,200 ha − 1,020 ha = 180 ha | Unstated values or hidden arithmetic | Reject result/operand mismatch | L2 recomputes arithmetic; L3 business interpretation |
| CONFLICT_VERSION_RESOLUTION | Prevent silent use of obsolete/draft sources | Two sources differ in time/status/version | Both sources plus explicit supersession/effectivity evidence | VERSION_RESOLVE or ABSTAIN | 2025 act states replacement of 2016 procedure | Newer publication assumed to supersede older | If chain incomplete, answer must abstain | L2 source roles/status; L3 legal effect |
| INSUFFICIENT_EVIDENCE_DETECTION | Make safe abstention measurable | Evidence contract has a named missing dependency | Available sources plus explicit gap | ABSTAIN; gold names missing evidence | General safety directive cannot prove a named dam is safe | Model invents inspection result | Reject unsupported positive answer | L2 confirms missing contract; L3 confirms gap realism |

## 4. Domain correctness gates

- **Entity:** exact facility/station/system identity and hierarchy; fuzzy names are not relations.
- **Geography:** the answer cannot broaden source scope.
- **Metric/value/unit:** typed tuple and valid conversion; Vietnamese decimal punctuation must be interpreted in table context.
- **Time:** observation, forecast target, publication, season and effective date remain distinct.
- **Rule/version:** signed/effective status, amendment/replacement chain, condition and material exception.
- **Tables:** row label, column header, inherited unit and notes must be reviewed together.
- **Relations:** only `VERIFIED` may support released cross-document gold. `MANIFEST_PENDING_HUMAN` forces review.

## 5. Three-layer decisions

1. **Layer 1 / structural:** schema, IDs, source paths, locator bounds, duplicate QA IDs and split IDs.
2. **Layer 2 / deterministic semantics:** page hash, contextual anchors, typed numeric/time/source roles, unit compatibility, operation recomputation, component support and minimality. Failure is `FAIL`; an unprovable claim is `UNKNOWN/REVIEW`, never pass.
3. **Layer 3 / human/domain:** business realism, non-shallowness, source support, sufficiency/minimality, relation validity and legal/technical interpretation. Only a named reviewer may set all three review dimensions to PASS and `HUMAN_ACCEPTED`.

`SEMANTIC_PASS` requires Layer 1 PASS, Layer 2 PASS and a valid Layer 3 HUMAN_ACCEPTED record. Otherwise the highest possible release state is `READY_FOR_HUMAN_REVIEW`.

## 6. Rejection and leakage rules

Reject templated/vague questions, fake comparison, fake multi-evidence, mixed facilities, wrong entity/time/unit/version, invalid arithmetic, locator-correct/fact-wrong records, paraphrase duplicates, incomplete conditions and out-of-corpus positives. Candidate Test paths/IDs are forbidden. V3.2 questions cannot be read by the generation pipeline; `legacy_qa_used` must be false and generation is based on a curated evidence inventory.

## 7. Pilot release policy

Auto-valid pilot records stay `PENDING_HUMAN_REVIEW`. `AUTO_REJECTED` items are retained in the audit, not the release set. Sources accepted at document level do not imply QA or evidence acceptance. Until humans review V4.1 evidence tuples and questions, the pilot is a reviewable research artifact—not a gold benchmark.
