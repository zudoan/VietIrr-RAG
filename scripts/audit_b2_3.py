from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from viirr_retrieval.b23 import load_b23_dev, normalize_modality
from viirr_retrieval.candidate_metrics import (
    budgeted_candidate_coverage,
    final_ranking_metrics,
    validate_coverage_recall_invariant,
)
from viirr_retrieval.io_utils import read_jsonl, sha256, write_json


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/B2_3"
RANKINGS = ROOT / "outputs/B2_3/rankings"


def load_records(method: str, budget: int) -> dict[str, dict]:
    if method == "M0":
        path = ROOT / f"outputs/B2_2/rankings/p0_s1_b{budget}_dev.jsonl"
    elif method == "M1":
        path = RANKINGS / f"m1_global_rrf_b{budget}_dev.jsonl"
    else:
        path = RANKINGS / "m2_cross_encoder_b100_dev.jsonl"
    return {row["qa_id"]: row for row in read_jsonl(path)}


def main() -> None:
    config = json.loads((ROOT / "configs/phase_b2_3.json").read_text(encoding="utf-8"))
    saved = json.loads((REPORT / "METRICS.json").read_text(encoding="utf-8"))
    audit = json.loads((REPORT / "FINAL_AUDIT.json").read_text(encoding="utf-8"))
    readiness = json.loads((REPORT / "READINESS.json").read_text(encoding="utf-8"))
    dev = load_b23_dev(ROOT)
    dev_by_id = {qa["qa_id"]: qa for qa in dev}
    valid_ids = {row["evidence_id"] for row in read_jsonl(ROOT / "data/processed/evidence_units.jsonl")}
    specs = (("M0", 50), ("M0", 100), ("M1", 50), ("M1", 100), ("M2", 100))
    errors = []
    recomputed = {}
    loaded = {}
    for method, budget in specs:
        label = f"{method}_B{budget}"
        rows = load_records(method, budget)
        loaded[label] = rows
        if set(rows) != set(dev_by_id) or len(rows) != 93:
            errors.append(f"{label}: DEV QA set mismatch")
            continue
        coverage_values = []
        values = {str(k): [] for k in config["final_k"]}
        mrr, ndcg = [], []
        for qa_id, qa in dev_by_id.items():
            row = rows[qa_id]
            candidates = row["candidate_ids"]
            results = row["results"]
            result_ids = [item["evidence_id"] for item in results]
            if len(candidates) != len(set(candidates)) or len(candidates) > budget:
                errors.append(f"{label}/{qa_id}: invalid candidate pool")
            if set(candidates) != set(result_ids) or not set(candidates) <= valid_ids:
                errors.append(f"{label}/{qa_id}: candidate/result mismatch")
            for rank, item in enumerate(results, 1):
                if item["rank"] != rank:
                    errors.append(f"{label}/{qa_id}: rank mismatch")
                    break
            for left, right in zip(results, results[1:]):
                if left["score"] < right["score"] or (
                    left["score"] == right["score"] and left["evidence_id"] > right["evidence_id"]
                ):
                    errors.append(f"{label}/{qa_id}: unstable score/tie order")
                    break
            coverage = budgeted_candidate_coverage(qa["retrieval_evidence_ids"], candidates, budget)
            final = final_ranking_metrics(qa["retrieval_evidence_ids"], result_ids, config["final_k"])
            validate_coverage_recall_invariant(coverage, final, config["final_k"], budget)
            coverage_values.append(coverage)
            for k in config["final_k"]:
                values[str(k)].append(final[str(k)]["all_recall"])
            mrr.append(final["mrr"])
            ndcg.append(final["ndcg@10"])
        recomputed[label] = {
            "candidate_coverage": sum(coverage_values) / len(coverage_values),
            "all_recall": {key: sum(rows) / len(rows) for key, rows in values.items()},
            "mrr": sum(mrr) / len(mrr), "ndcg@10": sum(ndcg) / len(ndcg),
        }
        target = saved["overall"][label]
        if abs(recomputed[label]["candidate_coverage"] - target["candidate_coverage"]) > 1e-12:
            errors.append(f"{label}: candidate coverage mismatch")
        for k in config["final_k"]:
            if abs(recomputed[label]["all_recall"][str(k)] - target[str(k)]["all_recall"]) > 1e-12:
                errors.append(f"{label}: All R@{k} mismatch")
        if abs(recomputed[label]["mrr"] - target["mrr"]) > 1e-12:
            errors.append(f"{label}: MRR mismatch")
        if abs(recomputed[label]["ndcg@10"] - target["ndcg@10"]) > 1e-12:
            errors.append(f"{label}: nDCG mismatch")

    for qa_id in dev_by_id:
        expected = loaded["M0_B100"][qa_id]["candidate_ids"]
        if loaded["M1_B100"][qa_id]["candidate_ids"] != expected or \
                loaded["M2_B100"][qa_id]["candidate_ids"] != expected:
            errors.append(f"{qa_id}: B100 candidate IDs/order differ")

    score_rows = {row["qa_id"]: row for row in read_jsonl(ROOT / "outputs/B2_3/cache/m2_scores.jsonl")}
    for qa_id, row in score_rows.items():
        ordered = [item_id for item_id, _ in sorted(
            zip(row["candidate_ids"], row["scores"]), key=lambda item: (-item[1], item[0]))]
        actual = [item["evidence_id"] for item in loaded["M2_B100"][qa_id]["results"]]
        if ordered != actual:
            errors.append(f"{qa_id}: M2 score/ranking mismatch")

    modality_counts = Counter(normalize_modality(qa) for qa in dev)
    if sum(modality_counts.values()) != 93 or modality_counts != Counter(
            {"TEXT_ONLY": 29, "TABLE_ONLY": 39, "TEXT_TABLE": 22, "TABLE_TABLE": 3}):
        errors.append("modality mapping coverage/count mismatch")

    passed = not errors
    audit["checks"]["artifact_metrics_independently_recomputed"] = passed
    audit["checks"]["m2_cached_scores_match_ranking"] = not any("M2 score/ranking" in err for err in errors)
    audit["artifact_recomputation"] = {
        "status": "PASS" if passed else "FAIL", "tolerance": 1e-12,
        "configurations": recomputed, "errors": errors,
    }
    if not passed:
        audit["status"] = "FAIL"
        if "artifact recomputation failed" not in audit["remaining_blockers"]:
            audit["remaining_blockers"].append("artifact recomputation failed")
        readiness["B2_3_VALID"] = False
        readiness["status"] = "FAIL"
        if "artifact recomputation failed" not in readiness["remaining_blockers"]:
            readiness["remaining_blockers"].append("artifact recomputation failed")
    write_json(REPORT / "FINAL_AUDIT.json", audit)
    write_json(REPORT / "READINESS.json", readiness)

    paths = [path for path in sorted(REPORT.glob("*")) if path.is_file() and path.name != "CHECKSUMS.json"]
    paths.extend(sorted(RANKINGS.glob("*.jsonl")))
    paths.extend([ROOT / "outputs/B2_3/cache/m2_scores.jsonl",
                  ROOT / "outputs/B2_3/cache/m2_metadata.json"])
    write_json(REPORT / "CHECKSUMS.json", {
        "files": [{"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
                   "sha256": sha256(path)} for path in paths]
    })
    print(json.dumps({"status": "PASS" if passed else "FAIL", "errors": len(errors),
                      "configurations": len(recomputed)}))


if __name__ == "__main__":
    main()
