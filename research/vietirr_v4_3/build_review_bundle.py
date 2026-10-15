"""Build the redistributable V4.3 review bundle without source PDFs or Candidate Test."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ZIP = HERE / "V4_3_REVIEW_BUNDLE.zip"
MANIFEST = HERE / "V4_3_BUNDLE_MANIFEST.json"

excluded = {ZIP.name, MANIFEST.name, "V4_3_INDEPENDENT_AUDIT.json"}
files = [path for path in HERE.rglob("*") if path.is_file() and path.name not in excluded and "__pycache__" not in path.parts]
support = [
    ROOT / "research/vietirr_v4_2/V4_2_QA_DRAFTS.jsonl",
    ROOT / "research/vietirr_v4_2/EVIDENCE_BANK.jsonl",
    ROOT / "research/vietirr_v4_2/EVIDENCE_RELATIONS.jsonl",
    ROOT / "research/vietirr_v4_2/QA_SCHEMA_V4_2.json",
    ROOT / "research/vietirr_v4_2/QA_VALIDATOR_V4_2.py",
    ROOT / "research/vietirr_v4_2_hardening/QA_EVIDENCE_REPAIR.jsonl",
    ROOT / "research/vietirr_v4_2_hardening/QA_38_FULL_AUDIT.csv",
    ROOT / "research/vietirr_v4_2_hardening/QA_MINIMALITY_AUDIT.csv",
    ROOT / "research/vietirr_v4_2_hardening/ALTERNATIVE_GOLD_SETS.jsonl",
    ROOT / "research/vietirr_v4_2_hardening/SOURCE_DEPENDENCIES.json",
    ROOT / "research/vietirr_v4_1/V4_CORPUS_MANIFEST.jsonl",
    ROOT / "research/vietirr_v4_1/QA_GROUND_UP_PILOT.jsonl",
    ROOT / "research/vietirr_v4_1/QA_PILOT_AUDIT.csv",
]
files = sorted(set(files + support), key=lambda path: path.relative_to(ROOT).as_posix())
rows = [{
    "path": path.relative_to(ROOT).as_posix(),
    "size_bytes": path.stat().st_size,
    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
} for path in files]
manifest = {
    "bundle": ZIP.name,
    "scope": "Published artifacts, validators, disclosed source excerpts and frozen supporting records",
    "payload_file_count": len(rows),
    "source_pdfs_included": False,
    "external_pdf_dependencies": 8,
    "candidate_test_included": False,
    "human_review_rows_included": 0,
    "official_gold": False,
    "files": rows,
}
MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, path.relative_to(ROOT).as_posix())
    archive.write(MANIFEST, MANIFEST.relative_to(ROOT).as_posix())
print(json.dumps({"bundle": ZIP.name, "payload_files": len(rows) + 1, "source_pdfs": 0, "candidate_test": 0}))
