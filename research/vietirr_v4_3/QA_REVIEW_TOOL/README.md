# V4.3 local review tool

From `research/vietirr_v4_3` run:

```powershell
python QA_REVIEW_TOOL/serve.py
```

Open the printed local URL. Reviews are stored in browser `localStorage` until exported as JSONL. The repository ledger starts empty; importing/exporting never silently writes a human verdict into the repository.

If port 8765 is occupied, use for example `python QA_REVIEW_TOOL/serve.py --port 8876`.
