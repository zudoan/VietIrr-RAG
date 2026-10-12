from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "b2_b2.1"

CORE_FILES = [
    "pyproject.toml",
    "configs/phase_b.json",
    "configs/phase_b2_1.json",
    "scripts/audit_b2.py",
    "scripts/reproduce_b2.py",
    "scripts/run_b2_1.py",
    "scripts/package_b2_b21.py",
    "tests/test_b2_retrieval.py",
    "tests/test_b21.py",
    "docs/B2_WINDOWS_REPRO.md",
    "data/processed/B1_INPUT_MANIFEST.json",
    "reports/B1_INTEGRITY.json",
]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    if DEST.exists():
        raise FileExistsError(
            f"Package destination already exists: {DEST}. "
            "Move or remove it explicitly before rebuilding."
        )

    relative_files = list(CORE_FILES)
    relative_files.extend(
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "src/viirr_retrieval").glob("*.py"))
    )
    for directory in (
        ROOT / "reports/B2",
        ROOT / "reports/B2_1",
        ROOT / "outputs/B2/rankings",
        ROOT / "outputs/B2_1/rankings",
    ):
        relative_files.extend(
            path.relative_to(ROOT).as_posix() for path in sorted(directory.glob("*")) if path.is_file()
        )
    relative_files = sorted(set(relative_files))

    missing = [relative for relative in relative_files if not (ROOT / relative).is_file()]
    if missing:
        raise FileNotFoundError("Missing package inputs: " + ", ".join(missing))

    for relative in relative_files:
        source = ROOT / relative
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    readme = """# VietIrr-RAG — Phase B2 + B2.1 package

This review package contains the essential implementation, configuration, tests,
reports, audits, and raw development-set rankings for Phase B2 and B2.1.

## Final status

- B2 independently verified: true.
- B2.1 valid: true.
- Best controlled page representation: P2 structure-aware.
- All R@20 at P=10: 0.5914 (P0) to 0.6129 (P2).
- Complete Gold Page Recall@10: 0.6559 to 0.6989.
- Main remaining bottleneck: page pruning.
- Candidate Test was byte-hashed only and remained untouched.
- Cached rerun reproduced all 13 B2.1 ranking files byte-for-byte.

## Included

- `src/viirr_retrieval/`: B1/B2/B2.1 retrieval and evaluation code.
- `configs/`: frozen B2 and B2.1 experiment configurations.
- `tests/`: B2 and B2.1 unit tests.
- `scripts/`: audit, reproduction, B2.1 runner, and package builder.
- `reports/B2/` and `reports/B2_1/`: complete primary reports and audits.
- `outputs/B2/rankings/` and `outputs/B2_1/rankings/`: primary raw rankings.
- `PACKAGE_MANIFEST.json`: byte sizes and SHA-256 checksums.

## Excluded intentionally

The virtual environment, downloaded E5 model, embedding/BM25 caches, and large frozen
source corpus are not duplicated. They remain in the parent workspace and can be
recreated or reused by following `docs/B2_WINDOWS_REPRO.md` and the saved configs.
"""
    readme_path = DEST / "README.md"
    readme_path.write_text(readme, encoding="utf-8", newline="\n")

    packaged = [DEST / relative for relative in relative_files] + [readme_path]
    entries = [
        {
            "path": path.relative_to(DEST).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
        for path in sorted(packaged)
    ]
    manifest = {
        "package": "VietIrr-RAG B2 + B2.1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "file_count_excluding_manifest": len(entries),
        "total_bytes_excluding_manifest": sum(row["bytes"] for row in entries),
        "excluded": [
            ".venv_b2",
            "downloaded E5 model",
            "outputs/B2/cache",
            "outputs/B2_1/cache",
            "large frozen source corpus",
        ],
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
    }))


if __name__ == "__main__":
    main()
