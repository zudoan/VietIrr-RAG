from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "phaseb"

FILES = [
    "pyproject.toml",
    "configs/phase_b.json",
    "scripts/audit_b2.py",
    "scripts/reproduce_b2.py",
    "scripts/package_phaseb.py",
    "tests/test_b2_retrieval.py",
    "docs/B2_WINDOWS_REPRO.md",
    "data/processed/B1_INPUT_MANIFEST.json",
    "reports/B1_INTEGRITY.json",
    "reports/B2/B2_BASELINE_METRICS.json",
    "reports/B2/B2_BASELINE_REPORT.md",
    "reports/B2/B2_CANDIDATE_CEILING.json",
    "reports/B2/B2_EXPERIMENT_MANIFEST.json",
    "reports/B2/B2_FAILURE_ANALYSIS.md",
    "reports/B2/B2_FAILURE_DETAILS.jsonl",
    "reports/B2/B2_FAILURE_SUMMARY.json",
    "reports/B2/B2_FINAL_AUDIT.json",
    "reports/B2/B2_PAGE_DIAGNOSTICS.json",
    "reports/B2/B2_PYTEST_RESULT.json",
    "reports/B2/B2_READINESS.json",
    "reports/B2/B2_REPRODUCIBILITY.json",
    "outputs/B2/rankings/bm25_dev_top200.jsonl",
    "outputs/B2/rankings/e5_dev_top200.jsonl",
    "outputs/B2/rankings/hybrid_dev_top200.jsonl",
    "outputs/B2/rankings/page_hybrid_dev_top100.jsonl",
    "outputs/B2/rankings/page_region_dev_top200.jsonl",
]


def sha256(path: Path) -> str:
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

    missing = [relative for relative in FILES if not (ROOT / relative).is_file()]
    source_dir = ROOT / "src" / "viirr_retrieval"
    source_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in source_dir.glob("*.py")
        if path.is_file()
    )
    missing.extend(relative for relative in source_files if not (ROOT / relative).is_file())
    if missing:
        raise FileNotFoundError("Missing package inputs: " + ", ".join(missing))

    package_files = FILES + source_files
    for relative in package_files:
        source = ROOT / relative
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    readme = """# VietIrrDocBench — Phase B package

This folder contains the essential Phase B1/B2 implementation, validation artifacts,
reports, and final development-set rankings.

## Verified outcome

- B1 integrity: PASS (89 documents, 2,479 pages, 27,045 indexable units, 545 QA).
- Development retrieval set: 93 questions, including 25 multi-evidence questions.
- Best Recall@20: page-to-region retrieval, 0.5914.
- Best candidate ceiling: Recall@100 = 0.8065 and Recall@200 = 0.8602.
- Main diagnosed bottleneck: page localization.
- B2 final audit: PASS; ready for Phase C.
- Frozen candidate test data was not parsed or used for evaluation/tuning.

## Contents

- `src/viirr_retrieval/`: retrieval and experiment code.
- `configs/phase_b.json`: Phase B configuration.
- `tests/`: retrieval unit tests.
- `scripts/`: audit, reproduction, and packaging scripts.
- `docs/B2_WINDOWS_REPRO.md`: Windows reproduction guide.
- `reports/`: B1 integrity and complete B2 reports/audits.
- `outputs/B2/rankings/`: primary dev ranking outputs.
- `PACKAGE_MANIFEST.json`: size and SHA-256 for every packaged artifact.

## Deliberately excluded

The Python virtual environment, downloaded model files, embedding caches, and the large
frozen source corpus are not duplicated here. They are reproducible or remain in the
parent workspace. Follow `docs/B2_WINDOWS_REPRO.md` from the workspace root to rerun.
"""
    readme_path = DEST / "README_PHASE_B.md"
    readme_path.write_text(readme, encoding="utf-8", newline="\n")

    manifested_paths = [DEST / relative for relative in package_files] + [readme_path]
    entries = []
    for path in sorted(manifested_paths):
        entries.append(
            {
                "path": path.relative_to(DEST).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    manifest = {
        "package": "VietIrrDocBench Phase B",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "file_count_excluding_manifest": len(entries),
        "total_bytes_excluding_manifest": sum(item["bytes"] for item in entries),
        "excluded": [
            ".venv_b2",
            "downloaded model files",
            "outputs/B2/cache",
            "large frozen source corpus",
        ],
        "files": entries,
    }
    (DEST / "PACKAGE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(
        json.dumps(
            {
                "package": str(DEST),
                "files_including_manifest": len(entries) + 1,
                "bytes_excluding_manifest": manifest["total_bytes_excluding_manifest"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
