"""Create the independent V4.2 review bundle without redistributing source PDFs."""
from __future__ import annotations
import hashlib
import json
import zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent; V41=HERE.parent/"vietirr_v4_1"
manifest={x["doc_id"]:x for x in map(json.loads,(V41/"V4_CORPUS_MANIFEST.jsonl").read_text(encoding="utf-8").splitlines())}
bank=[json.loads(x) for x in (HERE/"EVIDENCE_BANK.jsonl").read_text(encoding="utf-8").splitlines()]
doc_ids=sorted({x["doc_id"] for x in bank})
deps={"redistribution":"SOURCE_PDFS_NOT_INCLUDED","reason":"Use authoritative URLs/local corpus; verify SHA-256 before full source validation.",
      "documents":[{k:manifest[d].get(k) for k in ("doc_id","source_title","publisher","source_url","local_path","sha256")} for d in doc_ids]}
(HERE/"SOURCE_DEPENDENCIES.json").write_text(json.dumps(deps,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

writeup="""# Independent Review Instructions

1. Install Python 3.11+ and `pypdf`.
2. Extract the ZIP, then run `python QA_ADVERSARIAL_TESTS/run_tests.py`.
3. Expected: 16/16 caught and `test13_source_unreadable_absent=true`.
4. Inspect coverage, evidence, QA audit, pilot review, duplicate report, and readiness status.
5. For full PDF revalidation, obtain files from `SOURCE_DEPENDENCIES.json`, verify SHA-256, preserve the declared paths, and run the validator in the original workspace with `--check-sources`.

The ZIP intentionally excludes source PDFs and Candidate Test. It is self-contained for the claimed adversarial tests, not for full PDF revalidation or semantic human review.
"""
(HERE/"INDEPENDENT_REVIEW.md").write_text(writeup,encoding="utf-8")

FILES=[
 "README.md","INDEPENDENT_REVIEW.md","SOURCE_DEPENDENCIES.json","V4_2_INPUT_FREEZE.json",
 "DOMAIN_USE_CASE_COVERAGE.csv","QA_COVERAGE_MATRIX.csv","COVERAGE_GAP_REPORT.md",
 "EVIDENCE_BANK.jsonl","EVIDENCE_RELATIONS.jsonl","EVIDENCE_SET_CANDIDATES.jsonl","EVIDENCE_BANK_AUDIT.md",
 "V4_1_PILOT_REVIEW.csv","V4_1_PILOT_REVIEW_REPORT.md","QA_GENERATION_PROTOCOL.md","QA_GENERATION_PIPELINE.py",
 "build_evidence.py","build_qa.py","V4_2_QA_DRAFTS.jsonl","V4_2_QA_AUDIT.csv","QA_DUPLICATE_REPORT.md",
 "DUPLICATE_LEAKAGE_AUDIT.json","QA_SCHEMA_V4_2.json","QA_VALIDATOR_PATCH.py","QA_VALIDATOR_V4_2.py",
 "QA_VALIDATION_V4_2.json","QA_MUTATION_TEST_REPORT.md","QA_REPRODUCIBILITY_REPORT.md",
 "V4_2_DATASET_QUALITY_REPORT.md","V4_2_BENCHMARK_READINESS.json","V4_2_INDEPENDENT_AUDIT.py",
 "QA_ADVERSARIAL_TESTS/run_tests.py","QA_ADVERSARIAL_TESTS/TEST_RESULTS.json",
 "QA_ADVERSARIAL_TESTS/fixtures/SOURCE_FIXTURE_FACT_VALUE.json",
]
missing=[x for x in FILES if not (HERE/x).exists()]
if missing: raise SystemExit(f"Missing bundle files: {missing}")
checks={x:hashlib.sha256((HERE/x).read_bytes()).hexdigest() for x in FILES}
bundle_manifest={"bundle":"V4_2_REVIEW_BUNDLE.zip","payload_file_count":len(FILES),"source_pdfs_included":False,
                 "candidate_test_included":False,"files":checks}
(HERE/"V4_2_BUNDLE_MANIFEST.json").write_text(json.dumps(bundle_manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
zip_path=HERE/"V4_2_REVIEW_BUNDLE.zip"
with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED) as z:
    for x in FILES: z.write(HERE/x,arcname=x)
    z.write(HERE/"V4_2_BUNDLE_MANIFEST.json",arcname="V4_2_BUNDLE_MANIFEST.json")
print({"bundle":str(zip_path),"payload_files":len(FILES)+1,"source_pdfs":0,"candidate_test":0})
