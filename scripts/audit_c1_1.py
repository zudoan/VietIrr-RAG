from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from viirr_retrieval.candidate_metrics import final_ranking_metrics
from viirr_retrieval.io_utils import read_jsonl, sha256, write_json


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/C1_1"
OUTPUT_DIR = ROOT / "outputs/C1_1"


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def main() -> int:
    errors: list[str] = []
    dev = read_jsonl(ROOT / "data/benchmark/dev.jsonl")
    dev_by_id = {row["qa_id"]: row for row in dev}
    g0 = {row["qa_id"]: row for row in read_jsonl(ROOT / "outputs/C1/candidates/g0_b100_dev.jsonl")}
    rankings = {
        "E0": {row["qa_id"]: row for row in read_jsonl(
            ROOT / "outputs/C1/rankings/e0_g0_global_rrf_dev.jsonl")},
        "E2": {row["qa_id"]: row for row in read_jsonl(
            ROOT / "outputs/C1/rankings/e2_g0_cross_encoder_dev.jsonl")},
        "E3": {row["qa_id"]: row for row in read_jsonl(
            ROOT / "outputs/C1/rankings/e3_g0_set_aware_dev.jsonl")},
        "E4": {row["qa_id"]: row for row in read_jsonl(
            OUTPUT_DIR / "rankings/e4_g0_set_aware_v2_dev.jsonl")},
    }
    traces = {row["qa_id"]: row for row in read_jsonl(
        OUTPUT_DIR / "traces/e4_set_aware_v2_traces.jsonl")}
    representations = {row["qa_id"]: row for row in read_jsonl(
        OUTPUT_DIR / "representations/e4_candidate_representations_dev.jsonl")}
    expected = set(dev_by_id)
    if len(dev) != 93 or set(g0) != expected or set(traces) != expected or set(representations) != expected \
            or any(set(rows) != expected for rows in rankings.values()):
        errors.append("artifact QA IDs do not exactly match 93-row DEV")

    audit = json.loads((REPORT_DIR / "C1_1_FINAL_AUDIT.json").read_text(encoding="utf-8"))
    candidate_hash = sha256(ROOT / "data/benchmark/candidate_test.jsonl")
    if candidate_hash != audit.get("candidate_test_sha256_before"):
        errors.append("Candidate Test hash changed")

    recomputed = {}
    for method, rows in rankings.items():
        per_query = []
        for qa_id, qa in dev_by_id.items():
            pool = g0[qa_id]["candidate_ids"]
            row = rows[qa_id]
            if row["candidate_ids"] != pool:
                errors.append(f"{method}/{qa_id}: candidate pool differs from G0")
            ids = [result["evidence_id"] for result in row["results"]]
            if len(ids) != len(set(ids)) or not set(ids) <= set(pool):
                errors.append(f"{method}/{qa_id}: invalid result IDs")
            if method == "E4" and len(ids) > 20:
                errors.append(f"E4/{qa_id}: selection exceeds 20")
            gold = set(qa["retrieval_evidence_ids"])
            candidate_complete = float(gold <= set(pool))
            metrics = final_ranking_metrics(qa["retrieval_evidence_ids"], ids, [10, 20])
            if metrics["20"]["all_recall"] > candidate_complete:
                errors.append(f"{method}/{qa_id}: All R@20 exceeds candidate coverage")
            per_query.append({"qa_id": qa_id, "candidate": candidate_complete, "metrics": metrics})
        multi = [row for row in per_query if dev_by_id[row["qa_id"]]["retrieval_evidence_count"] >= 2]
        recomputed[method] = {
            "candidate_coverage@100": mean([row["candidate"] for row in per_query]),
            "all_r@20": mean([row["metrics"]["20"]["all_recall"] for row in per_query]),
            "multi_all_r@20": mean([row["metrics"]["20"]["all_recall"] for row in multi]),
        }

    with (REPORT_DIR / "C1_1_RESULTS.csv").open(encoding="utf-8", newline="") as handle:
        reported = {row["method"]: row for row in csv.DictReader(handle)}
    for method, metrics in recomputed.items():
        for key, value in metrics.items():
            if abs(float(reported[method][key]) - value) > 1e-12:
                errors.append(f"{method}: {key} report mismatch")

    regression_rows = read_jsonl(REPORT_DIR / "RANK_REGRESSION_DIAGNOSIS.jsonl")
    if len(regression_rows) != 13:
        errors.append(f"Expected 13 G1 regression diagnoses, found {len(regression_rows)}")
    if any(not row["gold_fusion_scores_unchanged"] for row in regression_rows):
        errors.append("G1 diagnosis reports an unexpected fusion-score change")
    requirement_audit = json.loads((REPORT_DIR / "REQUIREMENT_AUDIT.json").read_text(encoding="utf-8"))
    if requirement_audit["manual_review_queue"]["sample_count"] != 30:
        errors.append("Requirement review queue is not 30 QA")
    if requirement_audit["manual_review_queue"]["human_validated"]:
        errors.append("Unreviewed queue incorrectly marked human validated")
    for qa_id, trace in traces.items():
        if trace["requirement_prediction"]["status"] == "UNCERTAIN":
            e0_ids = [row["evidence_id"] for row in rankings["E0"][qa_id]["results"][:20]]
            if trace["final_selected_evidence_ids"] != e0_ids:
                errors.append(f"{qa_id}: uncertain requirement did not fall back exactly")

    checksum_errors = []
    checksums = json.loads((REPORT_DIR / "CHECKSUMS.json").read_text(encoding="utf-8"))
    mutable = {
        "reports/C1_1/C1_1_FINAL_AUDIT.json", "reports/C1_1/C1_1_READINESS.json",
        "reports/C1_1/C1_1_REPORT.md",
    }
    for entry in checksums["files"]:
        if entry["path"] in mutable:
            continue
        path = ROOT / entry["path"]
        if not path.is_file() or path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
            checksum_errors.append(entry["path"])
    errors.extend(f"checksum mismatch: {value}" for value in checksum_errors)

    audit["artifact_recomputation"] = {
        "status": "PASS" if not errors else "FAIL", "tolerance": 1e-12,
        "metrics": recomputed, "errors": errors,
    }
    audit["checks"]["metrics_independently_recomputed"] = not errors
    audit["checks"]["checksums_verified_before_independent_audit"] = not checksum_errors
    audit["checks"]["regression_diagnosis_recomputed"] = len(regression_rows) == 13
    audit["status"] = "PASS" if all(audit["checks"].values()) and not errors else "FAIL"
    audit["remaining_blockers"] = [name for name, passed in audit["checks"].items() if not passed]
    audit["remaining_blockers"].extend(errors)
    write_json(REPORT_DIR / "C1_1_FINAL_AUDIT.json", audit)

    readiness = json.loads((REPORT_DIR / "C1_1_READINESS.json").read_text(encoding="utf-8"))
    readiness["C1_1_VALID"] = audit["status"] == "PASS"
    readiness["status"] = audit["status"]
    readiness["remaining_blockers"] = audit["remaining_blockers"]
    readiness["READY_FOR_C2"] = bool(readiness["C1_1_VALID"] and readiness["EVIDENCE_SET_SELECTION_PROMISING"])
    write_json(REPORT_DIR / "C1_1_READINESS.json", readiness)

    paths = [path for path in sorted(REPORT_DIR.glob("*"))
             if path.is_file() and path.name != "CHECKSUMS.json"]
    paths.extend(path for path in sorted(OUTPUT_DIR.rglob("*")) if path.is_file())
    paths.append(ROOT / "configs/phase_c1_1.json")
    write_json(REPORT_DIR / "CHECKSUMS.json", {
        "files": [{"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
                   "sha256": sha256(path)} for path in paths]
    })
    print(json.dumps({"status": audit["status"], "errors": errors, "metrics": recomputed}, indent=2))
    return 0 if audit["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
