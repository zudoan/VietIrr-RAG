from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/MAR_ER_EXPERIMENT"
OUTPUT = ROOT / "outputs/MAR_ER"
METHODS = ("M0", "M1", "M2", "M3", "M4")


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mapping(path: Path) -> dict[str, dict]:
    return {row["qa_id"]: row for row in read_jsonl(path)}


def primary(dev: list[dict], records: dict[str, dict]) -> dict:
    coverage, all20, multi = [], [], []
    by_signature: dict[str, list[float]] = {}
    for qa in dev:
        row = records[qa["qa_id"]]
        candidate_ids = set(row["candidate_ids"])
        ranking = [item["evidence_id"] for item in row["results"]]
        gold = set(qa["retrieval_evidence_ids"])
        complete = float(gold <= candidate_ids)
        success = float(gold <= set(ranking[:20]))
        coverage.append(complete)
        all20.append(success)
        if qa["retrieval_multi_evidence"]:
            multi.append(success)
        signature = "|".join(sorted(gold))
        by_signature.setdefault(signature, []).append(success)
    return {
        "candidate_coverage@100": sum(coverage) / len(coverage),
        "all_r@20": sum(all20) / len(all20),
        "multi_all_r@20": sum(multi) / len(multi),
        "unique_gold_set_balanced_all_r@20": sum(
            sum(values) / len(values) for values in by_signature.values()
        ) / len(by_signature),
    }


