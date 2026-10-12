from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METHODS = ("M0", "M1", "M2", "M3", "M4")


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def mapping(path: Path) -> dict[str, dict]:
    return {row["qa_id"]: row for row in read_jsonl(path)}


def primary(dev: list[dict], records: dict[str, dict]) -> dict:
    coverage, overall, multi = [], [], []
    signatures: dict[str, list[float]] = {}
    for qa in dev:
        record = records[qa["qa_id"]]
        gold = set(qa["retrieval_evidence_ids"])
        candidates = set(record["candidate_ids"])
        ranked = [row["evidence_id"] for row in record["results"]]
        coverage.append(float(gold <= candidates))
        success = float(gold <= set(ranked[:20]))
        overall.append(success)
        if qa["retrieval_multi_evidence"]:
            multi.append(success)
        signature = "|".join(sorted(gold))
        signatures.setdefault(signature, []).append(success)
    return {
        "candidate_coverage@100": sum(coverage) / len(coverage),
        "all_r@20": sum(overall) / len(overall),
        "multi_all_r@20": sum(multi) / len(multi),
        "unique_gold_set_balanced_all_r@20": sum(
            sum(values) / len(values) for values in signatures.values()
        ) / len(signatures),
    }


def main() -> int:
    dev = read_jsonl(ROOT / "data/benchmark/dev.jsonl")
    reported = {
        row["method"]: row for row in csv.DictReader(
            (ROOT / "reports/MAR_ER_EXPERIMENT/RESULTS.csv").open(encoding="utf-8")
        )
    }
    output = {}
    errors = []
    rankings = {}
    for method in METHODS:
        rankings[method] = mapping(ROOT / f"outputs/MAR_ER/rankings/{method.lower()}_dev.jsonl")
        output[method] = primary(dev, rankings[method])
        for metric, value in output[method].items():
            if abs(float(reported[method][metric]) - value) > 1e-12:
                errors.append(f"metric:{method}:{metric}")
    for qa in dev:
        qa_id = qa["qa_id"]
        baseline = [row["evidence_id"] for row in rankings["M0"][qa_id]["results"]]
        protected = baseline[:15]
        for method in ("M3", "M4"):
            final = [row["evidence_id"] for row in rankings[method][qa_id]["results"][:20]]
            if len(set(final) & set(baseline[:20])) < 15:
                errors.append(f"top20_overlap:{method}:{qa_id}")
            if [item for item in final if item in set(protected)] != protected:
                errors.append(f"protected_order:{method}:{qa_id}")
            ranks = {item: rank for rank, item in enumerate(final, 1)}
            if any(item not in ranks or ranks[item] - (index + 1) > 5
                   for index, item in enumerate(protected)):
                errors.append(f"protected_displacement:{method}:{qa_id}")
    print(json.dumps({
        "status": "PASS" if not errors else "FAIL",
        "dev_qa": len(dev),
        "metrics": output,
        "errors": errors,
        "gpu_or_model_loaded": False,
    }, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
