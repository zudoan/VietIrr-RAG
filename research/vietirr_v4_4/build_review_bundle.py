"""Build the source-free V4.4 review handoff bundle."""
from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ZIP_PATH = HERE / "V4_4_REVIEW_BUNDLE.zip"
MANIFEST_PATH = HERE / "V4_4_BUNDLE_MANIFEST.json"

support = [
    ROOT / "research/vietirr_v4_1/V4_CORPUS_MANIFEST.jsonl",
    ROOT / "research/vietirr_v4_2/EVIDENCE_BANK.jsonl",
    ROOT / "research/vietirr_v4_2/V4_2_QA_DRAFTS.jsonl",
    ROOT / "research/vietirr_v4_2_hardening/QA_EVIDENCE_REPAIR.jsonl",
    ROOT / "research/vietirr_v4_2_hardening/QA_38_FULL_AUDIT.csv",
    ROOT / "research/vietirr_v4_3/QA_SOURCE_DOSSIERS.jsonl",
    ROOT / "research/vietirr_v4_3/QA_MACHINE_SOURCE_CHECKS.jsonl",
    ROOT / "research/vietirr_v4_3/V4_3_BENCHMARK_READINESS.json",
]

exclude_names = {ZIP_PATH.name, MANIFEST_PATH.name, "V4_4_INDEPENDENT_AUDIT.json"}
v44_files = [path for path in HERE.rglob("*") if path.is_file() and path.name not in exclude_names and "__pycache__" not in path.parts]
files = sorted(set(v44_files + support), key=lambda path: path.relative_to(ROOT).as_posix())

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

for path in files:
    rel = path.relative_to(ROOT).as_posix()
    assert path.suffix.lower() != ".pdf", f"PDF source must stay external: {rel}"
    assert "candidate_test" not in rel.lower(), f"sealed Candidate Test path forbidden: {rel}"

manifest = {
    "schema_version": "1.0",
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "bundle": "V4_4_REVIEW_BUNDLE.zip",
    "purpose": "review V4.4 corpus audit, evidence packs and controlled QA expansion",
    "source_pdfs_embedded": 0,
    "external_canonical_pdf_dependencies": 93,
    "candidate_test": "SEALED_NOT_OPENED_NOT_READ_NOT_HASHED_NOT_BUNDLED",
    "human_verified_count": 0,
    "official_gold_count": 0,
    "files": [{"path": path.relative_to(ROOT).as_posix(), "size_bytes": path.stat().st_size, "sha256": digest(path)} for path in files],
}
MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    archive.write(MANIFEST_PATH, MANIFEST_PATH.relative_to(ROOT).as_posix())
    for path in files:
        archive.write(path, path.relative_to(ROOT).as_posix())

print(json.dumps({"files": len(files) + 1, "zip_bytes": ZIP_PATH.stat().st_size, "pdfs_embedded": 0}))
