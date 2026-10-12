from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "b2.3"

CORE_FILES = [
    "pyproject.toml",
    "configs/phase_b.json",
    "configs/phase_b2_1.json",
    "configs/phase_b2_2.json",
    "configs/phase_b2_3.json",
    "scripts/audit_b2.py",
    "scripts/reproduce_b2.py",
    "scripts/run_b2_1.py",
    "scripts/run_b2_2.py",
    "scripts/audit_b2_2.py",
    "scripts/run_b2_3.py",
    "scripts/audit_b2_3.py",
    "scripts/package_b2_3.py",
    "tests/test_b2_retrieval.py",
    "tests/test_b21.py",
    "tests/test_b22.py",
    "tests/test_b23.py",
    "docs/B2_WINDOWS_REPRO.md",
    "data/processed/B1_INPUT_MANIFEST.json",
    "reports/B1_INTEGRITY.json",
    "reports/B2/B2_FINAL_AUDIT.json",
    "reports/B2/B2_READINESS.json",
    "reports/B2_1/VERIFICATION.json",
    "reports/B2_1/READINESS.json",
    "outputs/B2_2/rankings/p0_s1_b50_dev.jsonl",
    "outputs/B2_2/rankings/p0_s1_b100_dev.jsonl",
    "outputs/B2_3/cache/m2_scores.jsonl",
    "outputs/B2_3/cache/m2_metadata.json",
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
        ROOT / "reports/B2_2",
        ROOT / "reports/B2_3",
        ROOT / "outputs/B2_3/rankings",
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

    # Packaging is copy-only. No source file is moved, renamed, or deleted.
    for relative in files:
        source = ROOT / relative
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    readme = """# VietIrr-RAG — Phase B2.3 review package

This is a copy-only review package containing the primary Phase B2.3 code,
configuration, tests, reports, ranking outputs, and reranker score cache.
All source files remain unchanged in the parent workspace.

## Verified result

- B2.3 valid: true; final audit: PASS; 93 DEV QA; Candidate Test untouched.
- Modality mapping coverage: 93/93.
- Candidate coverage@100: 0.7742.
- M0 B100: All R@10=0.4516, All R@20=0.6129, MRR=0.2988.
- M1 B100: All R@10=0.4624, All R@20=0.6237, MRR=0.2855.
- M2 B100: All R@10=0.5484, All R@20=0.6452, MRR=0.3490.
- Cached ranking reproducibility and independent artifact recomputation: PASS.
- Main remaining bottleneck: candidate miss.

## Included

- `src/viirr_retrieval/`: retrieval and B2.1–B2.3 evaluation implementation.
- `configs/`: B2 through B2.3 configurations.
- `tests/`: retrieval and B2.1–B2.3 tests.
- `scripts/`: runners, audits, reproduction helper, and this package builder.
- `reports/B2_3/`: complete B2.3 reports, audit, readiness, and checksums.
- `outputs/B2_3/rankings/`: three primary B2.3 ranking outputs.
- `outputs/B2_3/cache/m2_scores.jsonl`: reusable M2 score cache and metadata.
- Two P0/S1 B2.2 candidate rankings used as B2.3 inputs.
- Compact B1/B2/B2.1/B2.2 lineage and verification context.
- `PACKAGE_MANIFEST.json`: package-level SHA-256 hashes and byte sizes.

## Excluded intentionally

The Python virtual environment, downloaded 2.27 GB reranker model, large frozen
corpus, and unrelated retrieval caches are not duplicated. They remain in the
parent workspace and are not primary B2.3 review outputs.
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
        "package": "VietIrr-RAG Phase B2.3",
        "copy_only": True,
        "source_files_preserved": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "file_count_excluding_manifest": len(entries),
        "total_bytes_excluding_manifest": sum(row["bytes"] for row in entries),
        "excluded": [
            ".venv_b2",
            "downloaded 2.27 GB reranker model",
            "large frozen source corpus",
            "outputs/B2/cache",
            "outputs/B2_1/cache",
            "unrelated caches and outputs",
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
                "destination": str(DEST),
                "files_including_manifest": len(entries) + 1,
                "bytes_excluding_manifest": manifest["total_bytes_excluding_manifest"],
            }
        )
    )


if __name__ == "__main__":
    main()
