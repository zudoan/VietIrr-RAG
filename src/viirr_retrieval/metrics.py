from __future__ import annotations

import math


def evaluate_ranking(gold_ids: list[str], ranked_ids: list[str], ks: list[int]) -> dict:
    gold = set(gold_ids)
    if not gold:
        raise ValueError("Retrieval evaluation requires at least one gold unit")
    output = {}
    for k in ks:
        found = gold & set(ranked_ids[:k])
        output[str(k)] = {"any_recall": float(bool(found)), "all_recall": float(found == gold),
                          "gold_coverage": len(found) / len(gold)}
    first_rank = next((rank for rank, item_id in enumerate(ranked_ids, 1) if item_id in gold), None)
    mrr = 0.0 if first_rank is None else 1.0 / first_rank
    dcg = sum((1.0 / math.log2(rank + 1)) for rank, item_id in enumerate(ranked_ids[:10], 1) if item_id in gold)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(len(gold), 10) + 1))
    output["mrr"] = mrr
    output["ndcg@10"] = dcg / ideal
    return output


def aggregate(per_query: list[dict], ks: list[int]) -> dict:
    count = len(per_query)
    if not count:
        return {"sample_count": 0, **{str(k): {"any_recall": None, "all_recall": None,
                                                "gold_coverage": None} for k in ks},
                "mrr": None, "ndcg@10": None}
    result = {"sample_count": count}
    for k in ks:
        result[str(k)] = {name: sum(row[str(k)][name] for row in per_query) / count
                          for name in ("any_recall", "all_recall", "gold_coverage")}
    result["mrr"] = sum(row["mrr"] for row in per_query) / count
    result["ndcg@10"] = sum(row["ndcg@10"] for row in per_query) / count
    return result


def evaluate_pages(gold_page_ids: list[str], ranked_page_ids: list[str], ps: list[int]) -> dict:
    gold = set(gold_page_ids)
    return {str(p): {"any_gold_page_recall": float(bool(gold & set(ranked_page_ids[:p]))),
                     "complete_gold_page_recall": float(gold <= set(ranked_page_ids[:p]))}
            for p in ps}


def validate_metric_invariants(metrics: dict, ks: list[int]) -> None:
    previous_any = previous_all = -1.0
    for k in ks:
        row = metrics[str(k)]
        if not 0.0 <= row["all_recall"] <= row["any_recall"] <= 1.0:
            raise AssertionError(f"Recall invariant failed at K={k}: {row}")
        if row["any_recall"] < previous_any or row["all_recall"] < previous_all:
            raise AssertionError(f"Recall must be monotonic at K={k}")
        previous_any, previous_all = row["any_recall"], row["all_recall"]
