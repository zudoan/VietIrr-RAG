from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "b2.2"

CORE_FILES = [
    "pyproject.toml",
    "configs/phase_b.json",
    "configs/phase_b2_1.json",
    "configs/phase_b2_2.json",
    "scripts/audit_b2.py",
    "scripts/reproduce_b2.py",
    "scripts/run_b2_1.py",
    "scripts/run_b2_2.py",
    "scripts/audit_b2_2.py",
    "scripts/package_b2_2.py",
    "tests/test_b2_retrieval.py",
    "tests/test_b21.py",
    "tests/test_b22.py",
    "docs/B2_WINDOWS_REPRO.md",
    "data/processed/B1_INPUT_MANIFEST.json",
    "reports/B1_INTEGRITY.json",
    "outputs/B2_1/rankings/p0_pages_dev_top100.jsonl",
    "outputs/B2_1/rankings/p2_pages_dev_top100.jsonl",
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
        ROOT / "reports/B2",
        ROOT / "reports/B2_1",
        ROOT / "reports/B2_2",
        ROOT / "outputs/B2_2/rankings",
    ):
        files.extend(
            path.relative_to(ROOT).as_posix()
            for path in sorted(directory.glob("*"))
            if path.is_file()
        )
    files = sorted(set(files))
    missing = [relative for relative in files if not (ROOT / relative).is_file()]
    if missing:
        raise FileNotFoundError("Missing package inputs: " + ", ".join(missing))

    for relative in files:
        source = ROOT / relative
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    readme = """# VietIrr-RAG — Phase B2.2 review package

This folder contains the main code, configurations, tests, reports, audit artifacts,
and raw rankings for the B2.2 Candidate Coverage and Page-Pruning Study.

## Verified result

- B2.2 valid: true; 93 DEV QA; Candidate Test remained sealed.
- Twelve controlled ranking outputs reproduced byte-for-byte from cache.
- Artifact-level independent metric recomputation: PASS.
- P2/B100 budgeted coverage: S0=0.6989, S1=0.7849, S2=0.7849.
- P2/B100 All R@20: S0=0.6129, S1=0.6022, S2=0.5269.
- Main remaining bottleneck: region ranking.
- Statistical conclusion for final-recall improvement: inconclusive.

## Included

- `src/viirr_retrieval/`: B1–B2.2 retrieval and evaluation implementation.
- `configs/`: B2, B2.1, and B2.2 configurations.
- `tests/`: all retrieval and candidate-metric tests.
- `scripts/`: runners, audits, reproduction helper, and package builder.
- `reports/B2_2/`: complete B2.2 reports, audit, readiness, and checksums.
- `outputs/B2_2/rankings/`: twelve raw controlled ranking outputs.
- `reports/B2/`, `reports/B2_1/`, and two B2.1 page rankings: verification context.
- `PACKAGE_MANIFEST.json`: package-level SHA-256 and byte sizes.

## Excluded intentionally

The Python virtual environment, downloaded E5 model, BM25/embedding caches, and large
frozen corpus are not duplicated. They remain in the parent workspace. These items are
large or reproducible and are not primary B2.2 review outputs.
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
        "package": "VietIrr-RAG Phase B2.2",
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
