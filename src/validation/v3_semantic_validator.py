"""Independent strict semantic validator for V3 QA records."""

from __future__ import annotations

import re
from typing import Any

from src.structure.semantic_table_parser import DATE_LIKE, ROMAN, clean, fold


RED_FLAG_FIELDS = {"tt", "stt", "date", "year", "ngay", "thang", "nam", "index", "so thu tu"}
VALID_METRICS = {
    "NarrativeStatement", "WaterLevel", "Discharge", "Rainfall", "ReservoirStorage", "Area",
    "Salinity", "Temperature", "PH", "DissolvedOxygen", "BOD", "COD", "TSS", "Ammonium",
    "Nitrate", "Phosphate", "AffectedHouseholds", "Production", "WaterDemand",
}


def _evidence_supports(component: dict, evidence: dict) -> bool:
    text = clean(component.get("text"))
    if evidence.get("evidence_type") == "TEXT_REGION":
        return fold(text.rstrip(".")) in fold(evidence.get("text", ""))
    tup = evidence.get("semantic_tuple") or {}
    return clean((tup.get("value") or {}).get("raw")) in text


def validate_record(qa: dict) -> tuple[str, list[str]]:
    errors: list[str] = []
    question = clean(qa.get("question"))
    if not question or not clean(qa.get("answer")):
        errors.append("EMPTY_QUESTION_OR_ANSWER")
    if re.search(r"\btrang\s+\d+\b", question, re.I):
        errors.append("PAGE_NUMBER_IN_QUESTION")
    evidence = qa.get("gold_evidence") or []
    components = qa.get("answer_components") or []
    if not evidence or not components:
        errors.append("MISSING_COMPONENTS_OR_EVIDENCE")
    if qa.get("challenge") and len(evidence) < 2:
        errors.append("CHALLENGE_NOT_MULTI_EVIDENCE")
    if len({e.get("evidence_id") for e in evidence}) != len(evidence):
        errors.append("DUPLICATE_GOLD_EVIDENCE")
    evidence_by_id = {e.get("evidence_id"): e for e in evidence}
    for component in components:
        supporting = component.get("supporting_evidence_ids") or []
        if len(supporting) != 1 or supporting[0] not in evidence_by_id:
            errors.append("COMPONENT_SUPPORT_NOT_INDEPENDENT")
            continue
        if not _evidence_supports(component, evidence_by_id[supporting[0]]):
            errors.append("ANSWER_NOT_DERIVABLE")
    if set(qa.get("gold_evidence_ids") or []) != set(evidence_by_id):
        errors.append("EVIDENCE_ID_MISMATCH")
    if not qa.get("minimal_gold_set") or len(qa.get("necessity_ablation") or []) != len(evidence):
        errors.append("NECESSITY_NOT_ESTABLISHED")
    signatures = qa.get("provenance_signatures") or []
    if len(signatures) != len(evidence):
        errors.append("PROVENANCE_CARDINALITY_MISMATCH")
    for sig in signatures:
        entity = sig.get("entity") or {}; metric = sig.get("metric") or {}; unit = sig.get("unit") or {}
        eraw, ecanonical = clean(entity.get("raw")), clean(entity.get("canonical"))
        mraw, mcanonical = clean(metric.get("raw")), clean(metric.get("canonical"))
        if not eraw or fold(eraw) in RED_FLAG_FIELDS or DATE_LIKE.fullmatch(eraw) or ROMAN.fullmatch(eraw):
            errors.append("INVALID_ENTITY_SIGNATURE")
        if not mcanonical or mcanonical not in VALID_METRICS or fold(mraw) in RED_FLAG_FIELDS:
            errors.append("INVALID_METRIC_SIGNATURE")
        if unit.get("raw") in {"đơn vị", "unit", "UNKNOWN", "N/A"}:
            errors.append("FAKE_UNIT")
        if entity.get("confidence", 0) < 0.75 or metric.get("confidence", 0) < 0.75:
            errors.append("LOW_PROVENANCE_CONFIDENCE")
    if any(e.get("text_extraction") == "OCR" and any(ch.isdigit() for ch in c.get("text", "")) for e, c in zip(evidence, components)):
        errors.append("OCR_NUMERIC_QA_PROHIBITED")
    return ("PASS" if not errors else "REJECT"), sorted(set(errors))


def validate_dataset(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    passed, rejected, uncertain = [], [], []
    seen_questions = set()
    for qa in rows:
        status, reasons = validate_record(qa)
        key = fold(qa.get("question"))
        if key in seen_questions:
            status, reasons = "REJECT", sorted(set(reasons + ["EXACT_DUPLICATE_QUESTION"]))
        if status == "PASS":
            qa["status"] = "PASS"; qa["validation_errors"] = []
            passed.append(qa); seen_questions.add(key)
        else:
            qa["status"] = "REJECT"; qa["validation_errors"] = reasons
            rejected.append(qa)
    return passed, rejected, uncertain

