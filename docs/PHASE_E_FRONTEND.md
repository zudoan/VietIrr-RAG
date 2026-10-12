# VietIrr-RAG Phase E — Frontend

Phase E adds a local React/TypeScript interface and a read-only HTTP adapter over the
existing frozen VietIrr corpus. It does not alter dataset, retrieval experiment, ranking,
or report artifacts.

## What is connected

- Search: the existing `BM25Retriever`, `data/processed/evidence_units.jsonl`, and its
  B2 cache at `outputs/B2/cache/bm25_regions.pkl`.
- Statistics: `reports/v3_2_final_semantic/dataset_stats.json` and the B1 manifest.
- Documents: `data/v3_1/metadata/documents.jsonl`.
- PDF links: only the `local_path` recorded by canonical metadata and only when that path
  resolves inside this workspace.

There is no answer-generation model in this workspace. The product therefore labels the
experience **Evidence Search** and returns source passages instead of a fabricated answer.
MAR-ER is not advertised as the live arbitrary-query method because its sealed experiment
is not a serving API.

## Windows quick start

Install frontend dependencies once:

```powershell
cd frontend
npm.cmd install
cd ..
```

Then start API and web app together:

```powershell
.\start_phase_e.cmd
```

Open `http://127.0.0.1:5173`. Stop both services with `Ctrl+C`.

API logs are written to `logs/phase_e_api.out.log` and
`logs/phase_e_api.error.log`.

## Separate development commands

```powershell
.\.venv_b2\Scripts\python.exe scripts\run_phase_e_api.py
cd frontend
npm.cmd run dev
```

Environment options are documented in `frontend/.env.example`.

## Validation

```powershell
.\.venv_b2\Scripts\python.exe -m pytest tests\test_phase_e_api.py -q
cd frontend
npm.cmd run typecheck
npm.cmd run build
```

## Known limitations

- Retrieval is the real B1 BM25 index, not a generative answer service.
- A browser PDF viewer decides how precisely `#page=N` is rendered.
- Several source files have `redistribution_status=UNCLEAR`; the interface serves local
  files for inspection and preserves the official source URL, but does not package PDFs.
- Corpus metadata is not human validated, which is surfaced in the API and landing stats.
