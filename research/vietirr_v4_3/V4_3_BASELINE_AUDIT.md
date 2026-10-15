# V4.3 Baseline Audit

## Reconciled inputs

- Raw V4.2 QA: **38** unique IDs.
- Hardening rows: **38** with the same ID set.
- Hardening decisions from data: **KEEP 22 / REVISE 11 / REJECT 5**.
- Evidence bank: **59 units / 8 PDFs**.
- Relations: **21**, human-verified relations: **0**.
- Source PDFs required by the 38 current QA: **8**; all eight are present and SHA-256 matched.

## Revision reconciliation

Hardening changes are materialized in `QA_EVIDENCE_REPAIR.jsonl`, while `V4_2_QA_DRAFTS.jsonl` remains unchanged. In particular, QA-026 uses EV053/EV057/EV058; QA-036 uses only EV033/EV034; QA-021/028/032 are labeled `SINGLE_DOCUMENT_SYNTHESIS`. V4.3 does not overwrite either layer.

## Source limitations found from PDFs

1. The local safety-directive PDF contains the cited text but leaves the document number/date fields blank. Legal issuance and applicability are therefore not established solely by this binary.
2. The dam-operation PDF section is titled as the November 2023 flood, but its page-8 flow paragraph contains March-style dates (`14/3`). Numeric values are traceable; event-time attribution requires adjudication.
3. QA-026 has a narrative 15-position extrema statement, but row-by-row completeness was not independently established by the machine pass.
4. V4.1 QA-008 remains an abstention/review case: no evidence grants retrospective applicability of the 2025 procedure to the 2021 plan.

## Integrity

`V4_3_INPUT_FREEZE.json` records the named baseline, V3.2 control files and all eight PDFs before V4.3 output creation. Candidate Test was not opened, read, hashed or packaged.

**Phase A decision:** input is precise enough to proceed; unresolved semantic/legal issues are carried forward as review gaps, not silently resolved.
