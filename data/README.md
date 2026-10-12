# Local data layout

The Git repository intentionally does not contain source PDFs, embedding caches, model
weights, full rankings, or frozen benchmark payloads. The original document metadata
marks redistribution as `UNCLEAR`, so public availability is not treated as permission
to redistribute files.

## Minimum artifacts for Phase E

Place the following canonical artifacts under the project root:

```text
data/
  processed/
    evidence_units.jsonl
    B1_INPUT_MANIFEST.json
  v3_1/
    metadata/
      documents.jsonl
  raw/
    ... local source PDFs referenced by documents.jsonl ...

reports/
  v3_2_final_semantic/
    dataset_stats.json
    V3_2_FINAL_SEMANTIC_READINESS.json

outputs/
  B2/
    cache/
      bm25_regions.pkl
```

`evidence_units.jsonl` can be rebuilt from canonical parsed artifacts with the B1 adapter.
The BM25 cache is optional: the API rebuilds it when absent, provided the corpus artifacts
and Python dependencies are available.

## Full research reproduction

Research phases additionally require frozen benchmark splits, parsed pages/regions/tables,
page and dense caches, and phase-specific rankings. Paths are declared in `configs/*.json`.
Use the matching audit and reproduction scripts in `scripts/`; do not substitute Candidate
Test for Dev or remove the sealed-test safeguards.

## Integrity

Verify local files against the manifests/checksums referenced by the selected report before
running an experiment. Never commit credentials, private documents, or source files whose
redistribution terms are unclear.
