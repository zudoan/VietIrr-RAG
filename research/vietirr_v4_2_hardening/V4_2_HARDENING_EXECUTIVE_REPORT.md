# VietIrr-RAG V4.2 Quality Hardening — Executive Report

## Outcome

All 38 V4.2 drafts were audited without modifying the frozen raw file. Decisions: **KEEP 22**, **REVISE 11**, **REJECT 5**. Human verified remains **0**.

## Mandatory repairs

- QA-021 and QA-032: false `CROSS_SOURCE_SYNTHESIS` labels replaced by `SINGLE_DOCUMENT_SYNTHESIS`. QA-028 received the same correction.
- QA-026: EV053 added to establish the 15-position domain; direct extrema evidence EV057/EV058 retained. It remains pending human table/source review.
- QA-036: storage EV035–EV038 removed; required evidence is only EV033/EV034. Arithmetic remains approximately `4,000 − 1,500 = 2,500 m³/s`.
- Additional minimality repairs: QA-004, QA-019, QA-025, QA-037 and QA-038.

## Diversity and generator

Twelve fact/reasoning clusters were classified. Five dominated questions were rejected, and QA-035 was rewritten from a repeated reservoir-specific subtraction into a three-reservoir comparison. The new generator produced two reproducible demos from previously unused evidence without code changes.

## Scientific decision

The hardening layer is technically ready for targeted human review. It is not official gold: no QA, relation, alternative set, table interpretation or legal applicability decision has human verification.
