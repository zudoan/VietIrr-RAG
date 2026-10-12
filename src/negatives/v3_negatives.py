"""Build provenance-aware V3 hard negatives from validated positive QA."""

from __future__ import annotations

import copy
import hashlib
import re
from typing import Any

from src.structure.semantic_table_parser import clean, fold


VALID_ALT_METRICS = ["WaterLevel", "Discharge", "Rainfall", "ReservoirStorage", "Area", "Salinity", "WaterDemand"]
VALID_ALT_ENTITIES = ["hồ Hòa Bình", "hồ Sơn La", "hệ thống Bắc Hưng Hải", "lưu vực sông Hương", "Đồng bằng sông Cửu Long"]
VALID_ALT_UNITS = ["m", "m3/s", "mm", "m3", "ha", "mg/L", "%"]


def stable_int(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)


def replace_ci(text: str, old: str, new: str) -> str:
    if old and re.search(re.escape(old), text, re.I):
        return re.sub(re.escape(old), new, text, count=1, flags=re.I)
    return f"{text.rstrip('?')} (đối với {new})?"


def build_minimal(qa_rows: list[dict]) -> list[dict]:
    negatives = []
    for idx, qa in enumerate(qa_rows):
        sig = copy.deepcopy(qa["provenance_signatures"][0])
        original = copy.deepcopy(sig)
        mode = idx % 4
        mutation_type = "WRONG_ENTITY"
        question = qa["question"]
        if mode == 0:
            current = clean(sig["entity"]["raw"])
            alt = next(v for v in VALID_ALT_ENTITIES if fold(v) != fold(current))
            sig["entity"] = {"raw": alt, "canonical": fold(alt), "confidence": 1.0, "basis": "controlled valid-domain counterfactual"}
            question = replace_ci(question, current, alt)
        elif mode == 1:
            mutation_type = "WRONG_METRIC"
            current = sig["metric"]["canonical"]
            alt = next(v for v in VALID_ALT_METRICS if v != current)
            sig["metric"] = {"raw": alt, "canonical": alt, "confidence": 1.0, "basis": "controlled valid-domain counterfactual"}
            question = f"{question.rstrip('?')} [chỉ số yêu cầu: {alt}]?"
        elif mode == 2 and sig.get("period", {}).get("start"):
            mutation_type = "WRONG_PERIOD"
            current_year = int(sig["period"]["start"][:4])
            alt_year = 2023 if current_year != 2023 else 2024
            sig["period"] = {"raw": f"năm {alt_year}", "start": f"{alt_year}-01-01", "end": f"{alt_year}-12-31", "confidence": 1.0, "basis": "controlled valid period counterfactual"}
            question = f"{question.rstrip('?')} (trong năm {alt_year})?"
        elif mode == 3 and sig.get("value_type") == "NUMERIC" and sig.get("unit", {}).get("normalized"):
            mutation_type = "WRONG_UNIT"
            current = sig["unit"]["normalized"]
            alt = next(v for v in VALID_ALT_UNITS if v != current)
            sig["unit"] = {"raw": alt, "normalized": alt, "confidence": 1.0, "basis": "controlled valid-unit counterfactual"}
            question = f"{question.rstrip('?')} (trả lời theo {alt})?"
        else:
            current = clean(sig["entity"]["raw"])
            alt = next(v for v in VALID_ALT_ENTITIES if fold(v) != fold(current))
            sig["entity"] = {"raw": alt, "canonical": fold(alt), "confidence": 1.0, "basis": "controlled valid-domain counterfactual"}
            question = replace_ci(question, current, alt)
        negatives.append({
            "negative_id": f"V3_NEG_MIN_{len(negatives)+1:05d}", "source_qa_id": qa["qa_id"],
            "negative_type": mutation_type, "question": question, "candidate_evidence": qa["gold_evidence"],
            "candidate_evidence_ids": qa["gold_evidence_ids"], "expected_label": "NEGATIVE",
            "original_signature": original, "counterfactual_signature": sig,
            "mutation_dimensions": [mutation_type.removeprefix("WRONG_").lower()],
            "minimal_counterfactual": True, "semantic_validation": "PENDING", "human_validated": False,
        })
    return negatives


def build_partial(challenge: list[dict]) -> list[dict]:
    rows = []
    for qa in challenge:
        removed = qa["gold_evidence"][-1]
        kept = qa["gold_evidence"][:-1]
        rows.append({
            "negative_id": f"V3_NEG_PART_{len(rows)+1:05d}", "source_qa_id": qa["qa_id"],
            "negative_type": "PARTIAL_EVIDENCE_SET", "question": qa["question"],
            "candidate_evidence": kept, "candidate_evidence_ids": [e["evidence_id"] for e in kept],
            "removed_evidence_id": removed["evidence_id"], "unsupported_component_ids": [qa["answer_components"][-1]["component_id"]],
            "expected_label": "NEGATIVE", "minimal_counterfactual": False, "human_validated": False,
        })
    return rows


def build_redundant(challenge: list[dict], all_qa: list[dict]) -> list[dict]:
    pool = [e for qa in all_qa for e in qa["gold_evidence"]]
    rows = []
    for qa in challenge:
        distractor = next((e for e in pool if e["doc_id"] != qa["doc_id"]), None)
        if not distractor:
            continue
        candidate = qa["gold_evidence"] + [distractor]
        rows.append({
            "negative_id": f"V3_NEG_RED_{len(rows)+1:05d}", "source_qa_id": qa["qa_id"],
            "negative_type": "REDUNDANT_EVIDENCE_SET", "question": qa["question"],
            "candidate_evidence": candidate, "candidate_evidence_ids": [e["evidence_id"] for e in candidate],
            "redundant_evidence_id": distractor["evidence_id"], "expected_label": "NEGATIVE",
            "minimal_counterfactual": False, "human_validated": False,
        })
    return rows

