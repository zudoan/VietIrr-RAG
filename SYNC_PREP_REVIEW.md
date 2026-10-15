# VietIrr-RAG V4 Research Artifacts — Public Sync Preparation Review

## 1. Final decision

- Branch: `sync/v4-research-artifacts`.
- Base commit: `05db4cac57e39889b63a5a7a4a45b5c2aaf7f1dc`.
- Final staged set: **188 files** (173 research artifacts, 6 aggregate QA reports, 2 analysis scripts, 3 clean-room reports, and 4 repository-control files).
- Status: **READY FOR PUBLIC PR REVIEW**, but **NOT A SELF-CONTAINED DATASET RELEASE**.
- No commit, push, merge or Pull Request has been created.
- No QA/evidence record, canonical ID, scientific result or verification verdict was changed.

The public staged set contains code, schemas, protocols, aggregate analyses, reports, manifests, hashes and locators. PDF binaries, raw excerpts, QA text exports and source-bearing builders remain local. Two artifacts found to contain source-derived text during PR review are represented by separately named public projections; their canonical files remain local at their original paths.

## 2. Technical blocker resolution

### 2.1. `QA_SCHEMA_V4_2.json`

Root cause: the `answer_components` schema was missing one closing brace. Consequently, `operations`, `unsupported_conditions`, `source_check` and `review` were parsed as children of `answer_components`; the root object then remained unclosed.

Minimal semantic-preserving patch:

```diff
-    "answer_components": {... "supported_by": {...}}},
+    "answer_components": {... "supported_by": {...}}}},
```

The added brace closes `answer_components` at the correct location. No property, constraint, enum, ID pattern or QA record changed.

Validation:

- JSON parse: PASS.
- JSON Schema Draft 2020-12 meta-validation: PASS.
- Root `required` versus `properties`: 18/18, no missing property.
- All 38 local V4.2 QA drafts validate: 38 records, 0 errors.
- Corrected schema SHA-256: `91e9a851ea68a8c3f2b003b8488452127f6b4231e28dc056792980695523e6d1`.
- Direct and transitive checksum references in V4.2 Hardening and V4.3 manifests/freezes were updated mechanically. Reference verification on the Git index: 483/483 hashes match.

### 2.2. Python dependency

`pypdf` was added only to the existing optional `corpus` dependency group in `pyproject.toml`:

```diff
-corpus = ["beautifulsoup4", "PyMuPDF", "requests"]
+corpus = ["beautifulsoup4", "PyMuPDF", "pypdf", "requests"]
```

No unrelated dependency changed. `PyMuPDF` continues to provide the `fitz` import used by Deep Audit code. `pytest` is already declared in `dev` and `research`; it was not installed in the current interpreter, so V4.4's 22 read-only test functions were invoked directly instead and all 22 passed without rewriting result files.

### 2.3. Byte-stable research artifacts

The research manifests contain byte-level SHA-256 values. Normal Git LF conversion would invalidate historical hashes for CRLF artifacts. `.gitattributes` now applies:

```gitattributes
research/** -text !eol diff
```

This preserves research artifact bytes across checkout while retaining textual diffs. It avoids rewriting scientific files or replacing hundreds of checksums solely because of line-ending conversion. A byte-aware whitespace check reports 0 true trailing-whitespace findings. Native `git diff --check` reports CRLF bytes as whitespace because the files are intentionally byte-preserved; those warnings are packaging-format warnings, not added spaces.

## 3. Final staged groups

| Group | Files | Public content |
|---|---:|---|
| V4.1 upstream metadata/protocols | 28 | Manifest, coverage, rulebook, validators, reports and checksums |
| V4.2 | 37 | Corrected schema, relations/sets, audits, reports, validators and manifests |
| V4.2 Hardening | 29 | Aggregate audits, schemas, tests, reports and manifests |
| V4.3 | 26 | Public-safe fact projection, review UI shell, reports, tests and manifests |
| V4.4 | 31 | Corpus/pack aggregate metadata, validation summaries, tests and reports |
| Scientific Deep Audit | 22 | Public-safe relation projection, aggregate analysis, relation/coverage summaries, validation and audit reports |
| `report_qa/` aggregate outputs | 6 | README plus document/domain/topic summaries |
| Root clean-room reports | 3 | Verification summaries without source payloads |
| Analysis scripts | 2 | Inventory and aggregate QA-analysis builders |
| Repository controls | 4 | `.gitignore`, `.gitattributes`, `pyproject.toml`, this report |

