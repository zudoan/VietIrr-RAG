# Phase B2 Windows reproduction

Run from the workspace root in PowerShell. Candidate Test is sealed; the B2 command only opens `data/benchmark/dev.jsonl`.

```powershell
C:\Python310\python.exe -m venv .venv_b2
.\.venv_b2\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu128
.\.venv_b2\Scripts\python.exe -m pip install sentence-transformers pytest rank-bm25 scipy
.\.venv_b2\Scripts\python.exe -m pip install -e . --no-build-isolation

.\.venv_b2\Scripts\python.exe -m viirr_retrieval.cli all --root .
.\.venv_b2\Scripts\python.exe -m pytest -q

$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
.\.venv_b2\Scripts\python.exe -m viirr_retrieval.cli b2 --root .
.\.venv_b2\Scripts\python.exe scripts/audit_b2.py
```

The E5 cache is written to `outputs/B2/cache/`; rankings are in `outputs/B2/rankings/`. Delete neither source data nor benchmark annotations. The default execution path refuses any split other than DEV.

