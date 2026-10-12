"""Create an immutable snapshot before the V3.2 final semantic patch."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "snapshots" / "pre_v3_2_final_semantic_patch"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    if DEST.exists():
        raise FileExistsError(f"Refusing to overwrite snapshot: {DEST}")
    sources = (
        "data/v3_2_final",
        "reports/v3_2_final",
        "src/validation/topic_alignment_validator_v3_2.py",
        "src/validation/ocr_quality_gate_v3_2_final.py",
        "src/validation/table_metric_semantics_validator.py",
        "scripts/build_v3_2_final_patch.py",
        "scripts/audit_v3_2_final_patch.py",
    )
    for relative in sources:
        source, target = ROOT / relative, DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(source, target)
    files = []
    for path in sorted(p for p in DEST.rglob("*") if p.is_file()):
        files.append({"path": path.relative_to(DEST).as_posix(), "bytes": path.stat().st_size,
                      "sha256": sha256(path)})
    manifest = {"snapshot": DEST.name, "algorithm": "SHA-256", "file_count": len(files),
                "total_bytes": sum(item["bytes"] for item in files), "files": files}
    (DEST / "SNAPSHOT_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_dir = ROOT / "reports" / "v3_2_final_semantic"
    report_dir.mkdir(parents=True, exist_ok=True)
    readiness = {"FINAL_SEMANTIC_PATCH_COMPLETE": False, "DATASET_FROZEN": False,
                 "READY_FOR_BASELINE_EXPERIMENTS": False, "READY_FOR_HUMAN_GOLD_REVIEW": False,
                 "HUMAN_VALIDATED": False, "reset_reason": "Final semantic patch in progress"}
    (report_dir / "V3_2_FINAL_SEMANTIC_READINESS.json").write_text(
        json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"snapshot": str(DEST), "files": len(files),
                      "bytes": manifest["total_bytes"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
