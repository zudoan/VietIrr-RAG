from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "c1.1"

CORE_FILES = [
    "pyproject.toml",
    "configs/phase_c1.json",
    "configs/phase_c1_1.json",
    "scripts/run_c1_1.py",
    "scripts/audit_c1_1.py",
    "scripts/package_c1_1.py",
    "tests/test_c11.py",
    "data/benchmark/dev.jsonl",
    "data/processed/evidence_units.jsonl",
    "data/processed/B1_INPUT_MANIFEST.json",
    "data/parsed/documents.jsonl",
    "data/parsed/regions.jsonl",
    "data/parsed/tables.jsonl",
    "reports/B1_INTEGRITY.json",
    "reports/C1/C1_READINESS.json",
    "reports/C1/C1_RESULTS.csv",
    "reports/C1/CONFIG.json",
    "reports/C1/CHECKSUMS.json",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    if DEST.exists():
        raise FileExistsError(
            f"Package destination already exists: {DEST}. "
            "Move or remove it explicitly before rebuilding."
        )

    files = list(CORE_FILES)
    files.extend(
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "src/viirr_retrieval").glob("*.py"))
    )
    for directory in (
        ROOT / "outputs/C1",
        ROOT / "outputs/C1_1",
        ROOT / "reports/C1_1",
    ):
        files.extend(
            path.relative_to(ROOT).as_posix()
            for path in sorted(directory.rglob("*"))
            if path.is_file()
        )
    files = sorted(set(files))

    missing = [relative for relative in files if not (ROOT / relative).is_file()]
    if missing:
        raise FileNotFoundError("Missing package inputs: " + ", ".join(missing))

    # Copy-only packaging: never move, rename, or delete workspace sources.
    for relative in files:
        source = ROOT / relative
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    readme = """# VietIrr-RAG - Phase C1.1 review package

This is a copy-only package. All original files remain unchanged in the parent
workspace.

## Verified result

- 93 Dev QA, 25 retrieval-multi QA, 45 unique gold-evidence sets.
- E4 Set-Aware V2: All R@20=0.6559, Multi All R@20=0.6000.
- C1.1 valid: true; independent audit: PASS; 55 tests passed.
- Evidence-set selection promising: false; Ready for C2: false.
- Candidate Test remained sealed and unchanged.

## Included

- C1.1 implementation, config, runner, audit, package script, and tests.
- Complete `reports/C1_1/` and `outputs/C1_1/` artifacts.
- C1 candidates/rankings/caches required to inspect and recompute C1.1.
- Dev QA, evidence units, and parsed metadata used by the representation audit.
- `PACKAGE_MANIFEST.json` with SHA-256 for every copied file.

## Excluded intentionally

Candidate Test content, train data, source PDFs, virtual environments, downloaded
models, and unrelated outputs are not copied. Candidate Test integrity is recorded
by hash in `reports/C1_1/C1_1_FINAL_AUDIT.json`.
"""
    readme_path = DEST / "README.md"
    readme_path.write_text(readme, encoding="utf-8", newline="\n")

    packaged = [DEST / relative for relative in files] + [readme_path]
    entries = [
        {
            "path": path.relative_to(DEST).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(packaged)
    ]
    manifest = {
        "package": "VietIrr-RAG Phase C1.1",
        "copy_only": True,
        "source_files_preserved": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "file_count_excluding_manifest": len(entries),
        "total_bytes_excluding_manifest": sum(row["bytes"] for row in entries),
        "candidate_test_included": False,
        "files": entries,
    }
    manifest_path = DEST / "PACKAGE_MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "destination": str(DEST),
                "files_including_manifest": len(entries) + 1,
                "bytes_excluding_manifest": manifest["total_bytes_excluding_manifest"],
                "copy_only": True,
            }
        )
    )


if __name__ == "__main__":
    main()
