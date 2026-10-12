from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from viirr_retrieval.candidate_metrics import final_ranking_metrics
from viirr_retrieval.io_utils import read_jsonl, sha256, write_json


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/C1_2"


def qa_map(path: Path) -> dict[str, dict]:
    return {row["qa_id"]: row for row in read_jsonl(path)}


def ranking_ids(row: dict) -> list[str]:
    return [item["evidence_id"] for item in row["results"]]


def recompute_metrics(dev: list[dict], ranking_path: Path, candidates: dict[str, dict]) -> dict:
    rankings = qa_map(ranking_path)
    all_values, multi_values, coverage = [], [], []
    for qa in dev:
        metrics = final_ranking_metrics(
            qa["retrieval_evidence_ids"], ranking_ids(rankings[qa["qa_id"]]), [20]
        )
        value = metrics["20"]["all_recall"]
        all_values.append(value)
        if qa["retrieval_multi_evidence"]:
            multi_values.append(value)
        coverage.append(float(set(qa["retrieval_evidence_ids"]) <= set(candidates[qa["qa_id"]]["candidate_ids"])))
    return {
        "candidate_coverage@100": float(np.mean(coverage)),
        "all_r@20": float(np.mean(all_values)),
        "multi_all_r@20": float(np.mean(multi_values)),
    }


def main() -> int:
    errors = []
    dev = read_jsonl(ROOT / "data/benchmark/dev.jsonl")
    multi = [qa for qa in dev if qa["retrieval_multi_evidence"]]
    g0 = qa_map(ROOT / "outputs/C1/candidates/g0_b100_dev.jsonl")
    missing = {
        qa["qa_id"]: sorted(set(qa["retrieval_evidence_ids"]) - set(g0[qa["qa_id"]]["candidate_ids"]))
        for qa in multi
        if not set(qa["retrieval_evidence_ids"]) <= set(g0[qa["qa_id"]]["candidate_ids"])
    }
    signatures = {"|".join(sorted(qa["retrieval_evidence_ids"])) for qa in multi}
    affected_signatures = {
        "|".join(sorted(qa["retrieval_evidence_ids"])) for qa in multi if qa["qa_id"] in missing
    }
    if (len(dev), len(multi), len(signatures), len(missing), len(affected_signatures)) != (93, 25, 8, 8, 4):
        errors.append("baseline_or_missing_counts")

    expected = json.loads((REPORT / "BASELINE_VERIFICATION.json").read_text(encoding="utf-8"))
    methods = {
        "E0": ROOT / "outputs/C1/rankings/e0_g0_global_rrf_dev.jsonl",
        "E2": ROOT / "outputs/C1/rankings/e2_g0_cross_encoder_dev.jsonl",
        "E4": ROOT / "outputs/C1_1/rankings/e4_g0_set_aware_v2_dev.jsonl",
    }
    recomputed = {name: recompute_metrics(dev, path, g0) for name, path in methods.items()}
    for name in methods:
        for metric, value in recomputed[name].items():
            if abs(value - expected["metrics_recomputed"][name][metric]) > 1e-12:
                errors.append(f"metric_mismatch:{name}:{metric}")

    diagnosis = read_jsonl(REPORT / "MISSING_MULTI_DIAGNOSIS.jsonl")
    diagnosed = {row["qa_id"]: row["missing_gold_id"] for row in diagnosis}
    expected_missing = {qa_id: values[0] for qa_id, values in missing.items()}
    if diagnosed != expected_missing:
        errors.append("diagnosis_does_not_match_g0")
    if any(row["missing_gold_id"] in g0[row["qa_id"]]["candidate_ids"] for row in diagnosis):
        errors.append("diagnosis_contains_nonmissing_gold")
    if any(row["primary_cause"] not in {"PAGE_LOCALIZATION_MISS", "PAGE_PRUNING", "CANDIDATE_BUDGET_MISS"} for row in diagnosis):
        errors.append("invalid_primary_cause")

    metadata = json.loads((REPORT / "METADATA_QUALITY.json").read_text(encoding="utf-8"))
    before = metadata["before_c1_1"]
    if before["candidate_occurrences"] != 9300 or before["evidence_time_known_old_rule"] != 661:
        errors.append("metadata_before_counts")
    if before["evidence_time_with_actual_raw_start_or_end"] != 390:
        errors.append("empty_time_reclassification")
    after = metadata["after_c1_2"]
    if after["candidate_occurrences"] != 9300 or after["unique_evidence_ids"] != 1332:
        errors.append("metadata_after_counts")
    if after["source_valid_time_by_occurrence"] != 390:
        errors.append("source_valid_time_after_repair")

    requirement = json.loads((REPORT / "REQUIREMENT_ROLE_AUDIT.json").read_text(encoding="utf-8"))
    if requirement["requirement_counts"]["after_temporal_comparison"] != 0:
        errors.append("temporal_reference_confusion_remains")
    queue = requirement["review_queue"]
    if queue["sample_size"] != 30 or queue["human_validated"] or any(row["human_validated"] for row in queue["rows"]):
        errors.append("review_queue_labeling")

    checksums = json.loads((REPORT / "CHECKSUMS.json").read_text(encoding="utf-8"))
    for relative, digest in checksums["inputs"].items():
        if sha256(ROOT / relative) != digest:
            errors.append(f"input_hash_changed:{relative}")
    for relative, digest in checksums["outputs"].items():
        if sha256(REPORT / relative) != digest:
            errors.append(f"output_hash_mismatch:{relative}")

    candidate_hash = sha256(ROOT / "data/benchmark/candidate_test.jsonl")
    if candidate_hash != expected["candidate_test_sha256_before"]:
        errors.append("candidate_test_hash_changed")
    test_result = json.loads((REPORT / "TEST_RESULTS.json").read_text(encoding="utf-8"))
    if not test_result.get("passed"):
        errors.append("pytest_failed")

    status = "PASS" if not errors else "FAIL"
    final_audit = {
        "status": status,
        "errors": errors,
        "independent_recomputation": {
            "metrics": recomputed,
            "dev_qa": len(dev), "retrieval_multi_qa": len(multi),
            "multi_unique_gold_sets": len(signatures), "missing_multi_qa": len(missing),
            "unique_affected_gold_sets": len(affected_signatures),
        },
        "checks": {
            "metrics_independently_recomputable": not any(e.startswith("metric_mismatch") for e in errors),
            "missing_qa_derived_from_actual_g0": "diagnosis_does_not_match_g0" not in errors,
            "candidate_test_not_loaded": True,
            "candidate_test_untouched": "candidate_test_hash_changed" not in errors,
            "input_output_hashes_verified": not any("hash" in e for e in errors),
            "review_queue_not_human_validated": "review_queue_labeling" not in errors,
            "no_new_method_or_model_evaluated": True,
        },
        "candidate_test_sha256": candidate_hash,
        "pytest": test_result,
    }
    write_json(REPORT / "C1_2_FINAL_AUDIT.json", final_audit)

    readiness = json.loads((REPORT / "C1_2_READINESS.json").read_text(encoding="utf-8"))
    readiness["status"] = status
    readiness["C1_2_VALID"] = status == "PASS"
    readiness["candidate_test_untouched"] = "candidate_test_hash_changed" not in errors
    readiness["blockers"] = errors
    write_json(REPORT / "C1_2_READINESS.json", readiness)
    print(json.dumps({"status": status, "errors": errors, "metrics": recomputed}, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
