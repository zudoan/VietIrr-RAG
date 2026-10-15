# V4.4 clean-room verification report

Final status: **FULLY_AUDITABLE**

Checks: 21 PASS, 0 FAIL, 0 BLOCKED, 0 NOT_APPLICABLE.

| Check | Status | Detail |
|---|---|---|
| ROOT_MANIFESTS | PASS | all required root manifests/reports are present |
| CHECKSUMS | PASS | all packaged regular files match CHECKSUMS.sha256 |
| CORPUS_93 | PASS | 93/93 canonical PDFs exist and match |
| CORPUS_UNIQUE_IDS | PASS | 93 unique canonical document IDs |
| DEPENDENCY_CLOSURE | PASS | all declared runtime dependencies are present and hash-matched |
| PARSED_JSON_DEPENDENCIES | PASS | all four parsed JSON sources are present |
| PILOT_38 | PASS | 38/38 pilot QA and KEEP decisions are preserved |
| PILOT_WARNINGS | PASS | source/semantic warnings remain traceable |
| NO_FALSE_HUMAN_GOLD | PASS | no pilot QA is silently promoted to human gold |
| NEW_QA_10 | PASS | all 10 V4.4 drafts are present and non-gold |
| QA_SOURCE_REFERENCES | PASS | all V4.4 QA source and evidence references resolve |
| PACK_SOURCE_REFERENCES | PASS | all selected pack document references resolve |
| RELATION_PROVENANCE | PASS | all relation sources resolve; one target is explicitly external/not-in-corpus |
| FROZEN_BASELINE_HASHES | PASS | all frozen upstream QA artifacts match recorded hashes |
| CANDIDATE_TEST_EXCLUDED | PASS | sealed Candidate Test is not packaged |
| DECLARED_COMPLETENESS | PASS | manifest completeness/status is appropriate |
| ARCHIVE_INTEGRITY | PASS | ZIP integrity and member paths are valid |
| ARTIFACT_CONSISTENCY | PASS | builder reproduces all stable scientific artifacts byte-for-byte |
| V4_4_TESTS | PASS | clean-room V4.4 tests pass 22/22 |
| V4_4_INDEPENDENT_AUDIT | PASS | clean-room independent audit passes 30/30 |
| HANDOFF_NEGATIVE_TESTS | PASS | all 10 deliberate corruptions are detected |

Package reproducibility does not by itself establish semantic correctness or human-gold eligibility.
