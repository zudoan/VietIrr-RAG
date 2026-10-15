# QA Validation Report

## Existing suites rerun

- V4.1 adversarial: **16/16**.
- V4.2 adversarial: **16/16**; test 13 has no `SOURCE_UNREADABLE`.
- V4.2 independent audit: **50/50**.

## Hardening suite

- New hardening/generator tests: **24/24**.
- Positive cases: **7**; negative cases: **17**.
- Repaired records checked: **38**; deterministic repair errors: **0**.
- Minimality: **33** structural passes pending human, **5** rejected records.

Technical PASS covers schema/IDs, provenance fields, evidence membership, label constraints, arithmetic and fail-closed behavior. It does not certify semantic sufficiency or gold status.