Exact paths are available with:

```powershell
git diff --cached --name-only
```

## 4. Source-bearing and rights-sensitive files kept local

The full 239-file set was scanned structurally and by exact-string propagation. The final public set has:

- 0 files with populated `anchor`, `source_text`, `source_text_span`, `span`, `source_excerpt`, `excerpt`, `snippet` or `evidence_snippets` fields;
- 0 exact copies of locally identified source excerpts;
- 0 exact copies of local QA question/answer text;
- aggregate facts, counts, IDs, hashes, source titles, URLs and locators only.

The following classes remain local and unstaged:

- 93 source PDFs and all PDF copies in handoff packages;
- ZIP bundles, cache, temporary folders and large duplicate handoffs;
- 55 files removed from the initial staged set because they contain source excerpts, source anchors, copied source strings or QA question/answer text;
- five Deep Audit files excluded from the public set: `CORPUS_93_CONTENT_AUDIT.csv`, `DEEP_DOCUMENT_EVIDENCE.jsonl`, `NEW_QA_DRAFTS.jsonl`, `PACK_RELATION_AUDIT.jsonl`, and `QA_48_HUMAN_REVIEW_QUEUE.csv`;
- canonical V4.3 `QA_FACT_VERIFICATION.csv`, which contains structured facts/calculations and several source-discrepancy notes;
- canonical V4.3 `QA_MACHINE_SOURCE_CHECKS.jsonl` and `QA_SOURCE_VERIFICATION_GAPS.csv`, plus V4.4 `PILOT_38_OPEN_ISSUES.md`, which repeated source-discrepancy text found during the final PR scan;
- `report_qa/outputs/QA_ANALYSIS_RECORDS.csv` and `QA_NEAR_DUPLICATES.csv`;
- reviewer-bearing local inventory `reports/document_inventory/ALL_PDF_DOCUMENT_INVENTORY.csv`;
- raw V3.2 data, OCR records and document metadata under `data/`.

Important excluded V4 groups include the 38 USER_KEEP payloads/reconciliations, the 10 V4.4 QA drafts/review queue, the 8 Deep Audit QA drafts, evidence banks with source spans, source dossiers/indexes, review-data payloads and builders embedding those exact strings. They were un-staged only; their local canonical files were not modified or deleted.

No claim is made that short snippets are automatically redistributable. They remain outside the public set until explicit rights approval.

### 4.1. Canonical-to-public projection mapping

| Canonical local dependency | Canonical SHA-256 | Public projection | Public SHA-256 | Public fields |
|---|---|---|---|---|
| `research/vietirr_v4_4_deep_audit/packs/PACK_RELATION_AUDIT.jsonl` | `f69c8d0a031d8844a47741eed9c4b8f60764f96e425c494f70e8dfa45df064bd` | `research/vietirr_v4_4_deep_audit/packs/PACK_RELATION_AUDIT_PUBLIC.jsonl` | `5f303ede3af0784f6d580273ba1fd3a09f0c9028c8b1761fdfc333300a7b6c53` | Relation/document IDs, type, page locators, PDF hashes, verification status, human-verification flag, evidence hashes and canonical-record hash |
| `research/vietirr_v4_3/QA_FACT_VERIFICATION.csv` | `60ce5223e834401a063dfcbc73b4d05f183157afc15b8a59d1a372ad7368b53a` | `research/vietirr_v4_3/QA_FACT_VERIFICATION_PUBLIC.csv` | `ebb65032b99067a5c14826a7282347093770e4f734646ef4b7b8bd282088dbef` | QA ID, machine/human status, counts, presence flag and hashes of omitted source-derived fields |

The canonical files are ignored by exact path and remain byte-identical in the local workspace. Scientific manifests, builders and independent-audit code continue to reference those canonical local paths and were not rewritten to treat the public projections as scientific inputs. Consequently, those checks require the controlled local artifacts and cannot run end-to-end from the public repository alone.

