from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "c1.2"

CORE_FILES = [
    "pyproject.toml",
    "configs/phase_c1_2.json",
    "scripts/run_c1_2.py",
    "scripts/audit_c1_2.py",
    "scripts/package_c1_2.py",
    "tests/test_c12.py",
    "data/benchmark/dev.jsonl",
    "data/processed/evidence_units.jsonl",
    "data/parsed/documents.jsonl",
    "data/parsed/regions.jsonl",
    "data/parsed/tables.jsonl",
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
        ROOT / "reports/C1_2",
        ROOT / "outputs/B2/rankings",
        ROOT / "outputs/B2_1/rankings",
        ROOT / "outputs/B2_2/rankings",
        ROOT / "outputs/C1",
        ROOT / "outputs/C1_1",
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

    # Copy-only packaging: workspace sources are never moved, renamed, or deleted.
    for relative in files:
        source = ROOT / relative
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    readme = """# VietIrr-RAG - Phase C1.2 review package

This folder is a copy-only package. Every original file remains unchanged in
the parent workspace.

## Verified result

- Baseline verification and independent audit: PASS.
- 93 Dev QA, 25 retrieval-multi QA, and 8 unique multi gold sets.
- 8 candidate-missing multi QA: 6 page-pruning and 2 page-localization misses.
- All 8 missing units are recoverable from at least one existing artifact.
- C1.2 valid: true; Ready for C2: false; 69 tests passed.
- Candidate Test remained sealed and is not included.

## Included

- C1.2 implementation, config, runner, audit, package script, and tests.
- Complete `reports/C1_2/` outputs, including diagnosis and candidate ceilings.
- B2/B2.1/B2.2 ranking artifacts used for page and region diagnosis.
- C1 candidates/rankings/caches and C1.1 E4 artifacts used for verification.
- Dev QA, evidence units, and parsed metadata used by the representation audit.
- `PACKAGE_MANIFEST.json` with SHA-256 for every copied file.

## Excluded intentionally

Candidate Test content, train data, source PDFs, virtual environments, downloaded
models, embedding indexes, and unrelated outputs are not copied. Candidate Test
integrity is recorded only by hash in `reports/C1_2/C1_2_FINAL_AUDIT.json`.
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
        "package": "VietIrr-RAG Phase C1.2",
        "copy_only": True,
        "source_files_preserved": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "file_count_excluding_manifest": len(entries),
        "total_bytes_excluding_manifest": sum(row["bytes"] for row in entries),
        "candidate_test_included": False,
        "files": entries,
    }
    (DEST / "PACKAGE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "destination": str(DEST),
        "files_including_manifest": len(entries) + 1,
        "bytes_excluding_manifest": manifest["total_bytes_excluding_manifest"],
        "copy_only": True,
    }))


if __name__ == "__main__":
    main()
