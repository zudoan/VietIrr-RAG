from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "r1.1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(files: set[Path], relative: str) -> None:
    path = ROOT / relative
    if not path.is_file():
        raise FileNotFoundError(f"Required packaging input is missing: {relative}")
    files.add(path)


def main() -> None:
    if DEST.exists():
        raise FileExistsError(f"Destination exists; refusing to overwrite: {DEST}")

    files: set[Path] = set()
    required = [
        "pyproject.toml",
        "configs/phase_b.json",
        "configs/r1.json",
        "configs/mash_er.json",
        "scripts/run_mash_er.py",
        "scripts/audit_mash_er.py",
        "scripts/package_r1_1.py",
        "tests/test_mash_er.py",
        "data/benchmark/dev.jsonl",
        "data/processed/evidence_units.jsonl",
        "data/parsed/documents.jsonl",
        "data/parsed/pages.jsonl",
        "data/parsed/regions.jsonl",
        "data/parsed/tables.jsonl",
        "outputs/B2/cache/bm25_regions.pkl",
        "outputs/B2_1/rankings/p0_pages_dev_top100.jsonl",
        "outputs/C1/candidates/g0_b100_dev.jsonl",
        "outputs/C1/rankings/e0_g0_global_rrf_dev.jsonl",
        "outputs/R1/rankings/full_retrieval_r0_dev.jsonl",
        "outputs/R1/cache/CACHE_MANIFEST.json",
        "outputs/R1/cache/r0_window_embeddings.json",
        "outputs/R1/cache/r1_window_embeddings.json",
        "outputs/R1/windows/r0_window_map.jsonl",
        "outputs/R1/windows/r1_window_map.jsonl",
        "reports/R1/RESULTS.csv",
        "reports/R1/REPRESENTATION_AUDIT.json",
        "reports/R1/FINAL_AUDIT.json",
        "reports/R1/READINESS.json",
        "reports/C1_2/BASELINE_VERIFICATION.json",
        "reports/C1_2/MISSING_MULTI_DIAGNOSIS.jsonl",
    ]
    for relative in required:
        require(files, relative)

    for path in (ROOT / "src/viirr_retrieval").glob("*.py"):
        files.add(path)
    for path in (ROOT / "data/parsed").glob("*.json"):
        files.add(path)
    for directory in (ROOT / "reports/MASH_ER", ROOT / "outputs/MASH_ER"):
        for path in directory.rglob("*"):
            if path.is_file():
                files.add(path)

    copied = []
    for source in sorted(files, key=lambda path: path.relative_to(ROOT).as_posix()):
        relative = source.relative_to(ROOT)
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append({
            "path": relative.as_posix(),
            "bytes": target.stat().st_size,
            "sha256": sha256(target),
        })

    excluded_large = []
    for relative in (
        "outputs/R1/cache/r0_window_embeddings.npy",
        "outputs/R1/cache/r1_window_embeddings.npy",
    ):
        source = ROOT / relative
        require(set(), relative)
        excluded_large.append({
            "path": relative,
            "bytes": source.stat().st_size,
            "sha256": sha256(source),
            "reason": "Large upstream R1 cache; metadata and window maps are included.",
        })

    candidate_test = ROOT / "data/benchmark/candidate_test.jsonl"
    readme = """# VietIrr-RAG R1.1 / MASH-ER review package

This is a copy-only package. No source workspace file was moved or deleted.

Included:
- MASH-ER implementation, configuration, runner, audit, and tests.
- All MASH-ER reports, A0-A3 rankings, score traces, view manifests, cache metadata, and TABLE_STRUCT embeddings.
- Dev-only benchmark inputs and parsed/processed evidence needed for inspection.
- Selected B2/C1/R1 baseline artifacts and metadata used by the experiment.

Excluded:
- Candidate Test content; it remains sealed and is represented only by a byte hash in the package manifest.
- Two large upstream R1 embedding arrays. Their paths, sizes, and SHA-256 hashes are recorded in the manifest.
- Environments, model downloads, unrelated phases, and temporary files.

Verified final state:
- 93 Dev QA; 25 retrieval-multi; 45 unique gold sets.
- A0 Coverage/All R@20/Multi All R@20: 0.7742 / 0.6237 / 0.6000.
- A3 Coverage/All R@20/Multi All R@20: 0.8602 / 0.4731 / 0.5600.
- 93 tests passed; independent audit passed; Candidate Test remained sealed.
- EXPERIMENT_VALID=true, METHOD_PROMISING=false, PAPER_READY=false.
"""
    readme_path = DEST / "README.md"
    readme_path.write_text(readme, encoding="utf-8", newline="\n")
    copied.append({
        "path": "README.md",
        "bytes": readme_path.stat().st_size,
        "sha256": sha256(readme_path),
    })

    manifest = {
        "package": "VietIrr-RAG R1.1 / MASH-ER",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "copy_only": True,
        "source_workspace": str(ROOT),
        "source_files_preserved": True,
        "candidate_test_included": False,
        "candidate_test_sha256": sha256(candidate_test),
        "upstream_r1_embedding_arrays_copied": False,
        "file_count_excluding_manifest": len(copied),
        "total_copied_bytes_excluding_manifest": sum(int(row["bytes"]) for row in copied),
        "files": copied,
        "excluded_large_artifacts": excluded_large,
    }
    (DEST / "PACKAGE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "destination": str(DEST),
        "files_excluding_manifest": len(copied),
        "copied_mb_excluding_manifest": round(
            manifest["total_copied_bytes_excluding_manifest"] / (1024 * 1024), 2
        ),
        "excluded_large_arrays": len(excluded_large),
    }))


if __name__ == "__main__":
    main()
