from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "c1"

CORE_FILES = [
    "pyproject.toml",
    "configs/phase_b.json",
    "configs/phase_b2_1.json",
    "configs/phase_b2_2.json",
    "configs/phase_b2_3.json",
    "configs/phase_c1.json",
    "scripts/run_c1.py",
    "scripts/audit_c1.py",
    "scripts/package_c1.py",
    "tests/test_c1.py",
    "docs/B2_WINDOWS_REPRO.md",
    "data/benchmark/dev.jsonl",
    "data/processed/evidence_units.jsonl",
    "data/processed/B1_INPUT_MANIFEST.json",
    "reports/B1_INTEGRITY.json",
    "outputs/B2/rankings/bm25_dev_top200.jsonl",
    "outputs/B2/rankings/e5_dev_top200.jsonl",
    "outputs/B2_1/rankings/p0_p20_dev_top200.jsonl",
    "outputs/B2_1/rankings/p2_p20_dev_top200.jsonl",
    "outputs/B2_2/rankings/p0_s1_b100_dev.jsonl",
    "outputs/B2_3/rankings/m1_global_rrf_b100_dev.jsonl",
    "outputs/B2_3/rankings/m2_cross_encoder_b100_dev.jsonl",
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
        ROOT / "reports/B2",
        ROOT / "reports/B2_1",
        ROOT / "reports/B2_2",
        ROOT / "reports/B2_3",
        ROOT / "reports/C1",
        ROOT / "outputs/C1",
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

    # Copy-only packaging: source files are never moved, renamed, or deleted.
    for relative in files:
        source = ROOT / relative
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    readme = """# VietIrr-RAG — Phase C1 review package

This is a copy-only package of the main Phase C1 code, configuration, tests,
reports, candidates, rankings, selector traces, and audit inputs. All source
files remain unchanged in the parent workspace.

## Verified result

- C1 valid: true; audit and independent artifact recomputation: PASS.
- 93 DEV QA, 25 retrieval-multi QA, and 45 unique gold-evidence sets.
- E0 G0+RRF: Candidate@100=0.7742, All R@20=0.6237, Multi All R@20=0.6000.
- E1 G1+RRF: Candidate@100=0.8172, All R@20=0.5054, Multi All R@20=0.5200.
- E2 G0+Cross-Encoder: Candidate@100=0.7742, All R@20=0.6452, Multi All R@20=0.4400.
- E3 G0+Set-Aware: Candidate@100=0.7742, All R@20=0.6237, Multi All R@20=0.6000.
- Decision: C1_INCONCLUSIVE; Ready for C2: false.
- Candidate Test remained sealed and unchanged.

## Included

- `src/viirr_retrieval/`: retrieval implementation through C1.
- `configs/phase_c1.json` and prerequisite B2 configurations.
- `scripts/run_c1.py`, `scripts/audit_c1.py`, and the package builder.
- `tests/test_c1.py`: C1 leakage, determinism, provenance, and invariant tests.
- `reports/C1/`: complete C1 results, analysis, audit, readiness, and checksums.
- `outputs/C1/`: G0/G1 candidates, E0–E3 rankings, global-rank cache, and R3 traces.
- Direct B2/B2.1/B2.2/B2.3 ranking inputs and cached M2 scores used by C1.
- DEV QA and the compact evidence-unit index needed for artifact inspection.
- Compact B1–B2.3 verification reports and `PACKAGE_MANIFEST.json`.

## Excluded intentionally

Candidate Test content, train data, source PDFs/corpus, Python virtual environments,
downloaded models, BM25 index cache, E5 embedding cache, and unrelated outputs are
not duplicated. Candidate Test integrity is represented only by its recorded SHA-256.
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
        "package": "VietIrr-RAG Phase C1",
        "copy_only": True,
        "source_files_preserved": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "file_count_excluding_manifest": len(entries),
        "total_bytes_excluding_manifest": sum(row["bytes"] for row in entries),
        "excluded": [
            "data/benchmark/candidate_test.jsonl (sealed; hash only)",
            "train data and source corpus/PDFs",
            ".venv and .venv_b2",
            "downloaded E5 and cross-encoder models",
            "outputs/B2/cache BM25 and E5 embedding caches",
            "unrelated outputs and caches",
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
