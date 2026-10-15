# V4.3 QA Coverage and Readiness Report

## Draft coverage

- Corpus manifest: **93 PDFs**; QA subset uses **8 PDFs**.
- Domains represented: **6** (D01, D02, D03, D04, D05, D06).
- Coverage cells/use-case proxies: **18**.
- Competencies: **9**.
- Evidence patterns: {"SAME_PAGE": 32, "CROSS_PAGE": 6}.
- Document families actually represented are limited to procedures/directives, seasonal plans, abstraction schedules, flood-operation reports and water-quality observation/forecast bulletins.

## Verified-layer separation

- Draft QA: **38**.
- Machine-supported without an outstanding machine caveat: **29**.
- Partial/review/ambiguous/unreadable combined: **9**.
- Human-accepted QA: **0**.

Draft coverage must not be reported as human-verified coverage. Human coverage is currently zero in every domain and competency.

## Depth

- Explicit arithmetic traces: **13**, reproduced from source-evidence operands: **13**.
- Same-page and cross-page are present; validated cross-document QA are absent.
- Text and table evidence are present; table-image adjudication remains pending.
- Rule/abstention examples exist, but legal applicability is not established for the local directive binary.
- Negative/abstention depth and temporal alignment remain limited.

## Expansion decision

**NO-GO for broad QA expansion now.** The blocker is not QA count: it is zero human-accepted QA, zero human-verified relations, unresolved legal-version evidence, table-completeness review and an internal event-date discrepancy. A small, controlled generator exercise may continue only as engineering validation and must not be merged into gold.
