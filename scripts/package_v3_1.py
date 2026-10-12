"""Copy the principal VietIrrDocBench V3.1 artifacts into ./3.1."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "3.1"


def copy_file(relative: str, destination: str | None = None) -> None:
    source = ROOT / relative
    target = DEST / (destination or relative)
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_tree(relative: str, destination: str | None = None) -> None:
    source = ROOT / relative
    target = DEST / (destination or relative)
    if not source.is_dir():
        raise FileNotFoundError(source)
    shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)

    copy_tree("data/v3_1", "data")
    copy_tree("reports/v3_1", "reports")

    for relative in (
        "src/common/__init__.py", "src/common/io_utils.py",
        "src/structure/__init__.py", "src/structure/semantic_table_parser.py",
        "src/evidence/__init__.py", "src/evidence/relation_discovery.py",
        "src/negatives/__init__.py", "src/negatives/source_grounded_v3_1.py",
        "src/validation/__init__.py", "src/validation/answer_component_extractor_v3_1.py",
        "src/validation/evidence_relation_validator.py", "src/validation/necessity_validator_v3_1.py",
        "src/validation/source_grounded_negative_validator.py",
    ):
        copy_file(relative)

    for name in (
        "build_v3_1_document_audit.py", "build_v3_1_core.py", "build_v3_1_relations.py",
        "build_v3_1_challenge.py", "build_v3_1_negatives.py", "build_v3_1_splits.py",
        "build_v3_1_review_package.py", "audit_v3_1_quality.py", "finalize_v3_1.py",
        "repair_v3_review_labels.py", "package_v3_1.py",
    ):
        copy_file(f"scripts/{name}")

    copy_file("reports/V3_FINAL_STATS.json", "legacy_v3/V3_FINAL_STATS.json")
    snapshot_checksum = ROOT / "snapshots/v3_0/reports/V3_CHECKSUMS.json"
    if snapshot_checksum.is_file():
        copy_file("snapshots/v3_0/reports/V3_CHECKSUMS.json", "legacy_v3/V3_0_SNAPSHOT_CHECKSUMS.json")

    readiness = json.loads((DEST / "reports/V3_1_READINESS.json").read_text(encoding="utf-8"))
    readme = f"""# VietIrrDocBench V3.1 — Inspection Package

Thư mục này là bản sao các artifact chính của đợt **Scientific Validity Repair V3.1**.

## Số liệu canonical

- Accepted documents: {readiness['ACCEPTED_DOCUMENTS']}
- True core-long: {readiness['TRUE_CORE_LONG_DOCUMENTS']}
- Core QA: {readiness['CORE_QA']}
- Challenge QA: {readiness['CHALLENGE_QA']}
- Total QA: {readiness['TOTAL_QA']}
- Source-grounded negatives: {readiness['SOURCE_GROUNDED_NEGATIVES']}
- Critical semantic red flags: {readiness['SEMANTIC_RED_FLAGS']}
- Human validated: {str(readiness['HUMAN_VALIDATED']).lower()}

## Cấu trúc

- `data/`: toàn bộ dữ liệu V3.1, relation layer, QA, split và negatives.
- `reports/`: báo cáo chất lượng, readiness, final audit, checksum và review sample 100/100/100.
- `src/`: mã relation discovery, component/necessity validation và source-grounded negatives.
- `scripts/`: pipeline tái tạo và audit V3.1.
- `legacy_v3/`: thống kê V3 dùng cho đối chiếu và checksum snapshot V3.0.
- `PACKAGE_MANIFEST.json`: checksum SHA-256 của chính gói kiểm tra này.

PDF/OCR và toàn bộ `data/parsed` không được nhân bản vào gói gọn này; QA/review sample đã chứa exact evidence cần thiết để kiểm tra. Bản nguồn đầy đủ vẫn nằm trong workspace chính.
"""
    (DEST / "README_V3_1_PACKAGE.md").write_text(readme, encoding="utf-8", newline="\n")

    files = []
    for path in sorted(p for p in DEST.rglob("*") if p.is_file() and p.name != "PACKAGE_MANIFEST.json"):
        files.append({
            "path": path.relative_to(DEST).as_posix(),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        })
    manifest = {
        "package": "VietIrrDocBench V3.1 inspection package",
        "algorithm": "SHA-256", "file_count": len(files),
        "total_bytes_excluding_manifest": sum(row["bytes"] for row in files),
        "files": files,
    }
    (DEST / "PACKAGE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({"destination": str(DEST), "files": len(files) + 1, "bytes": sum(row["bytes"] for row in files)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
