from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from viirr_retrieval.candidate_metrics import final_ranking_metrics
from viirr_retrieval.io_utils import read_jsonl, sha256, write_json


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/C1"
OUTPUT_DIR = ROOT / "outputs/C1"
RANKINGS = {
    "E0": "e0_g0_global_rrf_dev.jsonl",
    "E1": "e1_g1_global_rrf_dev.jsonl",
    "E2": "e2_g0_cross_encoder_dev.jsonl",
    "E3": "e3_g0_set_aware_dev.jsonl",
}


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def main() -> int:
    errors: list[str] = []
    dev = read_jsonl(ROOT / "data/benchmark/dev.jsonl")
    dev_by_id = {row["qa_id"]: row for row in dev}
    candidates = {
        "G0": {row["qa_id"]: row for row in read_jsonl(OUTPUT_DIR / "candidates/g0_b100_dev.jsonl")},
        "G1": {row["qa_id"]: row for row in read_jsonl(OUTPUT_DIR / "candidates/g1_b100_dev.jsonl")},
    }
    rankings = {
        name: {row["qa_id"]: row for row in read_jsonl(OUTPUT_DIR / "rankings" / filename)}
        for name, filename in RANKINGS.items()
    }
    expected_ids = set(dev_by_id)
    if len(dev) != 93 or any(set(rows) != expected_ids for rows in (*candidates.values(), *rankings.values())):
        errors.append("artifact QA IDs do not exactly match 93-row DEV")

    existing = json.loads((REPORT_DIR / "C1_AUDIT.json").read_text(encoding="utf-8"))
    candidate_hash = sha256(ROOT / "data/benchmark/candidate_test.jsonl")
    if candidate_hash != existing.get("candidate_test_sha256_before"):
        errors.append("Candidate Test hash changed")

    recomputed: dict[str, dict] = {}
    for experiment, rows in rankings.items():
        candidate_key = "G1" if experiment == "E1" else "G0"
        per_query = []
        for qa_id, qa in dev_by_id.items():
            row = rows[qa_id]
            pool = candidates[candidate_key][qa_id]["candidate_ids"]
            result_ids = [item["evidence_id"] for item in row["results"]]
            if len(pool) != len(set(pool)) or len(pool) > 100:
                errors.append(f"{experiment}/{qa_id}: invalid candidate pool")
            if not set(result_ids) <= set(pool):
                errors.append(f"{experiment}/{qa_id}: result is not a candidate subset")
            if experiment == "E3" and len(result_ids) > 20:
                errors.append(f"{experiment}/{qa_id}: selection exceeds 20")
            gold = set(qa["retrieval_evidence_ids"])
            complete = float(gold <= set(pool))
            metrics = final_ranking_metrics(qa["retrieval_evidence_ids"], result_ids, [10, 20])
            if metrics["20"]["all_recall"] > complete:
                errors.append(f"{experiment}/{qa_id}: All R@20 exceeds candidate coverage")
            per_query.append({"qa_id": qa_id, "complete": complete, "metrics": metrics})
        multi = [row for row in per_query if dev_by_id[row["qa_id"]]["retrieval_evidence_count"] >= 2]
        recomputed[experiment] = {
            "candidate_coverage@100": mean([row["complete"] for row in per_query]),
            "all_r@20": mean([row["metrics"]["20"]["all_recall"] for row in per_query]),
            "multi_all_r@20": mean([row["metrics"]["20"]["all_recall"] for row in multi]),
        }

    with (REPORT_DIR / "C1_RESULTS.csv").open(encoding="utf-8", newline="") as handle:
        reported = {row["experiment"]: row for row in csv.DictReader(handle)}
    for experiment, metrics in recomputed.items():
        for key, value in metrics.items():
            if abs(float(reported[experiment][key]) - value) > 1e-12:
                errors.append(f"{experiment}: reported {key} does not match ranking recomputation")

    for qa_id in expected_ids:
        g0 = candidates["G0"][qa_id]["candidate_ids"]
        if not (rankings["E0"][qa_id]["candidate_ids"] == g0
                == rankings["E2"][qa_id]["candidate_ids"]
                == rankings["E3"][qa_id]["candidate_ids"]):
            errors.append(f"{qa_id}: E0/E2/E3 do not share G0")

    source_e0 = {row["qa_id"]: row for row in read_jsonl(
        ROOT / "outputs/B2_3/rankings/m1_global_rrf_b100_dev.jsonl"
    )}
    source_e2 = {row["qa_id"]: row for row in read_jsonl(
        ROOT / "outputs/B2_3/rankings/m2_cross_encoder_b100_dev.jsonl"
    )}
    for experiment, source in (("E0", source_e0), ("E2", source_e2)):
        for qa_id in expected_ids:
            if rankings[experiment][qa_id]["results"] != source[qa_id]["results"]:
                errors.append(f"{experiment}/{qa_id}: verified B2.3 ranking was not reused exactly")
                break

    checksum_errors = []
    checksums = json.loads((REPORT_DIR / "CHECKSUMS.json").read_text(encoding="utf-8"))
    mutable = {"reports/C1/C1_AUDIT.json", "reports/C1/C1_READINESS.json", "reports/C1/C1_REPORT.md"}
    for entry in checksums["files"]:
        if entry["path"] in mutable:
            continue
        path = ROOT / entry["path"]
        if not path.is_file() or path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
            checksum_errors.append(entry["path"])
    if checksum_errors:
        errors.extend(f"checksum mismatch: {path}" for path in checksum_errors)

    existing["artifact_recomputation"] = {
        "status": "PASS" if not errors else "FAIL", "tolerance": 1e-12,
        "metrics": recomputed, "errors": errors,
    }
    existing["checks"]["artifact_metrics_independently_recomputed"] = not errors
    existing["checks"]["source_E0_E2_reused_exactly"] = not any("ranking was not reused" in value for value in errors)
    existing["checks"]["checksums_verified_before_independent_audit"] = not checksum_errors
    existing["status"] = "PASS" if all(existing["checks"].values()) and not errors else "FAIL"
    existing["remaining_blockers"] = [name for name, passed in existing["checks"].items() if not passed]
    existing["remaining_blockers"].extend(errors)
    write_json(REPORT_DIR / "C1_AUDIT.json", existing)

    readiness = json.loads((REPORT_DIR / "C1_READINESS.json").read_text(encoding="utf-8"))
    readiness["C1_VALID"] = existing["status"] == "PASS"
    readiness["status"] = existing["status"]
    readiness["remaining_blockers"] = existing["remaining_blockers"]
    readiness["ready_for_C2"] = bool(readiness["C1_VALID"] and readiness["ready_for_C2"])
    write_json(REPORT_DIR / "C1_READINESS.json", readiness)

    checksum_paths = [path for path in sorted(REPORT_DIR.glob("*"))
                      if path.is_file() and path.name != "CHECKSUMS.json"]
    checksum_paths.extend(path for path in sorted(OUTPUT_DIR.rglob("*")) if path.is_file())
    checksum_paths.append(ROOT / "configs/phase_c1.json")
    write_json(REPORT_DIR / "CHECKSUMS.json", {
        "files": [{"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
                   "sha256": sha256(path)} for path in checksum_paths]
    })
    print(json.dumps({"status": existing["status"], "errors": errors, "metrics": recomputed}, indent=2))
    return 0 if existing["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