Additional canonical local-only dependencies removed after exact-string propagation checking:

| Local-only artifact | SHA-256 | Reason |
|---|---|---|
| `research/vietirr_v4_3/QA_MACHINE_SOURCE_CHECKS.jsonl` | `850d356b982497ec89221d2d909c1607423fad12ed281089dae72584515203c3` | Repeats source-discrepancy text; required by local V4.3/V4.4 audits and manifests |
| `research/vietirr_v4_3/QA_SOURCE_VERIFICATION_GAPS.csv` | `32216ea6f2809ee76c938bb97641f8424cf9a8f7a158e81646a812ac209d4ac7` | Repeats source-discrepancy text |
| `research/vietirr_v4_4/baseline/PILOT_38_OPEN_ISSUES.md` | `62711186cf4962a410076fc8066c8b516ff4b038355ae637317a2ded2f418dc6` | Repeats source-discrepancy text; referenced by the local V4.4 bundle manifest |
| `research/vietirr_v4_4_deep_audit/qa/QA_48_HUMAN_REVIEW_QUEUE.csv` | `a4a3d64f1208e57eb1fa4d60d361426e1577cf26e0a6e5dadef13f49f2f70c29` | Repeats source-discrepancy text; referenced by the local Deep Audit checkpoint |

The branch history was rewritten after PR review because the first public commit contained the canonical relation audit. Rewriting the branch removes that blob from the current branch head and PR diff, but does not guarantee removal from GitHub caches, pull-request references, forks or direct access by the prior commit SHA.

## 5. Reference and dependency verification

ID references were checked against the preserved local canonical registry without opening Candidate Test:

| ID class | Referenced by staged set | Unresolved against local canonical data |
|---|---:|---:|
| QA IDs | 66 | 0 |
| Evidence IDs | 52 | 0 |
| Evidence-set IDs | 32 | 0 |
| Document IDs | 93 | 0 |
| Relation IDs | 9 | 0 |

Manifest/schema/path verification:

- 483 checksum references checked; 483 match, 0 mismatch, 0 missing from the current local workspace.
- 63 unique referenced targets are intentionally local-only or outside the public staged set.
- The public repository therefore supports review of lineage, contracts and aggregate results, but cannot reproduce PDF/OCR/source-grounded runs end-to-end without a controlled local data store.

Local-only dependencies include PDFs, `data/documents.jsonl`, `data/ocr/v3/`, V3.2 train/dev, `reports/TCB_RR_P2_3/P2_3_FROZEN_CONFIG.json`, document inventory, handoff manifests, excluded QA/evidence payloads and V4.0/V4.1 upstream inputs.

## 6. Final safety checks

- Final staged size before any commit: below 1.0 MiB; largest file is below 74 KiB.
- Structured parsing from staged Git blobs: 44 JSON, 14 JSONL, 33 CSV, 40 Python and 1 TOML file; 0 parse errors.
- Secret/PII scan: 0 private keys, token signatures, credential assignments, emails, user-profile paths, workspace paths or local reviewer identifiers.
- Binary/archive scan: 0 PDF, ZIP, archive, model or array files.
- Candidate Test: 0 staged path names and 0 Candidate Test payload files. Remaining mentions are only sealed-policy declarations, exclusion assertions and pre-existing aggregate statistics. Candidate Test was not opened, read or hashed.
- Source-bearing scan: 0 direct source-text fields and 0 exact propagated source/QA strings in the final staged set.
- ID references: 0 unresolved against local canonical data.
- V4.2 schema: valid Draft 2020-12; 38/38 local records validate.
- V4.4 read-only test functions: 22/22 pass.
- No tracked working-tree modification remains outside the index after final staging.

## 7. Release boundary

This set is safe to open as a **public review PR for code, metadata and aggregate research artifacts**, subject to user approval to commit/push. It must not be described as:

- a self-contained corpus;
- a redistribution of the 93 PDFs;
- a public release of the 38, 10 or 8 QA payloads;
- a human-gold or fully reproducible source release.

Any future inclusion of excluded source-bearing files requires an explicit rights/distribution decision and a new review. No automatic sanitization of canonical scientific content was performed.
