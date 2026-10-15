#!/usr/bin/env python3
"""Create and clean-room verify the scientific deep-audit handoff."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


REPO = Path(__file__).resolve().parents[2]
AUDIT = Path(__file__).resolve().parent
SOURCE_HANDOFF = REPO / "VR4_4_COMPLETE_AUDIT_HANDOFF"
DEST = REPO / "VR4_4_SCIENTIFIC_DEEP_AUDIT_HANDOFF"
ARCHIVE = REPO / "VR4_4_SCIENTIFIC_DEEP_AUDIT_HANDOFF.zip"
REPORT = REPO / "VR4_4_SCIENTIFIC_DEEP_AUDIT_CLEANROOM.json"
NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_file(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main() -> int:
    if DEST.exists() or ARCHIVE.exists():
        raise FileExistsError("Refusing to overwrite an existing final handoff directory/archive")

    checkpoint_path = AUDIT / "V4_4_DEEP_AUDIT_CHECKPOINT.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint.update({
        "updated_at": NOW,
        "current_phase": "COMPLETE_READY_FOR_HANDOFF",
        "pending_tasks": ["Human domain/source review", "Official gold adjudication"],
        "gate_status": {"A": "PASS_WITH_DECLARED_LIMITATIONS", "B": "PARTIAL_SOURCE_SUPPORTED", "C": "PASS", "D": "PASS_MACHINE_PENDING_HUMAN"},
        "continuation_command": "python research/vietirr_v4_4_deep_audit/V4_4_DEEP_AUDIT_INDEPENDENT_AUDIT.py",
    })
    checkpoint["completed_files"] = sorted(
        path.relative_to(AUDIT).as_posix()
        for path in AUDIT.rglob("*")
        if path.is_file() and path.name != "V4_4_DEEP_AUDIT_CHECKPOINT.json"
    )
    checkpoint_path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # New deep-audit outputs and scripts.
    shutil.copytree(AUDIT, DEST / "research" / "vietirr_v4_4_deep_audit")

    # Canonical source bundle: all 93 PDFs and the exact manifest.
    manifest_source = SOURCE_HANDOFF / "CORPUS_FILE_MANIFEST.csv"
    copy_file(manifest_source, DEST / "VR4_4_COMPLETE_AUDIT_HANDOFF" / "CORPUS_FILE_MANIFEST.csv")
    copy_file(SOURCE_HANDOFF / "CHECKSUMS.sha256", DEST / "VR4_4_COMPLETE_AUDIT_HANDOFF" / "CHECKSUMS.sha256")
    manifest_rows = list(csv.DictReader(manifest_source.open(encoding="utf-8-sig", newline="")))
    if len(manifest_rows) != 93:
        raise RuntimeError(f"Expected 93 canonical PDF rows, got {len(manifest_rows)}")
    for row in manifest_rows:
        relative = PurePosixPath(row["bundled_path"])
        source = SOURCE_HANDOFF / relative
        if sha256(source) != row["computed_sha256"]:
            raise RuntimeError(f"Source hash mismatch before packaging: {row['document_id']}")
        copy_file(source, DEST / "VR4_4_COMPLETE_AUDIT_HANDOFF" / relative)

    # Exact upstream metadata/OCR and QA research dependencies used by the builder.
    dependency_files = [
        "data/documents.jsonl",
        "research/vietirr_v4_2/V4_2_QA_DRAFTS.jsonl",
        "research/vietirr_v4_2_hardening/QA_38_FULL_AUDIT.csv",
        "research/vietirr_v4_3/QA_SOURCE_DOSSIERS.jsonl",
        "research/vietirr_v4_4/baseline/PILOT_38_RECONCILIATION.jsonl",
        "research/vietirr_v4_4/qa/V4_4_QA_NEW_DRAFTS.jsonl",
        "research/vietirr_v4_4/qa/V4_4_QA_VALIDATION_RESULTS.jsonl",
        "research/vietirr_v4_4/corpus/CORPUS_93_CANONICAL_AUDIT.csv",
    ]
    for relative in dependency_files:
        copy_file(REPO / PurePosixPath(relative), DEST / PurePosixPath(relative))
    for source in sorted((REPO / "data" / "ocr" / "v3").glob("*.jsonl")):
        copy_file(source, DEST / "data" / "ocr" / "v3" / source.name)

    (DEST / "requirements.txt").write_text("PyMuPDF==1.28.0\n", encoding="utf-8")
    root_readme = """# VietIrr-RAG V4.4 Scientific Deep Audit Handoff

