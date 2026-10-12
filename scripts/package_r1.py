from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "r1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add_if_file(paths: set[Path], relative_path: str) -> None:
    path = ROOT / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"Required packaging input is missing: {relative_path}")
    paths.add(path)


def main() -> None:
    if DEST.exists():
        raise FileExistsError(
            f"Destination already exists: {DEST}. Refusing to overwrite it."
        )

    files: set[Path] = set()
    required = [
        "pyproject.toml",
        "configs/phase_b.json",
        "configs/r1.json",
        "scripts/run_r1.py",
        "scripts/audit_r1.py",
        "scripts/package_r1.py",
        "tests/test_r1.py",
        "data/benchmark/dev.jsonl",
        "data/processed/evidence_units.jsonl",
        "data/parsed/documents.jsonl",
        "data/parsed/pages.jsonl",
        "data/parsed/regions.jsonl",
        "data/parsed/tables.jsonl",
        "outputs/C1/candidates/g0_b100_dev.jsonl",
        "outputs/C1/rankings/e0_g0_global_rrf_dev.jsonl",
        "outputs/B2_1/rankings/p0_pages_dev_top100.jsonl",
        "outputs/B2/cache/bm25_regions.pkl",
    ]
    for relative_path in required:
        add_if_file(files, relative_path)

    for path in (ROOT / "src" / "viirr_retrieval").glob("*.py"):
        files.add(path)
    for path in (ROOT / "reports" / "R1").rglob("*"):
        if path.is_file():
            files.add(path)
    for path in (ROOT / "outputs" / "R1").rglob("*"):
        if path.is_file() and path.suffix.lower() in {".json", ".jsonl"}:
            files.add(path)
    for path in (ROOT / "data" / "parsed").glob("*.json"):
        files.add(path)

    copied: list[dict[str, object]] = []
    for source in sorted(files, key=lambda item: item.relative_to(ROOT).as_posix()):
        relative = source.relative_to(ROOT)
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(
            {
                "path": relative.as_posix(),
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
            }
        )

    excluded_arrays: list[dict[str, object]] = []
    for source in sorted((ROOT / "outputs" / "R1").rglob("*.npy")):
        excluded_arrays.append(
            {
                "path": source.relative_to(ROOT).as_posix(),
                "bytes": source.stat().st_size,
                "sha256": sha256(source),
                "reason": "Large reproducible embedding array; metadata retained in package.",
            }
        )

    readme = """# VietIrr-RAG R1 review package

This directory is a copy-only review package. Original workspace files were not moved or deleted.

Included:
- R1 source code, configuration, test, audit, and runner files.
- R1 reports, rankings, contextual representations, window maps, and cache metadata.
- Dev benchmark and the processed/parsed inputs required to inspect or reproduce R1.
- Required upstream C1/B2 ranking and BM25 inputs.

Intentionally excluded:
- Sealed Candidate Test data.
- Large `.npy` embedding matrices. Their source paths, sizes, and SHA-256 hashes are recorded in `PACKAGE_MANIFEST.json`; JSON cache metadata remains included.
- Virtual environments, model downloads, temporary files, and unrelated phase artifacts.

Verified R1 status in the packaged reports:
- Dev questions: 93 (25 retrieval-multi).
- R1 audit: valid.
- Unit tests: 80 passed.
- Readiness decision: not ready for R2; see `reports/R1/READINESS.json` and `reports/R1/R1_REPORT.md`.
"""
    readme_path = DEST / "README.md"
    readme_path.write_text(readme, encoding="utf-8")

    manifest = {
        "package": "VietIrr-RAG R1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "copy_only": True,
        "source_workspace": str(ROOT),
        "candidate_test_included": False,
        "embedding_arrays_copied": False,
        "file_count_excluding_manifest": len(copied) + 1,
        "total_copied_bytes_excluding_manifest": sum(
            int(entry["bytes"]) for entry in copied
        )
        + readme_path.stat().st_size,
        "files": copied
        + [
            {
                "path": "README.md",
                "bytes": readme_path.stat().st_size,
                "sha256": sha256(readme_path),
            }
        ],
        "excluded_large_artifacts": excluded_arrays,
    }
    (DEST / "PACKAGE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "destination": str(DEST),
                "files_excluding_manifest": manifest["file_count_excluding_manifest"],
                "copied_mb_excluding_manifest": round(
                    int(manifest["total_copied_bytes_excluding_manifest"])
                    / (1024 * 1024),
                    2,
                ),
                "excluded_npy_files": len(excluded_arrays),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
