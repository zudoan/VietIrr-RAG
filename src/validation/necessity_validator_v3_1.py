"""Independent support-matrix and real ablation validation for V3.1."""

from __future__ import annotations

import re

from src.structure.semantic_table_parser import clean, fold
from src.validation.answer_component_extractor_v3_1 import extract_answer_components


def _compact_number(value: str) -> str:
    return re.sub(r"\s+", "", clean(value)).lower()


def judge_support(component: dict, evidence: dict) -> str:
    text = clean(component.get("text"))
    if not text:
        return "UNCERTAIN"
    if evidence.get("evidence_type") == "TEXT_REGION":
        claim = clean(evidence.get("claim_text") or evidence.get("text"))
        if fold(text).strip(" .;:") in fold(claim).strip(" .;:"):
            return "FULL_SUPPORT"
        overlap = set(fold(text).split()) & set(fold(claim).split())
        return "PARTIAL_SUPPORT" if len(overlap) >= 6 else "NO_SUPPORT"
    if evidence.get("evidence_type") == "TABLE_CELL":
        entity = fold(evidence.get("entity"))
        value = _compact_number(evidence.get("value"))
        folded_text = fold(text)
        compact_text = _compact_number(text)
        entity_ok = bool(entity and entity in folded_text)
        value_ok = bool(value and value in compact_text)
        metric = fold(evidence.get("metric_label") or evidence.get("metric"))
        metric_ok = bool(metric and metric in folded_text)
        if entity_ok and value_ok and metric_ok:
            return "FULL_SUPPORT"
        if sum((entity_ok, value_ok, metric_ok)) >= 2:
            return "PARTIAL_SUPPORT"
        return "NO_SUPPORT"
    return "UNCERTAIN"


def _support_for_set(components: list[dict], evidence: list[dict]) -> dict[str, str]:
    result = {}
    for component in components:
        judgments = [judge_support(component, item) for item in evidence]
        if "FULL_SUPPORT" in judgments:
            result[component["component_id"]] = "FULL_SUPPORT"
        elif "PARTIAL_SUPPORT" in judgments:
            result[component["component_id"]] = "PARTIAL_SUPPORT"
        elif "UNCERTAIN" in judgments:
            result[component["component_id"]] = "UNCERTAIN"
        else:
            result[component["component_id"]] = "NO_SUPPORT"
    return result


def validate_necessity(qa: dict) -> dict:
    components = extract_answer_components(qa.get("question", ""), qa.get("answer", ""))
    evidence = list(qa.get("gold_evidence") or [])
    matrix = {
        component["component_id"]: {
            item["evidence_id"]: judge_support(component, item) for item in evidence
        }
        for component in components
    }
    full_support = _support_for_set(components, evidence)
    ablations = {}
    necessary_flags = {}
    for removed in evidence:
        remaining = [item for item in evidence if item["evidence_id"] != removed["evidence_id"]]
        support = _support_for_set(components, remaining)
        key = f"without_{removed['evidence_id']}"
        loses_complete = any(
            full_support.get(cid) == "FULL_SUPPORT" and support.get(cid) != "FULL_SUPPORT"
            for cid in full_support
        )
        ablations[key] = {"support": support, "evidence_removed": removed["evidence_id"], "necessary": loses_complete}
        necessary_flags[removed["evidence_id"]] = loses_complete
    full_ok = bool(components) and all(value == "FULL_SUPPORT" for value in full_support.values())
    uncertain = any(value == "UNCERTAIN" for value in full_support.values()) or any(
        cell == "UNCERTAIN" for row in matrix.values() for cell in row.values()
    )
    all_necessary = bool(evidence) and all(necessary_flags.values())
    if uncertain:
        status = "UNCERTAIN"
    elif full_ok and all_necessary:
        status = "PASS"
    else:
        status = "FAIL"
    return {
        "qa_id": qa.get("qa_id"), "components": components,
        "support_matrix": matrix, "full_set_support": full_support,
        "ablations": ablations, "minimal_gold_set": status == "PASS",
        "necessity_status": status,
        "component_extractor_received_gold_count": False,
        "ablation_executed": True,
    }