This archive is self-contained for the declared audit: it includes all 93 canonical source PDFs, their canonical manifest, OCR records used for scanned decisions, exact upstream QA/audit inputs, new deep-audit artifacts, and executable checks.

## Review

1. Read `research/vietirr_v4_4_deep_audit/V4_4_DEEP_AUDIT_EXECUTIVE_REPORT.md`.
2. Review corpus, pack, and QA artifacts below that directory.
3. Run:

```powershell
python research/vietirr_v4_4_deep_audit/V4_4_DEEP_AUDIT_INDEPENDENT_AUDIT.py
```

The archive intentionally excludes sealed Candidate Test material. Machine PASS does not mean human semantic correctness or official gold readiness.
"""
    (DEST / "README.md").write_text(root_readme, encoding="utf-8")

    # Manifest excludes its own control files to avoid circular hashes.
    rows = []
    for path in sorted(p for p in DEST.rglob("*") if p.is_file() and p.name not in {"HANDOFF_MANIFEST.json", "CHECKSUMS.sha256"}):
        rows.append({
            "path": path.relative_to(DEST).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    handoff_manifest = {
        "generated_at": NOW,
        "package_name": DEST.name,
        "self_contained_for_declared_audit": True,
        "canonical_pdf_count": 93,
        "candidate_test_included": False,
        "human_gold_claimed": False,
        "file_count_excluding_controls": len(rows),
        "files": rows,
    }
    (DEST / "HANDOFF_MANIFEST.json").write_text(json.dumps(handoff_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksum_targets = sorted(p for p in DEST.rglob("*") if p.is_file() and p.name != "CHECKSUMS.sha256")
    checksum_text = "".join(f"{sha256(path)}  {path.relative_to(DEST).as_posix()}\n" for path in checksum_targets)
    (DEST / "CHECKSUMS.sha256").write_text(checksum_text, encoding="utf-8")

    # Stable ZIP paths under one top-level directory.
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in sorted(p for p in DEST.rglob("*") if p.is_file()):
            arcname = (Path(DEST.name) / path.relative_to(DEST)).as_posix()
            archive.write(path, arcname)

    # Clean extraction: verify all checksums, 93 PDFs, and rerun independent audit.
    with tempfile.TemporaryDirectory(prefix="vietirr_v44_deep_", dir=REPO / ".tmp") as temp_name:
        temp = Path(temp_name)
        with zipfile.ZipFile(ARCHIVE) as archive:
            archive.extractall(temp)
        extracted = temp / DEST.name
        checksum_ok = True
        checksum_lines = (extracted / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines()
        for line in checksum_lines:
            expected, relative = line.split("  ", 1)
            checksum_ok &= sha256(extracted / PurePosixPath(relative)) == expected
        extracted_pdfs = list((extracted / "VR4_4_COMPLETE_AUDIT_HANDOFF").rglob("*.pdf"))
        process = subprocess.run(
            [sys.executable, "research/vietirr_v4_4_deep_audit/V4_4_DEEP_AUDIT_INDEPENDENT_AUDIT.py"],
            cwd=extracted,
            text=True,
            capture_output=True,
            encoding="utf-8",
        )
        clean_report = {
            "generated_at": NOW,
            "status": "PASS" if checksum_ok and len(extracted_pdfs) == 93 and process.returncode == 0 else "FAIL",
            "archive": ARCHIVE.name,
            "archive_sha256": sha256(ARCHIVE),
            "archive_size_bytes": ARCHIVE.stat().st_size,
            "checksum_entries": len(checksum_lines),
            "all_checksums_pass": checksum_ok,
            "canonical_pdfs_extracted": len(extracted_pdfs),
            "independent_audit_returncode": process.returncode,
            "independent_audit_stdout": process.stdout.strip(),
            "independent_audit_stderr": process.stderr.strip(),
            "candidate_test_included": False,
            "human_gold_claimed": False,
        }
    REPORT.write_text(json.dumps(clean_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(clean_report, ensure_ascii=False))
    return 0 if clean_report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
