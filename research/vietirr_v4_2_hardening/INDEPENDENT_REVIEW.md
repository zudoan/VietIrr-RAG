# Independent review

The ZIP intentionally excludes PDF binaries and Candidate Test. Source URLs, paths and SHA-256 values are in `SOURCE_DEPENDENCIES.json`.

From the extracted bundle root:

```powershell
python research/vietirr_v4_2_hardening/QA_GENERATOR_TESTS/run_tests.py
python research/vietirr_v4_2_hardening/V4_2_HARDENING_INDEPENDENT_AUDIT.py
```

Expected results are hardening tests `24/24` and independent audit with zero failures. These checks establish technical reproducibility, not human semantic gold.
