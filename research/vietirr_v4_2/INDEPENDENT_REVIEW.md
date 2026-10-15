# Independent Review Instructions

1. Install Python 3.11+ and `pypdf`.
2. Extract the ZIP, then run `python QA_ADVERSARIAL_TESTS/run_tests.py`.
3. Expected: 16/16 caught and `test13_source_unreadable_absent=true`.
4. Inspect coverage, evidence, QA audit, pilot review, duplicate report, and readiness status.
5. For full PDF revalidation, obtain files from `SOURCE_DEPENDENCIES.json`, verify SHA-256, preserve the declared paths, and run the validator in the original workspace with `--check-sources`.

The ZIP intentionally excludes source PDFs and Candidate Test. It is self-contained for the claimed adversarial tests, not for full PDF revalidation or semantic human review.