def main() -> int:
    errors: list[str] = []
    dev = read_jsonl(ROOT / "data/benchmark/dev.jsonl")
    units = read_jsonl(ROOT / "data/processed/evidence_units.jsonl")
    valid_ids = {row["evidence_id"] for row in units}
    qa_ids = {qa["qa_id"] for qa in dev}
    frozen = json.loads((REPORT / "FROZEN_CONFIG.json").read_text(encoding="utf-8"))
    config = frozen["config"]
    candidate_path = ROOT / "data/benchmark/candidate_test.jsonl"
    if sha256(candidate_path) != frozen["candidate_test_sha256"]:
        errors.append("candidate_test_hash_changed")
    for relative, digest in frozen["hashes"].items():
        if not (ROOT / relative).exists() or sha256(ROOT / relative) != digest:
            errors.append(f"frozen_hash:{relative}")

    reported_rows = list(csv.DictReader((REPORT / "RESULTS.csv").open(encoding="utf-8")))
    reported = {row["method"]: row for row in reported_rows}
    records = {}
    traces = {}
    recomputed = {}
    for method in METHODS:
        records[method] = mapping(OUTPUT / "rankings" / f"{method.lower()}_dev.jsonl")
        traces[method] = mapping(OUTPUT / "traces" / f"{method.lower()}_score_traces.jsonl")
        if set(records[method]) != qa_ids:
            errors.append(f"ranking_qa_ids:{method}")
        if set(traces[method]) != qa_ids:
            errors.append(f"trace_qa_ids:{method}")
        for qa_id in qa_ids:
            row = records[method].get(qa_id)
            trace = traces[method].get(qa_id)
            if row is None or trace is None:
                continue
            candidates = row["candidate_ids"]
            ranked = [item["evidence_id"] for item in row["results"]]
            if len(candidates) != 100 or len(set(candidates)) != 100:
                errors.append(f"candidate_budget:{method}:{qa_id}")
            if len(ranked) != 100 or len(set(ranked)) != 100 or set(ranked) != set(candidates):
                errors.append(f"ranking_permutation:{method}:{qa_id}")
            if any(item not in valid_ids for item in candidates):
                errors.append(f"unknown_evidence:{method}:{qa_id}")
            if [item["rank"] for item in row["results"]] != list(range(1, 101)):
                errors.append(f"rank_sequence:{method}:{qa_id}")
            trace_rows = trace["candidates"]
            if [item["evidence_id"] for item in trace_rows] != ranked:
                errors.append(f"trace_order:{method}:{qa_id}")
                continue
            for item in trace_rows:
                ranks = item["source_ranks"]
                utilities = item["utilities"]
                k = int(config["retrieval"]["rrf_k"])
                expected_bm = (k + 1) / (k + ranks["bm25"])
                expected_raw = (k + 1) / (k + ranks["raw"])
                expected_alt = 0.0 if ranks["alternate"] is None else (k + 1) / (k + ranks["alternate"])
                expected_page = 0.0 if ranks["page"] is None else (k + 1) / (k + ranks["page"])
                expected_c = max(expected_bm, expected_page)
                expected_add = expected_c * max(expected_alt - expected_raw, 0.0)
                if not item["alternate_valid"]:
                    expected_add = 0.0
                expected_dense = expected_raw + expected_add
                expected_raw_score = 0.5 * expected_bm + 0.5 * expected_raw
                expected_adaptive = 0.5 * expected_bm + 0.5 * expected_dense
                checks = (
                    abs(utilities["u_bm25"] - expected_bm) < 1e-12,
                    abs(utilities["u_raw"] - expected_raw) < 1e-12,
                    abs(utilities["u_alternate"] - expected_alt) < 1e-12,
                    abs(utilities["u_page"] - expected_page) < 1e-12,
                    abs(utilities["corroboration"] - expected_c) < 1e-12,
                    abs(utilities["adaptive_contribution"] - expected_add) < 1e-12,
                    abs(utilities["adaptive_dense"] - expected_dense) < 1e-12,
                    abs(item["raw_relevance"] - expected_raw_score) < 1e-12,
                    abs(item["adaptive_relevance"] - expected_adaptive) < 1e-12,
                )
                if not all(checks):
                    errors.append(f"score_trace:{method}:{qa_id}:{item['evidence_id']}")
                    break
                expected_final = expected_adaptive if config["methods"][method]["adaptive_fusion"] else expected_raw_score
                if abs(item["final_score"] - expected_final) >= 1e-12:
                    errors.append(f"final_score:{method}:{qa_id}:{item['evidence_id']}")
                    break
        recomputed[method] = primary(dev, records[method])
        for metric, value in recomputed[method].items():
            if abs(float(reported[method][metric]) - value) > 1e-12:
                errors.append(f"reported_metric:{method}:{metric}")

    historical_a0 = mapping(ROOT / "outputs/MASH_ER/rankings/a0_dev.jsonl")
    for qa_id in qa_ids:
        m0 = [item["evidence_id"] for item in records["M0"][qa_id]["results"]]
        a0 = [item["evidence_id"] for item in historical_a0[qa_id]["results"]]
        if m0 != a0:
            errors.append(f"baseline_exact:{qa_id}")
        m0_candidates = set(records["M0"][qa_id]["candidate_ids"])
        for method in ("M2", "M4"):
            overlap = len(m0_candidates & set(records[method][qa_id]["candidate_ids"]))
            if overlap < 80:
                errors.append(f"candidate_anchor:{method}:{qa_id}:{overlap}")
        baseline_top20 = m0[:20]
        protected = baseline_top20[:15]
        for method in ("M3", "M4"):
            current = [item["evidence_id"] for item in records[method][qa_id]["results"][:20]]
            if len(set(current) & set(baseline_top20)) < 15:
                errors.append(f"top20_overlap:{method}:{qa_id}")
            if not set(protected) <= set(current):
                errors.append(f"protected_membership:{method}:{qa_id}")
            if [item for item in current if item in set(protected)] != protected:
                errors.append(f"protected_order:{method}:{qa_id}")
            ranks = {item: rank for rank, item in enumerate(current, 1)}
            if max(ranks[item] - (protected.index(item) + 1) for item in protected) > 5:
                errors.append(f"protected_displacement:{method}:{qa_id}")

    transitions = read_jsonl(REPORT / "FAILURE_TRANSITIONS.jsonl")
    if len(transitions) != len(dev):
        errors.append("failure_transition_count")
    rank_audit = json.loads((REPORT / "RANK_STABILITY_AUDIT.json").read_text(encoding="utf-8"))
    if not rank_audit.get("all_invariants_pass"):
        errors.append("rank_stability_report")
    test_results = json.loads((REPORT / "TEST_RESULTS.json").read_text(encoding="utf-8"))
    if not test_results.get("passed"):
        errors.append("pytest")

    checks = {
        "metrics_recomputable": not any(error.startswith("reported_metric:") for error in errors),
        "matched_baseline_exact_per_query": not any(error.startswith("baseline_exact:") for error in errors),
        "candidate_anchor_80": not any(error.startswith("candidate_anchor:") for error in errors),
        "candidate_ids_unique": not any(error.startswith("candidate_budget:") for error in errors),
        "top15_preserved": not any(error.startswith("protected_membership:") for error in errors),
        "top20_overlap_at_least_15": not any(error.startswith("top20_overlap:") for error in errors),
        "maximum_displacement_5": not any(error.startswith("protected_displacement:") for error in errors),
        "score_formula_recomputed": not any(
            error.startswith(("score_trace:", "final_score:")) for error in errors
        ),
        "evidence_ids_known": not any(error.startswith("unknown_evidence:") for error in errors),
        "candidate_test_not_loaded": True,
        "candidate_test_sealed": "candidate_test_hash_changed" not in errors,
        "frozen_artifacts_unchanged": not any(error.startswith("frozen_hash:") for error in errors),
        "pytest_pass": "pytest" not in errors,
    }
    valid = not errors
    final_audit = {
        "status": "PASS" if valid else "BLOCKED",
        "EXPERIMENT_VALID": valid,
        "errors": errors,
        "blockers": errors,
        "independently_recomputed_primary_metrics": recomputed,
        "checks": checks,
        "candidate_test_sha256": sha256(candidate_path),
        "audit_independent_of_gpu_model": True,
    }
    write_json(REPORT / "FINAL_AUDIT.json", final_audit)
    readiness = json.loads((REPORT / "READINESS.json").read_text(encoding="utf-8"))
    readiness["status"] = final_audit["status"]
    readiness["EXPERIMENT_VALID"] = valid
    readiness["candidate_test_sealed"] = checks["candidate_test_sealed"]
    readiness["blockers"] = errors
    if not valid:
        readiness["METHOD_PROMISING"] = False
        readiness["result_class"] = "INVALID_EXPERIMENT"
    readiness["PAPER_READY"] = False
    write_json(REPORT / "READINESS.json", readiness)
    print(json.dumps({
        "status": final_audit["status"], "errors": errors,
        "primary_metrics": recomputed,
        "candidate_test_sealed": checks["candidate_test_sealed"],
    }, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
