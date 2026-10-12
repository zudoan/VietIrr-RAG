from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from viirr_retrieval.io_utils import sha256, write_json


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/MAR_ER_EXPERIMENT"
BUNDLE = ROOT / "MAR_ER_REVIEW_BUNDLE.zip"


def main() -> int:
    if BUNDLE.exists():
        raise SystemExit("One-shot guard: MAR_ER_REVIEW_BUNDLE.zip already exists")
    readiness = json.loads((REPORT / "READINESS.json").read_text(encoding="utf-8"))
    final_audit = json.loads((REPORT / "FINAL_AUDIT.json").read_text(encoding="utf-8"))
    if not readiness.get("EXPERIMENT_VALID") or final_audit.get("status") != "PASS":
        raise SystemExit("Refusing review bundle because independent audit did not pass")

    files: set[Path] = {
        ROOT / "pyproject.toml",
        ROOT / "configs/mar_er.json",
        ROOT / "data/benchmark/dev.jsonl",
        ROOT / "src/viirr_retrieval/mar_er.py",
        ROOT / "tests/test_mar_er.py",
        ROOT / "scripts/preflight_mar_er.py",
        ROOT / "scripts/run_mar_er.py",
        ROOT / "scripts/audit_mar_er.py",
        ROOT / "scripts/recompute_mar_er_metrics.py",
        ROOT / "scripts/package_mar_er.py",
        ROOT / "outputs/MASH_ER/rankings/a0_dev.jsonl",
        ROOT / "reports/MASH_ER/BASELINE_VERIFICATION.json",
        ROOT / "reports/MASH_ER/RESULTS.csv",
        ROOT / "reports/R1/RESULTS.csv",
        ROOT / "reports/C1/C1_RESULTS.csv",
    }
    files.update((ROOT / "reports/MAR_ER_DESIGN").glob("*.md"))
    files.update(path for path in REPORT.iterdir() if path.is_file()
                 and path.name != "ARTIFACT_MANIFEST.json")
    files.update((ROOT / "outputs/MAR_ER/rankings").glob("*.jsonl"))
    files.update((ROOT / "outputs/MAR_ER/traces").glob("*.jsonl"))
    files.update((ROOT / "outputs/MAR_ER/metadata").glob("*.jsonl"))
    missing = [path for path in files if not path.exists()]
    if missing:
        raise SystemExit(f"Missing bundle inputs: {missing}")

    cache_paths = [
        ROOT / "outputs/R1/cache/r0_window_embeddings.npy",
        ROOT / "outputs/R1/cache/r1_window_embeddings.npy",
        ROOT / "outputs/MASH_ER/cache/table_struct_window_embeddings.npy",
        ROOT / "outputs/B2/cache/bm25_regions.pkl",
    ]
    manifest = {
        "package": "MAR-ER one-shot review bundle",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Recompute primary Dev metrics and inspect frozen method without GPU/model loading.",
        "experiment_valid": readiness["EXPERIMENT_VALID"],
        "method_promising": readiness["METHOD_PROMISING"],
        "paper_ready": False,
        "candidate_test_included": False,
        "candidate_test_sha256": final_audit["candidate_test_sha256"],
        "full_corpus_included": False,
        "embedding_caches_included": False,
        "recompute_command": "python scripts/recompute_mar_er_metrics.py",
        "included_files": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())
        ],
        "excluded_large_cache_references": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in cache_paths
        ],
        "scientific_limits": [
            "Dev-only exploratory result.",
            "Candidate Test remained sealed and is not in the bundle.",
            "Only eight unique multi-evidence gold signatures.",
            "PAPER_READY is fixed false for this round.",
        ],
    }
    write_json(REPORT / "ARTIFACT_MANIFEST.json", manifest)
    files.add(REPORT / "ARTIFACT_MANIFEST.json")
    with zipfile.ZipFile(BUNDLE, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for path in sorted(files, key=lambda item: item.relative_to(ROOT).as_posix()):
            archive.write(path, path.relative_to(ROOT).as_posix())
    print(json.dumps({
        "bundle": BUNDLE.name,
        "bytes": BUNDLE.stat().st_size,
        "sha256": sha256(BUNDLE),
        "file_count": len(files),
        "candidate_test_included": False,
        "embedding_caches_included": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
