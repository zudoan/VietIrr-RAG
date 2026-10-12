"""Snapshot the pre-V3.2 state and reset final-freeze readiness."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "snapshots/pre_v3_2_final_freeze"


def copy_tree(relative: str) -> None:
    source = ROOT / relative
    target = SNAPSHOT / relative
    if source.exists():
        shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def copy_file(relative: str) -> None:
    source = ROOT / relative
    if source.is_file():
        target = SNAPSHOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    for relative in ("data/v3_1", "reports/v3_1", "reports/stage1", "src"):
        copy_tree(relative)
    for relative in ("STAGE1_FREEZE_REPORT.md",):
        copy_file(relative)
    for path in sorted((ROOT / "scripts").glob("*v3_1*.py")) + [ROOT / "scripts/validate_stage1_freeze.py"]:
        if path.is_file():
            copy_file(path.relative_to(ROOT).as_posix())
    files = []
    for path in sorted(p for p in SNAPSHOT.rglob("*") if p.is_file() and p.name != "SNAPSHOT_MANIFEST.json"):
        files.append({"path": path.relative_to(SNAPSHOT).as_posix(), "sha256": sha256(path), "bytes": path.stat().st_size})
    (SNAPSHOT / "SNAPSHOT_MANIFEST.json").write_text(json.dumps({
        "snapshot": "pre_v3_2_final_freeze", "immutable_reference": True,
        "file_count": len(files), "total_bytes": sum(x["bytes"] for x in files), "files": files,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    report = ROOT / "reports/v3_2"
    report.mkdir(parents=True, exist_ok=True)
    readiness = {
        "V3_2_COMPLETE": False, "TOTAL_QA": 0, "CORE_QA": 0, "CHALLENGE_QA": 0,
        "ANSWER_MULTI_EVIDENCE_QA": 0, "RETRIEVAL_MULTI_EVIDENCE_QA": 0,
        "ANSWER_THREE_PLUS_QA": 0, "RETRIEVAL_THREE_PLUS_QA": 0,
        "SAME_PAGE_QA": 0, "CROSS_PAGE_SAME_DOCUMENT_QA": 0, "CROSS_DOCUMENT_QA": 0,
        "TEXT_TABLE_QA": 0, "TABLE_TABLE_QA": 0, "CRITICAL_SEMANTIC_RED_FLAGS": 0,
        "UNRESOLVED_OCR_QA": 0, "VALID_SOURCE_GROUNDED_NEGATIVES": 0, "DEV_CHALLENGE_QA": 0,
        "QA_SEMANTIC_ALIGNMENT_PASS": False, "RELATION_INTENT_PASS": False,
        "RETRIEVAL_EVIDENCE_MAPPING_PASS": False, "NECESSITY_PASS": False,
        "OCR_QUALITY_PASS": False, "TABLE_SEMANTIC_PASS": False,
        "SOURCE_TRACEABILITY_PASS": False, "NEGATIVE_VALIDATION_PASS": False,
        "LEAKAGE_AUDIT_PASS": False, "REPORT_CONSISTENCY_PASS": False,
        "HUMAN_VALIDATED": False, "DATASET_FROZEN": False,
        "READY_FOR_BASELINE_EXPERIMENTS": False, "READY_FOR_HUMAN_GOLD_REVIEW": False,
    }
    (report / "V3_2_FREEZE_READINESS.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"snapshot": str(SNAPSHOT), "files": len(files), "bytes": sum(x["bytes"] for x in files), "readiness_reset": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
