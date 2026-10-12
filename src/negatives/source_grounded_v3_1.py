"""Build V3.1 negatives only from source-resolved evidence.

Minimal negatives substitute one gold table cell with a real table cell whose
provenance signature differs on one declared query dimension.  No entity,
period, metric, unit, or evidence text is invented here.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from src.evidence.relation_discovery import make_table_evidence, normalized_family, valid_relation_entity


def _period(ev: dict) -> str | None:
    return (ev.get("period") or {}).get("start")


def signature(ev: dict) -> dict:
    return {
        "entity": ev.get("entity_canonical"),
        "metric": ev.get("metric"),
        "unit": ev.get("unit_normalized"),
        "period": _period(ev),
        "value": ev.get("value"),
        "evidence_id": ev.get("evidence_id"),
        "doc_id": ev.get("doc_id"),
        "table_id": ev.get("table_id"),
    }


def signature_differences(gold: dict, negative: dict) -> list[str]:
    return [key for key in ("entity", "metric", "unit", "period") if gold.get(key) != negative.get(key)]


def build_table_pool(documents: list[dict], tables: list[dict]) -> list[dict]:
    docs = {d["doc_id"]: d for d in documents if d.get("document_type_v3_1") != "supporting_reference"}
    pool = []
    for table in tables:
        doc = docs.get(table.get("doc_id"))
        if not doc or table.get("structural_quality") != "GOOD" or table.get("semantic_quality") != "GOOD":
            continue
        for tup in table.get("semantic_tuples", []):
            if not tup.get("qa_eligible") or not valid_relation_entity(tup["entity"]["raw"], tup["entity"]["canonical"]):
                continue
            pool.append(make_table_evidence(table, tup, doc))
    return pool


def _candidate_indexes(pool: Iterable[dict], documents: list[dict]) -> dict:
    docs = {d["doc_id"]: d for d in documents}
    indexes: dict[str, dict[tuple, list[dict]]] = {
        "WRONG_ENTITY": defaultdict(list),
        "WRONG_PERIOD": defaultdict(list),
        "WRONG_METRIC": defaultdict(list),
    }
    for ev in pool:
        sig = signature(ev)
        indexes["WRONG_ENTITY"][(sig["metric"], sig["unit"], sig["period"])].append(ev)
        family = normalized_family(docs[ev["doc_id"]]["title"], docs[ev["doc_id"]].get("source_group", ""))
        indexes["WRONG_PERIOD"][(sig["entity"], sig["metric"], sig["unit"], family)].append(ev)
        indexes["WRONG_METRIC"][(sig["entity"], sig["unit"], sig["period"])].append(ev)
    return indexes


def _select_alternative(kind: str, gold: dict, indexes: dict, documents: list[dict], excluded_ids: set[str] | None = None) -> dict | None:
    sig = signature(gold)
    excluded_ids = excluded_ids or set()
    if kind == "WRONG_ENTITY":
        candidates = indexes[kind].get((sig["metric"], sig["unit"], sig["period"]), [])
        candidates = [x for x in candidates if x["entity_canonical"] != sig["entity"] and x["evidence_id"] not in excluded_ids]
        candidates.sort(key=lambda x: (x.get("table_id") != gold.get("table_id"), x.get("doc_id") != gold.get("doc_id"), x["evidence_id"]))
    elif kind == "WRONG_PERIOD":
        doc = next(d for d in documents if d["doc_id"] == gold["doc_id"])
        family = normalized_family(doc["title"], doc.get("source_group", ""))
        candidates = indexes[kind].get((sig["entity"], sig["metric"], sig["unit"], family), [])
        candidates = [x for x in candidates if _period(x) and _period(x) != sig["period"] and x["evidence_id"] not in excluded_ids]
        candidates.sort(key=lambda x: (x.get("table_id") == gold.get("table_id"), x["evidence_id"]))
    else:
        candidates = indexes[kind].get((sig["entity"], sig["unit"], sig["period"]), [])
        candidates = [x for x in candidates if x["metric"] != sig["metric"] and x["evidence_id"] not in excluded_ids]
        candidates.sort(key=lambda x: (x.get("doc_id") != gold.get("doc_id"), x["evidence_id"]))
    return candidates[0] if candidates else None


def build_minimal(qa_rows: list[dict], pool: list[dict], documents: list[dict], limit: int = 700) -> list[dict]:
    indexes = _candidate_indexes(pool, documents)
    rows, seen = [], set()
    for qa in qa_rows:
        gold_ids = set(qa.get("gold_evidence_ids", []))
        for position, gold in enumerate(qa.get("gold_evidence", [])):
            if gold.get("evidence_type") != "TABLE_CELL":
                continue
            for kind in ("WRONG_ENTITY", "WRONG_PERIOD", "WRONG_METRIC"):
                alt = _select_alternative(kind, gold, indexes, documents, gold_ids)
                if not alt:
                    continue
                key = (qa["qa_id"], gold["evidence_id"], alt["evidence_id"], kind)
                if key in seen:
                    continue
                seen.add(key)
                candidate = list(qa["gold_evidence"])
                candidate[position] = alt
                gs, ns = signature(gold), signature(alt)
                rows.append({
                    "negative_id": f"V3_1_NEG_MIN_{len(rows)+1:05d}",
                    "source_qa_id": qa["qa_id"], "negative_type": kind,
                    "question": qa["question"], "expected_label": "NEGATIVE",
                    "gold_target_evidence_id": gold["evidence_id"],
                    "negative_evidence_id": alt["evidence_id"],
                    "candidate_evidence_ids": [x["evidence_id"] for x in candidate],
                    "candidate_evidence": candidate,
                    "gold_signature": gs, "negative_signature": ns,
                    "signature_differences": signature_differences(gs, ns),
                    "mutation_dimensions": [kind.removeprefix("WRONG_").lower()],
                    "minimal_counterfactual": True, "source_grounded": True,
                    "construction_method": "real_evidence_substitution",
                    "review_status": "AUTO_VALIDATED", "human_validated": False,
                })
                if len(rows) >= limit:
                    return rows
    return rows


def build_partial(challenge: list[dict]) -> list[dict]:
    rows = []
    for qa in challenge:
        ablations = (qa.get("necessity_validation") or {}).get("ablations") or {}
        for ev in qa.get("gold_evidence", []):
            outcome = ablations.get(f"without_{ev['evidence_id']}")
            if not outcome or not outcome.get("necessary"):
                continue
            kept = [x for x in qa["gold_evidence"] if x["evidence_id"] != ev["evidence_id"]]
            unsupported = [cid for cid, state in outcome.get("support", {}).items() if state != "FULL_SUPPORT"]
            rows.append({
                "negative_id": f"V3_1_NEG_PART_{len(rows)+1:05d}",
                "source_qa_id": qa["qa_id"], "negative_type": "PARTIAL_EVIDENCE_SET",
                "question": qa["question"], "expected_label": "NEGATIVE",
                "candidate_evidence": kept, "candidate_evidence_ids": [x["evidence_id"] for x in kept],
                "removed_evidence_id": ev["evidence_id"], "negative_evidence_id": ev["evidence_id"],
                "unsupported_component_ids": unsupported,
                "ablation_proof": outcome, "minimal_counterfactual": False,
                "source_grounded": True, "construction_method": "validated_necessity_ablation",
                "review_status": "AUTO_VALIDATED", "human_validated": False,
            })
            break
    return rows


def build_redundant(challenge: list[dict], pool: list[dict], documents: list[dict]) -> list[dict]:
    indexes = _candidate_indexes(pool, documents)
    rows = []
    for qa in challenge:
        distractor = None
        gold_ids = set(qa.get("gold_evidence_ids", []))
        for gold in qa.get("gold_evidence", []):
            if gold.get("evidence_type") != "TABLE_CELL":
                continue
            distractor = _select_alternative("WRONG_PERIOD", gold, indexes, documents, gold_ids)
            if not distractor:
                distractor = _select_alternative("WRONG_ENTITY", gold, indexes, documents, gold_ids)
            if distractor:
                break
        if not distractor:
            continue
        candidate = qa["gold_evidence"] + [distractor]
        rows.append({
            "negative_id": f"V3_1_NEG_RED_{len(rows)+1:05d}",
            "source_qa_id": qa["qa_id"], "negative_type": "REDUNDANT_EVIDENCE_SET",
            "question": qa["question"], "expected_label": "NEGATIVE",
            "candidate_evidence": candidate, "candidate_evidence_ids": [x["evidence_id"] for x in candidate],
            "redundant_evidence_id": distractor["evidence_id"], "negative_evidence_id": distractor["evidence_id"],
            "minimal_counterfactual": False, "source_grounded": True,
            "construction_method": "real_related_evidence_addition",
            "review_status": "AUTO_VALIDATED", "human_validated": False,
        })
    return rows
