"""Fail-closed contextual topic alignment for the V3.2 semantic freeze.

This validator intentionally distinguishes generic elevation from water level
and checks common quantitative near-neighbour concepts independently of the
legacy keyword validator.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.validation.topic_alignment_validator_v3_2 import validate_topic_alignment


def fold(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "")).lower()
    return "".join(c for c in text if unicodedata.category(c) != "Mn").replace("đ", "d")


CONCEPTS = {
    "WATER_LEVEL": ("muc nuoc", "cao trinh muc nuoc", "cao trinh mat nuoc"),
    "ELEVATION": ("cao trinh", "cao do"),
    "STORAGE_VOLUME": ("dung tich", "tru luong"),
    "STORAGE_PERCENT": ("ty le dung tich", "% dung tich", "so voi thiet ke"),
    "RAINFALL_AMOUNT": ("luong mua", "tong luong mua"),
    "RAINFALL_PERCENT": ("ty le luong mua", "% luong mua", "so voi trung binh"),
    "INFLOW": ("luu luong den", "dong chay den", "luu luong ve ho"),
    "OUTFLOW": ("luu luong xa", "dong chay xa", "xa qua"),
    "FORECAST": ("du bao",),
    "OBSERVED": ("thuc do", "quan trac", "ghi nhan"),
    "AREA": ("dien tich",),
    "IRRIGATED_AREA": ("dien tich tuoi", "dien tich dap ung", "dien tich gieo trong"),
    "SALINITY": ("do man", "xam nhap man", "nong do man"),
    "WATER_QUALITY": ("chat luong nuoc", "wqi", "bod", "cod", "tss"),
    "THRESHOLD": ("nguong", "gioi han", "quy chuan"),
    "ACTUAL_VALUE": ("thuc do", "quan trac", "ghi nhan", "dat", "la"),
}


def _has(text: str, cues: tuple[str, ...]) -> bool:
    value = f" {re.sub(r'[^a-z0-9%]+', ' ', fold(text)).strip()} "
    return any(f" {re.sub(r'[^a-z0-9%]+', ' ', fold(c)).strip()} " in value for c in cues)


def _evidence_texts(row: dict) -> list[str]:
    results = []
    for evidence in row.get("gold_evidence") or []:
        tup = evidence.get("semantic_tuple") or {}
        metric = tup.get("metric") or {}
        results.append(" | ".join(str(x) for x in (
            evidence.get("text"), evidence.get("metric"), evidence.get("metric_label"), evidence.get("metric_raw"),
            metric.get("raw"), metric.get("normalized"), evidence.get("unit"), evidence.get("value"),
        ) if x not in (None, "")))
    return results


def _elevation_subtype(evidence_text: str) -> str | None:
    value = fold(evidence_text)
    if "cao trinh o bao" in value or ("o bao" in value and "cao trinh" in value):
        return "cao trình ô bao"
    if "cao trinh mat dat" in value or "cao do mat dat" in value:
        return "cao trình mặt đất"
    if "cao trinh day kenh" in value:
        return "cao trình đáy kênh"
    return None


def _replace_water_level(question: str, subtype: str) -> str:
    return re.sub(r"mực\s+nước", subtype, question, count=1, flags=re.IGNORECASE)


def validate_contextual_topic_alignment(row: dict) -> dict:
    question, answer = str(row.get("question") or ""), str(row.get("answer") or "")
    evidence = _evidence_texts(row)
    evidence_joined = "\n".join(evidence)
    qf, ef = fold(question), fold(evidence_joined)
    errors: list[str] = []

    # The critical regression: generic terrain/structure elevation cannot prove
    # a water-level claim.  A deterministic repair is allowed only when the
    # exact elevation subtype is explicit in the source passage.
    if "muc nuoc" in qf and "muc nuoc" not in ef:
        subtype = _elevation_subtype(evidence_joined)
        if subtype:
            return {
                "status": "REPAIR", "errors": ["WATER_LEVEL_ELEVATION_CONFUSION"],
                "question_concept": "WATER_LEVEL", "evidence_concept": "ELEVATION",
                "elevation_subtype": subtype,
                "proposed_question": _replace_water_level(question, subtype),
                "proposed_answer": answer,
                "validation_basis": "source explicitly states an elevation subtype, not a water level",
            }
        errors.append("WATER_LEVEL_NOT_SUPPORTED_BY_EVIDENCE")

    pairs = (
        ("STORAGE_PERCENT", "STORAGE_VOLUME"),
        ("RAINFALL_PERCENT", "RAINFALL_AMOUNT"),
        ("INFLOW", "OUTFLOW"),
        ("OUTFLOW", "INFLOW"),
        ("IRRIGATED_AREA", "AREA"),
        ("SALINITY", "WATER_QUALITY"),
    )
    for requested, neighbour in pairs:
        if _has(question, CONCEPTS[requested]) and not _has(evidence_joined, CONCEPTS[requested]):
            if _has(evidence_joined, CONCEPTS[neighbour]):
                errors.append(f"{requested}_CONFUSED_WITH_{neighbour}")

    if _has(question, CONCEPTS["THRESHOLD"]) and not _has(evidence_joined, CONCEPTS["THRESHOLD"]):
        errors.append("THRESHOLD_CONFUSED_WITH_ACTUAL_VALUE")

    # Forecast/observed distinctions are intentionally delegated to the
    # evidence-time validator.  Report titles frequently contain "dự báo" even
    # when the requested fact itself is neither a forecast nor an observation.

    legacy = validate_topic_alignment(question, answer, evidence)
    if legacy["status"] == "FAIL":
        errors.extend(x for x in legacy.get("errors", []) if x not in errors)
    if errors:
        return {"status": "REJECT", "errors": errors, "legacy": legacy,
                "proposed_question": None, "proposed_answer": None,
                "validation_basis": "contextual concept and requested-relation checks"}
    if legacy["status"] == "UNCERTAIN":
        return {"status": "UNCERTAIN", "errors": legacy.get("errors", []), "legacy": legacy,
                "proposed_question": None, "proposed_answer": None,
                "validation_basis": "question concept could not be resolved"}
    return {"status": "PASS", "errors": [], "legacy": legacy,
            "proposed_question": None, "proposed_answer": None,
            "validation_basis": "contextual concept and requested-relation checks"}
