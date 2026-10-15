# Reproducibility Report

From `research/vietirr_v4_2/` run:

```powershell
python build_coverage.py
python QA_GENERATION_PIPELINE.py
python QA_VALIDATOR_V4_2.py V4_2_QA_DRAFTS.jsonl --check-sources --output QA_VALIDATION_V4_2.json
python QA_ADVERSARIAL_TESTS/build_fixture.py
python QA_ADVERSARIAL_TESTS/run_tests.py
python build_reports.py
python V4_2_INDEPENDENT_AUDIT.py
```

The standalone review bundle can reproduce the adversarial suite without PDFs because test 13 uses the embedded checksum-bound fixture. Full source/hash revalidation needs the external PDFs listed in `SOURCE_DEPENDENCIES.json`; the bundle does not claim to redistribute them.
