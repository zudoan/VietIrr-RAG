# QA Diversity Report

## Decisions

- KEEP: **22**
- REVISE: **11**
- REJECT: **5**
- Human verified: **0**

## Semantic diversity

- Domains: {'D01': 8, 'D02': 2, 'D03': 6, 'D04': 4, 'D05': 8, 'D06': 10}
- Refined competencies: {'SINGLE_FACT_LOOKUP': 5, 'MULTI_FACT_LOOKUP': 8, 'VERIFIABLE_COMPUTATION': 9, 'QUANTITATIVE_COMPARISON': 6, 'VERSION_RESOLUTION': 1, 'INSUFFICIENT_EVIDENCE': 2, 'CONDITION_EVALUATION': 1, 'SINGLE_DOCUMENT_SYNTHESIS': 5, 'RULE_APPLICATION': 1}
- Distinct coverage cells/use cases: **18**
- Source document families: **8**
- QA using more than one evidence unit after repair: **29/38**
- Fact/reasoning clusters requiring analysis: **12**
- Exact/paraphrase duplicates retained: **0 identified**

Five dominated questions are rejected. QA-035 is rewritten to remove a repeated entity-swapped subtraction template. The retained same-fact pairs exercise materially different behavior (lookup vs arithmetic, comparison vs abstention/classification) and receive reduced sampling weight where appropriate.

Depth remains limited in D02 and D04, and there are still no validated cross-document questions because no relation is human verified. This is a disclosed corpus limitation, not a target to game.
