"""Independent artifact and reproducibility audit for Phase B2."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from viirr_retrieval.io_utils import read_jsonl, sha256, write_json
from viirr_retrieval.metrics import validate_metric_invariants


def main() -> None:
    report_dir = ROOT / "reports" / "B2"
    output_dir = ROOT / "outputs" / "B2" / "rankings"
    required = [
        "B2_BASELINE_REPORT.md", "B2_BASELINE_METRICS.json", "B2_FAILURE_ANALYSIS.md",
        "B2_FAILURE_DETAILS.jsonl", "B2_PAGE_DIAGNOSTICS.json", "B2_CANDIDATE_CEILING.json",
        "B2_EXPERIMENT_MANIFEST.json",
    ]
    artifact_presence = {name: (report_dir / name).is_file() and (report_dir / name).stat().st_size > 0 for name in required}
    test_run = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT,
                              text=True, capture_output=True, encoding="utf-8")
    write_json(report_dir / "B2_PYTEST_RESULT.json", {
        "returncode": test_run.returncode, "stdout": test_run.stdout, "stderr": test_run.stderr,
        "pass": test_run.returncode == 0,
    })
    b1 = json.loads((ROOT / "reports" / "B1_INTEGRITY.json").read_text(encoding="utf-8"))
    metrics = json.loads((report_dir / "B2_BASELINE_METRICS.json").read_text(encoding="utf-8"))
    manifest = json.loads((report_dir / "B2_EXPERIMENT_MANIFEST.json").read_text(encoding="utf-8"))
    failures = read_jsonl(report_dir / "B2_FAILURE_DETAILS.jsonl")
    ks = metrics["evidence_k"]
    invariant_pass = True
    try:
        for method in ("bm25", "e5", "hybrid", "page_region"):
            validate_metric_invariants(metrics["overall"][method], ks)
    except AssertionError:
        invariant_pass = False

    rankings_valid = True
    ranking_hashes = {}
    for method in ("bm25", "e5", "hybrid", "page_region"):
        path = output_dir / f"{method}_dev_top200.jsonl"
        rows = read_jsonl(path) if path.exists() else []
        ranking_hashes[method] = sha256(path) if path.exists() else None
        if len(rows) != 93:
            rankings_valid = False
            continue
        for row in rows:
            ids = [result["evidence_id"] for result in row["results"]]
            ranks = [result["rank"] for result in row["results"]]
            if len(ids) > 200 or len(ids) != len(set(ids)) or ranks != list(range(1, len(ranks) + 1)):
                rankings_valid = False
            if any(not {"evidence_id", "doc_id", "page_id", "page_number", "unit_type", "score", "rank"} <= set(result)
                   for result in row["results"]):
                rankings_valid = False

    units = read_jsonl(ROOT / "data" / "processed" / "evidence_units.jsonl")
    forbidden = {"question", "answer", "gold_evidence", "retrieval_evidence_ids", "answer_evidence_ids"}
    no_leakage = all(not (forbidden & set(row)) for row in units)
    candidate = ROOT / "data" / "benchmark" / "candidate_test.jsonl"
    frozen_candidate = ROOT / "data" / "v3_2_final_semantic" / "candidate_test.jsonl"
    candidate_untouched = (
        not manifest["candidate_test_annotations_loaded_by_runner"] and
        not manifest["candidate_test_used_for_evaluation_or_tuning"] and
        manifest["candidate_test_hash_before"] == manifest["candidate_test_hash_after"] ==
        sha256(candidate) == sha256(frozen_candidate)
    )
    reproducibility_path = report_dir / "B2_REPRODUCIBILITY.json"
    reproducibility = (json.loads(reproducibility_path.read_text(encoding="utf-8"))
                       if reproducibility_path.exists() else {"rankings_identical": False})
    gates = {
        "B2_IMPLEMENTATION_COMPLETE": all(artifact_presence.values()),
        "B1_INTEGRITY_PASS": b1["B1_INTEGRITY"] == "PASS",
        "BM25_EXECUTED": "bm25" in ranking_hashes and ranking_hashes["bm25"] is not None,
        "E5_EXECUTED": "e5" in ranking_hashes and ranking_hashes["e5"] is not None,
        "HYBRID_EXECUTED": "hybrid" in ranking_hashes and ranking_hashes["hybrid"] is not None,
        "PAGE_REGION_EXECUTED": "page_region" in ranking_hashes and ranking_hashes["page_region"] is not None,
        "EVALUATION_VALID": invariant_pass and metrics["dev_qa"] == 93,
        "NO_QA_GOLD_INDEX_LEAKAGE": no_leakage,
        "CANDIDATE_TEST_UNTOUCHED": candidate_untouched,
        "FAILURE_DIAGNOSIS_COMPLETE": (report_dir / "B2_FAILURE_ANALYSIS.md").stat().st_size > 0 and len(failures) > 0,
        "REPRODUCIBILITY_PASS": test_run.returncode == 0 and rankings_valid and reproducibility["rankings_identical"],
    }
    valid = all(gates.values())
    blockers = [name for name, passed in gates.items() if not passed]
    audit = {
        "status": "PASS" if valid else "FAIL", "gates": gates,
        "artifact_presence": artifact_presence, "metric_invariants_pass": invariant_pass,
        "rankings_valid": rankings_valid, "ranking_sha256": ranking_hashes,
        "candidate_test_untouched": candidate_untouched, "index_leakage_fields": sorted(forbidden),
        "pytest_pass": test_run.returncode == 0, "human_validated": False,
        "remaining_blockers": blockers,
    }
    readiness = {**gates, "READY_FOR_PHASE_C": valid, "HUMAN_VALIDATED": False,
                 "REMAINING_BLOCKERS": blockers}
    write_json(report_dir / "B2_FINAL_AUDIT.json", audit)
    write_json(report_dir / "B2_READINESS.json", readiness)
    print(json.dumps({"status": audit["status"], "gates": gates,
                      "ready_for_phase_c": valid, "blockers": blockers}, ensure_ascii=False, indent=2))
    if not valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
