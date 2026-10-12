"""Package the frozen VietIrrDocBench V3.2 final semantic patch into ./3.2."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "3.2"


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
    shutil.copytree(source, target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    copy_tree("data/v3_2_final_semantic")
    copy_tree("reports/v3_2_final_semantic")
    copy_file("snapshots/pre_v3_2_final_semantic_patch/SNAPSHOT_MANIFEST.json",
              "snapshot/SNAPSHOT_MANIFEST.json")

    source_files = (
        "src/common/__init__.py",
        "src/common/io_utils.py",
        "src/structure/__init__.py",
        "src/structure/semantic_table_parser.py",
        "src/validation/__init__.py",
        "src/validation/answer_component_extractor_v3_1.py",
        "src/validation/necessity_validator_v3_1.py",
        "src/validation/topic_alignment_validator_v3_2.py",
        "src/validation/contextual_topic_alignment_final.py",
        "src/validation/evidence_time_validator_final.py",
        "src/validation/entity_ocr_canonicalizer_final.py",
        "src/validation/ocr_quality_gate_v3_2.py",
        "src/validation/ocr_quality_gate_v3_2_final.py",
        "src/validation/table_metric_semantics_validator.py",
    )
    for relative in source_files:
        copy_file(relative, f"code/{relative}")

    scripts = (
        "start_v3_2.py",
        "build_v3_2_final.py",
        "audit_v3_2_final.py",
        "start_v3_2_final_patch.py",
        "build_v3_2_final_patch.py",
        "audit_v3_2_final_patch.py",
        "start_v3_2_final_semantic_patch.py",
        "build_v3_2_final_semantic.py",
        "temporal_consistency_scan.py",
        "final_semantic_red_flag_scan.py",
        "package_v3_2.py",
    )
    for name in scripts:
        copy_file(f"scripts/{name}", f"code/scripts/{name}")

    report_dir = ROOT / "reports" / "v3_2_final_semantic"
    stats = json.loads((report_dir / "dataset_stats.json").read_text(encoding="utf-8"))
    readiness = json.loads((report_dir / "V3_2_FINAL_SEMANTIC_READINESS.json").read_text(encoding="utf-8"))
    audit = json.loads((report_dir / "V3_2_FINAL_SEMANTIC_AUDIT.json").read_text(encoding="utf-8"))
    qa = stats["qa"]
    answer = stats["answer_evidence"]
    retrieval = stats["retrieval_evidence"]
    location = stats["location"]
    negatives = stats["negatives"]
    splits = stats["splits"]
    readme = f"""# VietIrrDocBench V3.2 — Final Semantic Freeze Patch Package

Dataset frozen: **{str(readiness['DATASET_FROZEN']).lower()}**  
Independent verification: **{audit['audit_status']}**  
Human validated: **false**

## Canonical counts

- Input QA: {qa['input']}
- Final accepted QA: {qa['total']} ({qa['core']} Core, {qa['challenge']} Challenge)
- Rejected in final semantic patch: {qa['rejected_in_final_semantic_patch']}; uncertain: {qa['uncertain']}
- Answer evidence: {answer['single']} single, {answer['2']} two, {answer['3plus']} three-plus
- Retrieval evidence: {retrieval['single']} single, {retrieval['2']} two, {retrieval['3plus']} three-plus
- Location: {location['same_page']} same-page, {location['same_document_cross_page']} same-document cross-page, {location['cross_document']} cross-document
- Valid source-grounded negatives: {negatives['source_grounded']}
- Invalid negatives removed: {negatives['removed_in_final_semantic_patch']}
- Splits: train {splits['train']['total']}, dev {splits['dev']['total']}, candidate test {splits['candidate_test']['total']}
- Dev Challenge QA: {splits['dev']['challenge']}
- Dev retrieval-multi QA: {splits['dev']['retrieval_multi']}
- Document/family leakage: {stats['leakage_count']}
- Critical semantic red flags: {audit['critical_semantic_red_flags']}
- Series holdout heavy: {str(stats['SERIES_HOLDOUT_HEAVY']).lower()}
- Temporal QA repaired: {stats['repairs'].get('TEMPORAL_SEMANTICS', 0)}
- Core topic QA repaired: {stats['repairs'].get('CONTEXTUAL_TOPIC_ALIGNMENT', 0)}
- Entity/metric OCR QA normalized: {stats['entity_ocr']['status_counts'].get('NORMALIZED', 0)}

## Contents

- `data/v3_2_final_semantic/`: final clean QA, splits, evidence maps, and validated negatives.
- `reports/v3_2_final_semantic/`: semantic audits, canonical statistics, and final freeze gates.
- `code/`: validators, build, independent audit, temporal scan, and packaging code.
- `snapshot/SNAPSHOT_MANIFEST.json`: manifest of the pre-semantic-patch snapshot.
- `PACKAGE_MANIFEST.json`: SHA-256 and size for every packaged file.

The package does not duplicate raw PDFs or the full snapshot. No baseline, training,
RAG, corpus expansion, or additional QA generation is included.
"""
    (DEST / "README_PACKAGE_3_2.md").write_text(readme, encoding="utf-8", newline="\n")

    files = []
    for path in sorted(p for p in DEST.rglob("*") if p.is_file() and p.name != "PACKAGE_MANIFEST.json"):
        files.append({"path": path.relative_to(DEST).as_posix(),
                      "sha256": sha256(path), "bytes": path.stat().st_size})
    manifest = {
        "package": "VietIrrDocBench V3.2 Final Semantic Freeze Patch",
        "source_version": "v3_2_final_semantic",
        "dataset_frozen": readiness["DATASET_FROZEN"],
        "independent_verification": audit["audit_status"],
        "critical_semantic_red_flags": audit["critical_semantic_red_flags"],
        "human_validated": False,
        "algorithm": "SHA-256",
        "file_count": len(files),
        "total_bytes_excluding_manifest": sum(row["bytes"] for row in files),
        "files": files,
    }
    (DEST / "PACKAGE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"destination": str(DEST), "files": len(files) + 1,
                      "bytes": manifest["total_bytes_excluding_manifest"],
                      "dataset_frozen": readiness["DATASET_FROZEN"],
                      "verification": audit["audit_status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
