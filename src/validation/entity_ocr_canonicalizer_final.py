"""Controlled entity and metric OCR canonicalization for the final freeze.

Raw source strings are never overwritten.  Only entries in the evidence-backed
maps below may be normalized automatically; unknown suspicious strings fail
closed for human review.
"""

from __future__ import annotations

import copy
import re
import unicodedata
from typing import Any


ENTITY_MAP = {
    "Ai NghTa": "Ái Nghĩa",
    "A Vuong": "A Vương",
    "Bau Nit": "Bàu Nít",
    "Blnh Dinh": "Bình Định",
    "C.An Trung": "C. An Trung",
    "Cao Ngan": "Cao Ngạn",
    "Cay Thong": "Cây Thông",
    "Dak Drinh": "Đắk Đrinh",
    "KaNak": "Ka Năk",
    "Khanh Hoa": "Khánh Hòa",
    "NHO QUAN": "Nho Quan",
    "Quang Nam": "Quảng Nam",
    "QuangNgai": "Quảng Ngãi",
    "Song Hinh": "Sông Hinh",
    "Vinh Son C": "Vĩnh Sơn C",
    "An Khe": "An Khê",
}

ENTITY_BASIS = "canonical spelling confirmed by another legible occurrence in the same corpus/source family"

METRIC_MAP = {
    "Dung tich bg to~m m3 (tri~u ) — Thi St kS": "Dung tích hồ toàn bộ (triệu m3) — Thiết kế",
    "Dung tich toan b(.> m3 (tri~u ) — ThiSt k6": "Dung tích hồ toàn bộ (triệu m3) — Thiết kế",
    "Dung tich hi9n t;,1i — Wtb (trieu m3)": "Dung tích hiện tại — Wtb (triệu m3)",
    "Dien tich dap irng (ha)": "Diện tích đáp ứng (ha)",
}
METRIC_BASIS = "reconstructed from the table's multi-level header, unit, and adjacent column labels"


def fold(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "")).lower()
    return "".join(c for c in text if unicodedata.category(c) != "Mn").replace("đ", "d")


def _suspicious_entity(value: str) -> bool:
    return bool(re.search(r"[?<>~]", value) or re.search(r"(?:NghTa|Blnh|QuangNgai|KaNak)", value))


def _suspicious_metric(value: str) -> bool:
    return bool(re.search(r"[?<>~]", value) or re.search(r"\b(?:hi9n|irng|tri~u|ThiSt)\b", value))


def inspect_qa_entities_metrics(row: dict) -> dict:
    checks = []
    for index, evidence in enumerate(row.get("gold_evidence") or []):
        entity = str(evidence.get("entity") or ((evidence.get("semantic_tuple") or {}).get("entity") or {}).get("raw") or "")
        if entity in ENTITY_MAP:
            checks.append({"path": f"gold_evidence[{index}].entity", "semantic_role": "entity",
                           "raw": entity, "normalized": ENTITY_MAP[entity], "status": "NORMALIZED",
                           "normalization_basis": ENTITY_BASIS})
        elif entity and _suspicious_entity(entity):
            checks.append({"path": f"gold_evidence[{index}].entity", "semantic_role": "entity",
                           "raw": entity, "normalized": None, "status": "UNCERTAIN",
                           "normalization_basis": None})
        raw_metric = str(evidence.get("metric_raw") or ((evidence.get("semantic_tuple") or {}).get("metric") or {}).get("raw") or "")
        if raw_metric in METRIC_MAP:
            checks.append({"path": f"gold_evidence[{index}].metric_raw", "semantic_role": "metric",
                           "raw": raw_metric, "normalized": METRIC_MAP[raw_metric], "status": "NORMALIZED",
                           "normalization_basis": METRIC_BASIS})
        elif raw_metric and _suspicious_metric(raw_metric):
            checks.append({"path": f"gold_evidence[{index}].metric_raw", "semantic_role": "metric",
                           "raw": raw_metric, "normalized": None, "status": "UNCERTAIN",
                           "normalization_basis": None})
    unresolved = [x for x in checks if x["status"] == "UNCERTAIN"]
    normalized = [x for x in checks if x["status"] == "NORMALIZED"]
    status = "UNCERTAIN" if unresolved else ("NORMALIZED" if normalized else "CLEAN")
    return {"status": status, "checks": checks, "normalizations": normalized,
            "uncertain_fields": unresolved, "raw_source_preserved": True}


def _replace_exact(text: str, raw: str, normalized: str) -> str:
    return text.replace(raw, normalized)


def canonicalize_qa(row: dict) -> tuple[dict, dict]:
    output = copy.deepcopy(row)
    audit = inspect_qa_entities_metrics(output)
    if audit["status"] == "UNCERTAIN":
        return output, audit
    for evidence in output.get("gold_evidence") or []:
        raw_entity = str(evidence.get("entity") or ((evidence.get("semantic_tuple") or {}).get("entity") or {}).get("raw") or "")
        if raw_entity in ENTITY_MAP:
            normalized = ENTITY_MAP[raw_entity]
            for field in ("question", "answer"):
                output[field] = _replace_exact(str(output.get(field) or ""), raw_entity, normalized)
            evidence["entity_raw"] = raw_entity
            evidence["entity"] = normalized
            evidence["entity_normalized"] = normalized
            evidence["entity_canonical"] = fold(normalized)
            evidence["entity_normalization_basis"] = ENTITY_BASIS
            entity_tuple = (evidence.setdefault("semantic_tuple", {}).setdefault("entity", {}))
            entity_tuple.setdefault("raw", raw_entity)
            entity_tuple["normalized"] = normalized
            entity_tuple["canonical"] = fold(normalized)
            entity_tuple["normalization_basis"] = ENTITY_BASIS
            if evidence.get("text"):
                evidence["text_normalized"] = _replace_exact(str(evidence["text"]), raw_entity, normalized)
        raw_metric = str(evidence.get("metric_raw") or ((evidence.get("semantic_tuple") or {}).get("metric") or {}).get("raw") or "")
        if raw_metric in METRIC_MAP:
            normalized = METRIC_MAP[raw_metric]
            evidence.setdefault("metric_raw", raw_metric)
            evidence["metric_normalized"] = normalized
            metric_tuple = evidence.setdefault("semantic_tuple", {}).setdefault("metric", {})
            metric_tuple.setdefault("raw", raw_metric)
            metric_tuple["normalized"] = normalized
            metric_tuple["normalization_basis"] = METRIC_BASIS
            evidence["metric_canonical"] = evidence.get("metric") or metric_tuple.get("canonical")
            evidence["metric_normalization_basis"] = METRIC_BASIS
    output["entity_ocr_canonicalization_final"] = audit
    return output, audit
