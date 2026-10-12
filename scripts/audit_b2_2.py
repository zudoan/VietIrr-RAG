from __future__ import annotations

import json
from pathlib import Path

from viirr_retrieval.candidate_metrics import (
    budgeted_candidate_coverage,
    final_ranking_metrics,
    raw_page_candidate_ceiling,
    validate_coverage_recall_invariant,
)
from viirr_retrieval.io_utils import read_jsonl, sha256, write_json


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/B2_2"
RANKINGS = ROOT / "outputs/B2_2/rankings"


def main() -> None:
    config = json.loads((ROOT / "configs/phase_b2_2.json").read_text(encoding="utf-8"))
    metrics = json.loads((REPORT / "METRICS.json").read_text(encoding="utf-8"))
    audit = json.loads((REPORT / "FINAL_AUDIT.json").read_text(encoding="utf-8"))
    readiness = json.loads((REPORT / "READINESS.json").read_text(encoding="utf-8"))
    dev = read_jsonl(ROOT / "data/benchmark/dev.jsonl")
    dev_by_id = {row["qa_id"]: row for row in dev}
    units = read_jsonl(ROOT / "data/processed/evidence_units.jsonl")
    valid_ids = {row["evidence_id"] for row in units}
    evidence_to_page = {row["evidence_id"]: row["page_id"] for row in units}
    page_rankings = {}
    for rep in ("P0", "P2"):
        rows = read_jsonl(ROOT / f"outputs/B2_1/rankings/{rep.lower()}_pages_dev_top100.jsonl")
        page_rankings[rep] = {
            row["qa_id"]: [item["page_id"] for item in row["results"]] for row in rows
        }

    errors = []
    recomputed = {}
    for rep in ("P0", "P2"):
        for strategy in ("S0", "S1", "S2"):
            page_p = int(config["strategies"][strategy]["page_budget"])
            for budget in config["candidate_budgets"]:
                label = f"{rep}_{strategy}_B{budget}"
                path = RANKINGS / f"{rep.lower()}_{strategy.lower()}_b{budget}_dev.jsonl"
                rows = read_jsonl(path)
                by_id = {row["qa_id"]: row for row in rows}
                if len(rows) != 93 or set(by_id) != set(dev_by_id):
                    errors.append(f"{label}: DEV row/ID mismatch")
                    continue
                coverage_values, raw_values = [], []
                final_values = {str(k): [] for k in config["final_k"]}
                for qa_id, qa in dev_by_id.items():
                    row = by_id[qa_id]
                    candidates = row["candidate_ids"]
                    results = row["results"]
                    result_ids = [item["evidence_id"] for item in results]
                    if len(candidates) != len(set(candidates)) or len(candidates) > budget:
                        errors.append(f"{label}/{qa_id}: invalid candidate pool")
                    if not set(candidates) <= valid_ids or set(result_ids) != set(candidates):
                        errors.append(f"{label}/{qa_id}: candidate/result mapping mismatch")
                    if len(result_ids) != len(set(result_ids)):
                        errors.append(f"{label}/{qa_id}: duplicate ranking IDs")
                    for rank, item in enumerate(results, 1):
                        if item["rank"] != rank:
                            errors.append(f"{label}/{qa_id}: rank sequence mismatch")
                            break
                    for left, right in zip(results, results[1:]):
                        if left["score"] < right["score"] or (
                            left["score"] == right["score"] and
                            left["evidence_id"] > right["evidence_id"]
                        ):
                            errors.append(f"{label}/{qa_id}: nondeterministic ranking order")
                            break
                    coverage = budgeted_candidate_coverage(
                        qa["retrieval_evidence_ids"], candidates, budget)
                    final = final_ranking_metrics(
                        qa["retrieval_evidence_ids"], result_ids, config["final_k"])
                    validate_coverage_recall_invariant(coverage, final, config["final_k"], budget)
                    raw = raw_page_candidate_ceiling(
                        qa["retrieval_evidence_ids"], page_rankings[rep][qa_id][:page_p],
                        evidence_to_page)
                    coverage_values.append(coverage)
                    raw_values.append(raw)
                    for k in config["final_k"]:
                        final_values[str(k)].append(final[str(k)]["all_recall"])
                recomputed[label] = {
                    "raw_page_candidate_ceiling": sum(raw_values) / len(raw_values),
                    "budgeted_candidate_coverage": sum(coverage_values) / len(coverage_values),
                    "final_all_evidence_recall": {
                        key: sum(values) / len(values) for key, values in final_values.items()
                    },
                }
                saved = metrics["configurations"][label]["OVERALL"]
                for name in ("raw_page_candidate_ceiling", "budgeted_candidate_coverage"):
                    if abs(recomputed[label][name] - saved[name]) > 1e-12:
                        errors.append(f"{label}: {name} mismatch")
                for k in config["final_k"]:
                    if abs(recomputed[label]["final_all_evidence_recall"][str(k)] -
                           saved["final_all_evidence_recall"][str(k)]) > 1e-12:
                        errors.append(f"{label}: final All R@{k} mismatch")

    passed = not errors
    audit["checks"]["artifact_metrics_independently_recomputed"] = passed
    audit["artifact_recomputation"] = {
        "status": "PASS" if passed else "FAIL",
        "tolerance": 1e-12,
        "configuration_count": len(recomputed),
        "errors": errors,
        "metrics": recomputed,
    }
    if not passed:
        audit["status"] = "FAIL"
        if "artifact metric recomputation failed" not in audit["remaining_blockers"]:
            audit["remaining_blockers"].append("artifact metric recomputation failed")
        readiness["B2_2_VALID"] = False
        readiness["status"] = "FAIL"
        if "artifact metric recomputation failed" not in readiness["remaining_blockers"]:
            readiness["remaining_blockers"].append("artifact metric recomputation failed")
    write_json(REPORT / "FINAL_AUDIT.json", audit)
    write_json(REPORT / "READINESS.json", readiness)

    paths = [path for path in sorted(REPORT.glob("*")) if path.is_file() and path.name != "CHECKSUMS.json"]
    paths.extend(sorted(RANKINGS.glob("*.jsonl")))
    write_json(REPORT / "CHECKSUMS.json", {
        "files": [{"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
                   "sha256": sha256(path)} for path in paths]
    })
    print(json.dumps({"status": "PASS" if passed else "FAIL", "errors": len(errors),
                      "configurations": len(recomputed)}))


if __name__ == "__main__":
    main()
