# VietIrr-RAG V4.3 — Executive Report

## Outcome

All **38/38** QA have a source dossier and a direct machine-source-check output. The reconciled machine statuses are: **MACHINE_SUPPORTED 29**, **PARTIALLY_SUPPORTED 8**, **REVIEW_REQUIRED 1**. No result is labeled human-verified or gold.

## Findings

- All eight PDF binaries exist and match declared SHA-256 values.
- **13/13** explicit arithmetic traces reproduce from source-evidence operands.
- QA-026 remains `REVIEW_REQUIRED`: narrative extrema are present, but row-by-row completeness across 15 positions was not auto-certified.
- QA-036 retains only EV033/EV034 and recomputes 4,000 − 1,500 = 2,500 m³/s; event-time attribution remains partial because the PDF page mixes a November section heading with March dates.
- QA-031/032 source text is present, but the local directive PDF has blank number/date fields, so applicability/version status is unresolved.
- Four source-grounded revisions are proposed with lineage; none is accepted automatically.

## Decision

**Technically complete for targeted human review; conditional GO for review operations; NO-GO for broad QA expansion and official benchmark release.** Human reviews completed: **0**.
