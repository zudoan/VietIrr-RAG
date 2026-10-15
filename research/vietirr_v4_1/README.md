# VietIrr-RAG V4.1 review workspace

Run from the repository root:

```powershell
python research/vietirr_v4_1/freeze_inputs.py
python research/vietirr_v4_1/build_corpus.py
python research/vietirr_v4_1/build_coverage.py
python research/vietirr_v4_1/QA_GENERATION_PIPELINE.py
python research/vietirr_v4_1/QA_VALIDATOR_V2.py research/vietirr_v4_1/QA_GROUND_UP_PILOT.jsonl --output research/vietirr_v4_1/QA_PILOT_VALIDATION.json
python research/vietirr_v4_1/QA_ADVERSARIAL_TESTS/run_tests.py
python research/vietirr_v4_1/build_deliverables.py
python research/vietirr_v4_1/V4_1_INDEPENDENT_AUDIT.py
python research/vietirr_v4_1/build_review_bundle.py
```

Do not rerun `freeze_inputs.py` after modifying frozen inputs; it is a pre-change seal. The bundle intentionally excludes PDF binaries and every Candidate Test artifact. Source URLs and checksums are in the corpus manifest.
