from __future__ import annotations

import math


def deduplicate(ids: list[str]) -> list[str]:
    output, seen = [], set()
    for item_id in ids:
        if item_id not in seen:
            seen.add(item_id)
            output.append(item_id)
    return output


def raw_page_candidate_ceiling(gold_ids: list[str], selected_page_ids: list[str],
                               evidence_to_page: dict[str, str]) -> float:
    selected = set(selected_page_ids)
    return float(all(evidence_to_page[item_id] in selected for item_id in gold_ids))


def budgeted_candidate_coverage(gold_ids: list[str], candidate_ids: list[str], budget: int) -> float:
    candidates = deduplicate(candidate_ids)
    if len(candidates) > budget:
        raise ValueError(f"Candidate pool has {len(candidates)} unique IDs, budget is {budget}")
    return float(set(gold_ids) <= set(candidates))


def final_ranking_metrics(gold_ids: list[str], ranked_ids: list[str], ks: list[int]) -> dict:
    ranking = deduplicate(ranked_ids)
    gold = set(gold_ids)
    if not gold:
        raise ValueError("Gold evidence set must be non-empty")
    output = {}
    last_any = last_all = -1.0
    for k in ks:
        found = gold.intersection(ranking[:k])
        row = {
            "any_recall": float(bool(found)),
            "all_recall": float(found == gold),
            "average_gold_coverage": len(found) / len(gold),
        }
        if row["any_recall"] < last_any or row["all_recall"] < last_all:
            raise AssertionError("Recall must be monotonic over one fixed ranking")
        output[str(k)] = row
        last_any, last_all = row["any_recall"], row["all_recall"]
    first = next((rank for rank, item_id in enumerate(ranking, 1) if item_id in gold), None)
    output["mrr"] = 0.0 if first is None else 1.0 / first
    dcg = sum(1.0 / math.log2(rank + 1) for rank, item_id in enumerate(ranking[:10], 1)
              if item_id in gold)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(10, len(gold)) + 1))
    output["ndcg@10"] = dcg / ideal
    return output


def validate_coverage_recall_invariant(candidate_coverage: float, final_metrics: dict,
                                       ks: list[int], candidate_budget: int) -> None:
    for k in ks:
        if k <= candidate_budget and final_metrics[str(k)]["all_recall"] > candidate_coverage:
            raise AssertionError(
                f"Final All R@{k} cannot exceed complete candidate coverage at B={candidate_budget}"
            )
