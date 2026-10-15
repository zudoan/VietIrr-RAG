# V4.4 Deep Audit — Independent Audit Results

- Status: **PASS**
- Checks: **30/30 PASS**
- Mutation tests: **5/5 caught**
- Human semantic/gold verification: **not claimed**

## Checks

- `A01_MANIFEST_COUNT` — PASS: rows=93 unique=93
- `A02_PHYSICAL_PDF_HASHES` — PASS: All 93 physical PDFs resolve and match both declared hashes
- `A03_CORPUS_AUDIT_ACCOUNTING` — PASS: rows=93
- `A04_HONEST_INSPECTION_STATUS` — PASS: Every canonical PDF has an allowed explicit inspection status
- `A05_DEEP_EVIDENCE_RESOLVES` — PASS: evidence_records=60
- `A06_DEEP_DOCUMENT_COUNT` — PASS: deep_documents=20
- `A07_COVERAGE_USECASE_SPECIFIC` — PASS: cells=16
- `B01_RELATION_ENDPOINTS` — PASS: relations=9
- `B02_RELATION_STATUS_VOCAB` — PASS: All relation statuses use required vocabulary
- `B03_NO_FAKE_HUMAN_RELATION` — PASS: No relation claims human verification
- `B04_PACK_RELATIONS_RESOLVE` — PASS: packs=3
- `B05_PACK_EVIDENCE_RELATIONS_RESOLVE` — PASS: pack_evidence=9
- `C00_FROZEN_INPUT_HASHES` — PASS: matched=4/4
- `C01_BASELINE_QA_COUNT` — PASS: rows=48 unique=48
- `C02_USER_KEEP_38` — PASS: USER_KEEP=38
- `C03_QA_REVIEW_ACCOUNTING` — PASS: review_rows=48
- `C04_NO_HUMAN_GOLD_PROMOTION` — PASS: All 48 remain non-gold
- `C05_QA016_OPEN_BOUND_RISK` — PASS: QA-016 explicitly requires revision
- `C06_KNOWN_RISKS_PRESERVED` — PASS: Known extrema/legal/chronology issues are explicit
- `D01_NEW_QA_COUNT` — PASS: new_qa=8
- `D02_ANSWER_COMPONENT_SUPPORT` — PASS: Every answer component points to a declared evidence ID
- `D02B_INLINE_EVIDENCE_RESOLVES` — PASS: declared=8 inline=8
- `D03_GENERATION_METHOD_HONEST` — PASS: Manual curation is not disguised as an automatic generator
- `D04_NEW_QA_VALIDATION` — PASS: validation_rows=8
- `D05_NEW_QA_NOT_GOLD` — PASS: No new QA claims human approval
- `D06_COMPETENCY_PATTERN_SANITY` — PASS: No cross-document label is assigned to a single source
- `E01_UPSTREAM_INPUTS_PRESENT` — PASS: Required frozen/raw upstream QA inputs resolve
- `E02_NO_CANDIDATE_TEST_LEAKAGE` — PASS: output_paths_clean=True; declarations_false=True; all_QA_sources_canonical=True
- `E03_DEPENDENCY_REPRODUCIBLE` — PASS: PyMuPDF=1.28.0
- `F01_MUTATION_TESTS` — PASS: caught=5/5

PASS establishes structural integrity, provenance resolution, and declared controls; it does not establish human semantic correctness or official gold status.
