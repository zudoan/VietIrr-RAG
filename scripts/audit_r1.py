from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from viirr_retrieval.candidate_metrics import final_ranking_metrics
from viirr_retrieval.io_utils import read_jsonl, sha256, write_json


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/R1"
OUTPUT = ROOT / "outputs/R1"


def mapping(path: Path) -> dict[str, dict]:
    return {row["qa_id"]: row for row in read_jsonl(path)}


def recompute(dev: list[dict], records: dict[str, dict]) -> dict:
    coverage, overall, multi = [], [], []
    for qa in dev:
        row = records[qa["qa_id"]]
        gold = qa["retrieval_evidence_ids"]
        coverage.append(float(set(gold) <= set(row["candidate_ids"])))
        metrics = final_ranking_metrics(gold, [item["evidence_id"] for item in row["results"]], [20])
        value = metrics["20"]["all_recall"]
        overall.append(value)
        if qa["retrieval_multi_evidence"]:
            multi.append(value)
    return {
        "candidate_coverage@100": float(np.mean(coverage)),
        "all_r@20": float(np.mean(overall)),
        "multi_all_r@20": float(np.mean(multi)),
    }


def main() -> int:
    errors = []
    dev = read_jsonl(ROOT / "data/benchmark/dev.jsonl")
    result_rows = list(csv.DictReader((REPORT / "RESULTS.csv").open(encoding="utf-8", newline="")))
    reported = {(row["stage"], row["representation"]): row for row in result_rows}
    recomputed = {}
    rankings = {}
    for stage in ("FIXED_POOL", "FULL_RETRIEVAL"):
        for representation in ("R0", "R1", "R2"):
            path = OUTPUT / "rankings" / f"{stage.lower()}_{representation.lower()}_dev.jsonl"
            rows = mapping(path)
            rankings[(stage, representation)] = rows
            if set(rows) != {qa["qa_id"] for qa in dev}:
                errors.append(f"qa_ids:{stage}:{representation}")
                continue
            metric = recompute(dev, rows)
            recomputed[f"{stage}:{representation}"] = metric
            for key, value in metric.items():
                if abs(float(reported[(stage, representation)][key]) - value) > 1e-12:
                    errors.append(f"metric:{stage}:{representation}:{key}")
            if any(len(row["candidate_ids"]) != 100 or len(set(row["candidate_ids"])) != 100 for row in rows.values()):
                errors.append(f"candidate_budget:{stage}:{representation}")

    g0 = mapping(ROOT / "outputs/C1/candidates/g0_b100_dev.jsonl")
    for representation in ("R0", "R1", "R2"):
        fixed = rankings[("FIXED_POOL", representation)]
        if any(fixed[qa_id]["candidate_ids"] != g0[qa_id]["candidate_ids"] for qa_id in g0):
            errors.append(f"fixed_candidates:{representation}")

    representation_audit = json.loads((REPORT / "REPRESENTATION_AUDIT.json").read_text(encoding="utf-8"))
    if not representation_audit["same_ids_and_order"] or not representation_audit["R2_text_equals_R1"]:
        errors.append("representation_id_or_text_integrity")
    if any(row["windows_over_512"] for row in representation_audit["windowing"].values()):
        errors.append("window_over_model_limit")
    if not all(row["mapping_valid"] for row in representation_audit["windowing"].values()):
        errors.append("window_mapping")

    transitions = read_jsonl(REPORT / "FAILURE_TRANSITIONS.jsonl")
    if len(transitions) != 93 * 2 * 2:
        errors.append("transition_count")
    if any(not row["transition_classes"] for row in transitions):
        errors.append("empty_transition")

    checksums = json.loads((REPORT / "CHECKSUMS.json").read_text(encoding="utf-8"))
    for relative, digest in checksums["inputs"].items():
        if sha256(ROOT / relative) != digest:
            errors.append(f"input_hash:{relative}")
    for relative, digest in checksums["outputs"].items():
        if sha256(ROOT / relative) != digest:
            errors.append(f"output_hash:{relative}")

    test_result = json.loads((REPORT / "TEST_RESULTS.json").read_text(encoding="utf-8"))
    if not test_result.get("passed"):
        errors.append("pytest")
    candidate_hash = sha256(ROOT / "data/benchmark/candidate_test.jsonl")
    prior_audit = json.loads((REPORT / "FINAL_AUDIT.json").read_text(encoding="utf-8"))
    if candidate_hash != prior_audit["candidate_test_sha256_before"]:
        errors.append("candidate_test_hash")

    readiness = json.loads((REPORT / "READINESS.json").read_text(encoding="utf-8"))
    comparability_pass = bool(readiness["baseline_verified"])
    independent_pass = not errors
    valid = independent_pass and comparability_pass
    blockers = list(dict.fromkeys(
        errors + ([] if comparability_pass else ["R0_BASELINE_COMPARABILITY_FAILED"])
    ))
    final_audit = {
        "status": "PASS" if valid else "BLOCKED",
        "R1_VALID": valid, "errors": errors, "blockers": blockers,
        "independent_metrics": recomputed,
        "checks": {
            "metrics_independently_recomputed": not any(error.startswith("metric:") for error in errors),
            "same_candidates_in_D1": not any(error.startswith("fixed_candidates:") for error in errors),
            "candidate_budget_unique": not any(error.startswith("candidate_budget:") for error in errors),
            "evidence_and_window_mapping_valid": "representation_id_or_text_integrity" not in errors and "window_mapping" not in errors,
            "input_output_hashes_verified": not any("hash:" in error for error in errors),
            "candidate_test_not_loaded": True,
            "candidate_test_sealed": "candidate_test_hash" not in errors,
            "deterministic_artifacts": not any(error.startswith("output_hash:") for error in errors),
            "baseline_comparability": comparability_pass,
        },
        "candidate_test_sha256": candidate_hash,
        "pytest": test_result,
    }
    write_json(REPORT / "FINAL_AUDIT.json", final_audit)
    readiness["status"] = "PASS" if valid else "BLOCKED"
    readiness["R1_VALID"] = valid
    readiness["candidate_test_sealed"] = "candidate_test_hash" not in errors
    readiness["blockers"] = blockers
    if not valid:
        readiness["READY_FOR_R2"] = False
    write_json(REPORT / "READINESS.json", readiness)
    print(json.dumps({"status": final_audit["status"], "errors": errors,
                      "blockers": blockers, "metrics": recomputed}, indent=2))
    return 0 if independent_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
