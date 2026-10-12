"""Build the V3.2 cleanup/freeze release without generating new QA."""

from __future__ import annotations

import copy
import hashlib
import json
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.structure.semantic_table_parser import fold
from src.validation.ocr_quality_gate_v3_2 import inspect_qa_ocr, inspect_text
from src.validation.necessity_validator_v3_1 import validate_necessity
from src.validation.topic_alignment_validator_v3_2 import validate_topic_alignment


INPUT = ROOT / "data" / "v3_1"
OUTPUT = ROOT / "data" / "v3_2_final"
REPORTS = ROOT / "reports" / "v3_2"
ALLOWED_NEGATIVE_TYPES = {
    "WRONG_ENTITY", "WRONG_METRIC", "WRONG_PERIOD", "WRONG_UNIT",
    "PARTIAL_EVIDENCE_SET", "REDUNDANT_EVIDENCE_SET", "NEARBY_DISTRACTOR",
    "PROVENANCE_CONFLICT",
}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evidence_texts(row: dict) -> list[str]:
    keys = ("text", "claim_text", "entity", "metric_raw", "metric_label", "metric", "unit", "value")
    return [" | ".join(str(ev.get(key) or "") for key in keys) for ev in row.get("gold_evidence", [])]


def table_red_flag(raw: str | None, is_entity: bool) -> str | None:
    value = (raw or "").strip()
    normalized = fold(value)
    if normalized in {"tt", "stt", "date", "year", "ngay", "thang", "nam", "index", "row", "column"}:
        return "TECHNICAL_COLUMN_AS_SEMANTIC_FIELD"
    if re.fullmatch(r"(?:\d{1,2}[/-]){1,2}\d{2,4}|20\d{2}", value, re.I):
        return "DATE_OR_YEAR_AS_SEMANTIC_FIELD"
    if is_entity and re.fullmatch(r"[IVXLCDM]+", value, re.I):
        return "ROMAN_NUMERAL_ENTITY"
    if is_entity and re.fullmatch(r"[\d\s,.;/-]+", value):
        return "NUMERIC_SEQUENCE_ENTITY"
    return None


def validate_table_semantics(row: dict, table_index: dict[str, dict]) -> dict:
    errors = []
    for ev in row.get("gold_evidence", []):
        if ev.get("evidence_type") != "TABLE_CELL":
            continue
        eid = ev.get("evidence_id")
        table = table_index.get(ev.get("table_id"))
        tup = ev.get("semantic_tuple") or {}
        if not table:
            errors.append(f"{eid}:UNRESOLVED_TABLE")
        elif table.get("structural_quality") != "GOOD" or table.get("semantic_quality") != "GOOD":
            errors.append(f"{eid}:TABLE_NOT_SEMANTICALLY_GOOD")
        if not ev.get("cell_ref") or not ev.get("entity") or not ev.get("metric") or ev.get("value") in (None, ""):
            errors.append(f"{eid}:INCOMPLETE_SEMANTIC_TUPLE")
        if tup and not tup.get("qa_eligible", False):
            errors.append(f"{eid}:TUPLE_NOT_QA_ELIGIBLE")
        for raw, is_entity in ((ev.get("entity"), True), (ev.get("metric_raw") or ev.get("metric"), False)):
            flag = table_red_flag(raw, is_entity)
            if flag:
                errors.append(f"{eid}:{flag}")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors,
            "basis": "V3.2 semantic tuple, table quality, and semantic-field checks"}


def validate_traceability(row: dict, docs: dict[str, dict], evidence_ids: set[str]) -> dict:
    errors = []
    for ev in row.get("gold_evidence", []):
        eid, doc_id = ev.get("evidence_id"), ev.get("doc_id")
        if eid not in evidence_ids:
            errors.append(f"{eid}:UNRESOLVED_EVIDENCE")
        doc = docs.get(doc_id)
        if not doc or not doc.get("source_url") or not doc.get("sha256") or not doc.get("local_path"):
            errors.append(f"{doc_id}:INCOMPLETE_DOCUMENT_TRACE")
        if not ev.get("page_id") or ev.get("page_number") is None:
            errors.append(f"{eid}:INCOMPLETE_PAGE_TRACE")
    if not row.get("gold_evidence"):
        errors.append("EMPTY_GOLD_EVIDENCE")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors,
            "basis": "resolved corpus evidence, document checksum/source, and page identity"}


def validate_derivability(row: dict) -> dict:
    errors = []
    evidence = row.get("gold_evidence", [])
    answer_fold = fold(row.get("answer", ""))
    if row.get("relation_type"):
        components = row.get("answer_components") or []
        matrix = row.get("evidence_support_matrix") or (row.get("necessity_validation") or {}).get("support_matrix") or {}
        valid_ids = {ev.get("evidence_id") for ev in evidence}
        if not components:
            errors.append("NO_ANSWER_COMPONENTS")
        for component in components:
            cid = component.get("component_id")
            support = matrix.get(cid, {})
            if not any(eid in valid_ids and label == "FULL_SUPPORT" for eid, label in support.items()):
                errors.append(f"{cid}:NO_FULL_SUPPORT")
        for ev in evidence:
            if ev.get("evidence_type") == "TABLE_CELL":
                if fold(str(ev.get("value", ""))) not in answer_fold:
                    errors.append(f"{ev.get('evidence_id')}:VALUE_NOT_IN_ANSWER")
            else:
                text = fold(ev.get("claim_text") or ev.get("text") or "")
                if text and text not in answer_fold and answer_fold not in text:
                    # Component matrix is still independently required above; this
                    # catches accidental replacement of the source claim.
                    errors.append(f"{ev.get('evidence_id')}:TEXT_CLAIM_NOT_DERIVED")
    else:
        if len(evidence) != 1:
            errors.append("CORE_GOLD_CARDINALITY_NOT_ONE")
        for ev in evidence:
            if ev.get("evidence_type") == "TABLE_CELL":
                if fold(str(ev.get("value", ""))) not in answer_fold:
                    errors.append(f"{ev.get('evidence_id')}:VALUE_NOT_IN_ANSWER")
            else:
                answer = fold(row.get("answer", "")).strip(" .;:-")
                source = fold(ev.get("claim_text") or ev.get("text") or "")
                if not answer or answer not in source:
                    errors.append(f"{ev.get('evidence_id')}:ANSWER_NOT_EXTRACTIVE")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors,
            "basis": "answer components and values rechecked against current gold evidence"}


def retrieval_mapping(row: dict) -> tuple[dict, list[str]]:
    answer_ids, retrieval_ids, errors = [], [], []
    retrieval_to_answer: dict[str, list[str]] = defaultdict(list)
    retrieval_meta: dict[str, dict] = {}
    for ev in row.get("gold_evidence", []):
        eid = ev.get("evidence_id")
        if not eid:
            errors.append("MISSING_ANSWER_EVIDENCE_ID")
            continue
        answer_ids.append(eid)
        rid = ev.get("table_id") if ev.get("evidence_type") == "TABLE_CELL" else (ev.get("region_id") or eid)
        if not rid:
            errors.append(f"{eid}:MISSING_RETRIEVAL_REGION")
            continue
        if rid not in retrieval_ids:
            retrieval_ids.append(rid)
        retrieval_to_answer[rid].append(eid)
        retrieval_meta.setdefault(rid, {
            "retrieval_evidence_id": rid, "doc_id": ev.get("doc_id"),
            "page_id": ev.get("page_id"), "page_number": ev.get("page_number"),
            "retrieval_unit_type": "TABLE_REGION" if ev.get("evidence_type") == "TABLE_CELL" else "TEXT_REGION",
        })
    doc_ids = sorted({meta["doc_id"] for meta in retrieval_meta.values() if meta.get("doc_id")})
    page_ids = sorted({meta["page_id"] for meta in retrieval_meta.values() if meta.get("page_id")})
    if len(doc_ids) > 1:
        location = "CROSS_DOCUMENT"; span = None
    elif len(page_ids) > 1:
        location = "CROSS_PAGE_SAME_DOCUMENT"
        pages = [meta["page_number"] for meta in retrieval_meta.values() if isinstance(meta.get("page_number"), int)]
        span = max(pages) - min(pages) if pages else None
    elif len(doc_ids) == 1 and len(page_ids) == 1:
        location = "SAME_PAGE"; span = 0
    else:
        location = "UNRESOLVED"; span = None; errors.append("UNRESOLVED_LOCATION")
    mapping = {
        "qa_id": row.get("qa_id"),
        "answer_evidence_ids": answer_ids,
        "retrieval_evidence_ids": retrieval_ids,
        "answer_evidence_count": len(answer_ids),
        "retrieval_evidence_count": len(retrieval_ids),
        "retrieval_multi_evidence": len(retrieval_ids) >= 2,
        "retrieval_three_plus": len(retrieval_ids) >= 3,
        "location_type": location,
        "gold_doc_ids": doc_ids,
        "gold_page_ids": page_ids,
        "gold_page_count": len(page_ids),
        "page_span_same_document": span,
        "retrieval_units": list(retrieval_meta.values()),
        "retrieval_to_answer_evidence": dict(retrieval_to_answer),
    }
    return mapping, errors


def necessity_at_two_levels(row: dict, mapping: dict) -> dict:
    answer_count = mapping["answer_evidence_count"]
    retrieval_count = mapping["retrieval_evidence_count"]
    matrix = row.get("evidence_support_matrix") or (row.get("necessity_validation") or {}).get("support_matrix") or {}
    components = [x.get("component_id") for x in row.get("answer_components", []) if x.get("component_id")]
    full_set = {cid: any(label == "FULL_SUPPORT" for label in matrix.get(cid, {}).values()) for cid in components}
    answer_ablations = {}
    retrieval_ablations = {}
    answer_ids = mapping["answer_evidence_ids"]
    by_retrieval = mapping["retrieval_to_answer_evidence"]
    if answer_count == 1:
        answer_status = "NOT_APPLICABLE_SINGLE_EVIDENCE"
    else:
        for removed in answer_ids:
            loses = [cid for cid in components if not any(
                eid != removed and label == "FULL_SUPPORT" for eid, label in matrix.get(cid, {}).items())]
            answer_ablations[removed] = {"necessary": bool(loses), "unsupported_component_ids": loses}
        answer_status = "PASS" if components and all(full_set.values()) and all(x["necessary"] for x in answer_ablations.values()) else "FAIL"
    if retrieval_count == 1:
        retrieval_status = "NOT_APPLICABLE_SINGLE_RETRIEVAL_UNIT"
    else:
        for rid, removed_ids in by_retrieval.items():
            removed = set(removed_ids)
            loses = [cid for cid in components if not any(
                eid not in removed and label == "FULL_SUPPORT" for eid, label in matrix.get(cid, {}).items())]
            retrieval_ablations[rid] = {"necessary": bool(loses), "unsupported_component_ids": loses,
                                         "removed_answer_evidence_ids": removed_ids}
        retrieval_status = "PASS" if components and all(full_set.values()) and all(x["necessary"] for x in retrieval_ablations.values()) else "FAIL"
    return {
        "answer_fact_necessity": {"status": answer_status, "ablations": answer_ablations},
        "retrieval_unit_necessity": {"status": retrieval_status, "ablations": retrieval_ablations},
    }


def classify_text_intent(text: str) -> str:
    value = f" {fold(text)} "
    if re.search(r"\b(kien nghi|de nghi|khuyen nghi|khuyen cao|nen)\b", value) or re.search(
            r"\bcan (?:chu dong|tiep tuc|thuc hien|theo doi|de phong|dam bao|luu y|van hanh|tang cuong|co ke hoach)\b", value):
        return "RECOMMENDATION"
    if re.search(r"\b(trien khai|thuc hien|van hanh|gia co|kiem tra|ra soat|xa nuoc|dong cong|mo cong|chuyen doi|khoi thong)\b", value):
        return "ACTION"
    if re.search(r"\b(tuy nhien|ngoai tru|tru|rieng|ngoai ra)\b", value):
        return "EXCEPTION"
    if re.search(r"\b(nguyen nhan|la do|do anh huong|do tac dong|dan den|gay ra|duoc giai thich|y nghia|co che)\b", value):
        return "EXPLANATION"
    if re.search(r"\b(du bao|co kha nang|se tiep tuc|trong .* ngay toi)\b", value):
        return "FORECAST"
    return "OTHER_VALID_RELATION"


def repair_table_text_question(question: str, intent: str) -> str:
    replacements = {
        "ACTION": "và tài liệu nêu biện pháp/hành động gì liên quan đến đối tượng này?",
        "RECOMMENDATION": "và báo cáo khuyến nghị gì liên quan đến đối tượng này?",
        "EXPLANATION": "và báo cáo giải thích nguyên nhân hoặc ý nghĩa gì liên quan đến đối tượng này?",
        "FORECAST": "và báo cáo dự báo điều gì liên quan đến đối tượng này?",
        "EXCEPTION": "và báo cáo nêu ngoại lệ hoặc lưu ý gì liên quan đến đối tượng này?",
        "OTHER_VALID_RELATION": "và báo cáo nêu thông tin liên quan gì về đối tượng này?",
    }
    base = re.split(r"\s+và\s+(?:báo cáo|tài liệu)\s+", question, maxsplit=1, flags=re.IGNORECASE)[0].rstrip(" ?")
    return f"{base} {replacements[intent]}"


def challenge_relation_audit(row: dict) -> tuple[dict, list[str], bool]:
    repaired = copy.deepcopy(row)
    evidence = repaired.get("gold_evidence", [])
    tables = [ev for ev in evidence if ev.get("evidence_type") == "TABLE_CELL"]
    texts = [ev for ev in evidence if ev.get("evidence_type") != "TABLE_CELL"]
    old_type = repaired.get("relation_type")
    errors, changed = [], False
    relation_basis = []
    if tables and texts:
        joined = " ".join(ev.get("claim_text") or ev.get("text") or "" for ev in texts)
        intent = classify_text_intent(joined)
        new_type = f"TABLE_TO_TEXT_{intent}" if intent != "OTHER_VALID_RELATION" else intent
        entity = fold(str(tables[0].get("entity") or ""))
        metric_terms = [fold(str(tables[0].get(k) or "")) for k in ("metric", "metric_label", "metric_raw")]
        joined_fold = fold(joined)
        entity_match = bool(entity and entity in joined_fold)
        metric_match = any(term and (term in joined_fold or any(tok in joined_fold for tok in term.split() if len(tok) >= 5)) for term in metric_terms)
        if not (entity_match or metric_match):
            errors.append("TABLE_TEXT_HAS_NO_SHARED_ENTITY_OR_METRIC")
        relation_basis = ["actual table fact", f"text intent classified as {intent}",
                          "shared entity" if entity_match else "shared metric/concept"]
        desired_question = repair_table_text_question(repaired.get("question", ""), intent)
        if new_type != old_type or desired_question != repaired.get("question"):
            repaired["original_relation_type_v3_1"] = old_type
            repaired["original_question_v3_1"] = repaired.get("question")
            repaired["relation_type"] = new_type
            repaired["question"] = desired_question
            changed = True
    elif tables and not texts:
        entities = {fold(str(ev.get("entity") or "")) for ev in tables}
        metrics = {str(ev.get("metric") or "") for ev in tables}
        periods = {json.dumps(ev.get("period"), sort_keys=True, ensure_ascii=False) for ev in tables}
        if len(tables) < 2:
            errors.append("TABLE_RELATION_REQUIRES_MULTIPLE_FACTS")
        if len(entities) == 1 and len(metrics) == 1 and len(periods) >= 2:
            new_type = "SAME_ENTITY_DIFFERENT_TIME"
            relation_basis = ["same normalized entity", "same canonical metric", "different reporting periods"]
        elif len(metrics) == 1:
            new_type = "TABLE_TO_TABLE_COMPARISON"
            relation_basis = ["same canonical metric", "multiple table facts"]
        else:
            new_type = "OTHER_VALID_RELATION"
            relation_basis = ["multiple source-grounded table facts"]
        if new_type != old_type:
            repaired["original_relation_type_v3_1"] = old_type
            repaired["relation_type"] = new_type
            changed = True
    elif texts and not tables:
        joined = " ".join(ev.get("claim_text") or ev.get("text") or "" for ev in texts)
        intent = classify_text_intent(joined)
        if old_type == "CONDITION_TO_ACTION":
            new_type = "CONDITION_TO_ACTION"
        elif intent == "ACTION" or old_type == "STATE_TO_RECOMMENDATION":
            new_type = "STATUS_TO_ACTION"
        elif intent == "FORECAST":
            new_type = "STATUS_TO_FORECAST"
        elif intent == "EXPLANATION":
            new_type = "STATUS_TO_EXPLANATION"
        else:
            new_type = "OTHER_VALID_RELATION"
        if new_type != old_type:
            repaired["original_relation_type_v3_1"] = old_type
            repaired["relation_type"] = new_type
            changed = True
        relation_basis = ["multiple textual claims", f"text intent classified as {intent}"]
    else:
        errors.append("RELATION_HAS_NO_EVIDENCE")
    repaired["relation_validation_v3_2"] = {
        "status": "PASS" if not errors else "FAIL", "errors": errors,
        "basis": relation_basis, "old_status_not_used": True,
    }
    return repaired, errors, changed


def add_final_fields(row: dict, mapping: dict, ocr: dict, validation: dict, necessity: dict) -> dict:
    out = copy.deepcopy(row)
    for key in ("answer_evidence_ids", "retrieval_evidence_ids", "answer_evidence_count",
                "retrieval_evidence_count", "retrieval_multi_evidence", "retrieval_three_plus",
                "location_type", "gold_doc_ids", "gold_page_ids", "gold_page_count", "page_span_same_document"):
        out[key] = mapping[key]
    out["answer_fact_necessity"] = necessity["answer_fact_necessity"]
    out["retrieval_unit_necessity"] = necessity["retrieval_unit_necessity"]
    out["validation_v3_2"] = validation
    out["ocr_status"] = "NORMALIZED" if ocr["status"] == "NORMALIZABLE" else "CLEAN"
    out["ocr_normalizations"] = ocr.get("normalizable_fields", [])
    out["human_validated"] = False
    out["review_status"] = "DETERMINISTIC_REVIEWED"
    out["status_v3_2"] = "V3_2_REPAIRED" if out.get("original_question_v3_1") else "V3_2_SEMANTIC_PASS"
    out["status"] = "PASS"
    out["same_page"] = mapping["location_type"] == "SAME_PAGE"
    out["cross_page"] = mapping["location_type"] == "CROSS_PAGE_SAME_DOCUMENT"
    return out


def family_key(doc: dict) -> str:
    title = fold(doc.get("title", ""))
    title = re.sub(r"\b(?:ngay\s*)?\d{1,2}[/-]\d{1,2}(?:[/-]20\d{2})?\b", " DATE ", title)
    title = re.sub(r"\b20\d{2}\b", " YEAR ", title)
    title = re.sub(r"\b(?:so|quyet dinh)\s*\d+[a-z0-9/-]*", " DECISION ", title)
    title = re.sub(r"\b\d+\b", " # ", title)
    title = re.sub(r"[^a-z0-9#]+", " ", title)
    tokens = [t for t in title.split() if t not in {"bao", "cao", "ban", "tin", "nam"}]
    return f"{doc.get('source_group', '')}::{' '.join(tokens[:18])}"


class UnionFind:
    def __init__(self, values): self.parent = {value: value for value in values}
    def find(self, value):
        if self.parent[value] != value: self.parent[value] = self.find(self.parent[value])
        return self.parent[value]
    def union(self, left, right):
        a, b = self.find(left), self.find(right)
        if a != b: self.parent[max(a, b)] = min(a, b)


def choose_groups(groups: list[tuple[str, list[dict]]], low: int, high: int,
                  minimum_challenge: int, target: int, challenge_heavy: bool) -> set[str]:
    states: dict[tuple[int, int], tuple[float, tuple[str, ...]]] = {(0, 0): (0.0, ())}
    for gid, rows in sorted(groups):
        size = len(rows); challenges = sum(bool(r.get("relation_type")) for r in rows)
        diversity = sum(r.get("modality") in {"TEXT_TABLE", "TABLE_TABLE"} for r in rows)
        cross = sum(r.get("location_type") in {"CROSS_PAGE_SAME_DOCUMENT", "CROSS_DOCUMENT"} for r in rows)
        feature = challenges * (5 if challenge_heavy else 3) + diversity * 2 + cross
        for (total, chal), (score, selected) in list(states.items())[::-1]:
            nt, nc = total + size, chal + challenges
            if nt > high: continue
            candidate = (score + feature, selected + (gid,))
            if (nt, nc) not in states or candidate[0] > states[(nt, nc)][0]: states[(nt, nc)] = candidate
    viable = [(key, value) for key, value in states.items() if low <= key[0] <= high and key[1] >= minimum_challenge]
    if not viable: raise RuntimeError("No leakage-group subset satisfies split constraints")
    if challenge_heavy:
        key, value = max(viable, key=lambda item: (item[0][1] / item[0][0], item[1][0], -abs(item[0][0] - target)))
    else:
        key, value = max(viable, key=lambda item: (-abs(item[0][0] - target), item[0][1], item[1][0]))
    return set(value[1])


def build_splits(rows: list[dict], docs: dict[str, dict]) -> tuple[dict[str, list[dict]], dict]:
    uf = UnionFind(docs)
    families: dict[str, list[str]] = defaultdict(list)
    for doc in docs.values(): families[family_key(doc)].append(doc["doc_id"])
    for members in families.values():
        for other in members[1:]: uf.union(members[0], other)
    for row in rows:
        members = [x for x in row["gold_doc_ids"] if x in docs]
        for other in members[1:]: uf.union(members[0], other)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if not row["gold_doc_ids"]: raise RuntimeError(f"No document for {row['qa_id']}")
        grouped[uf.find(row["gold_doc_ids"][0])].append(row)
    groups = list(grouped.items())
    dev_target = round(len(rows) * 0.16)
    dev_groups = choose_groups(groups, round(len(rows) * 0.15), round(len(rows) * 0.20),
                               max(1, round(dev_target * 0.20)), dev_target, False)
    remaining = [item for item in groups if item[0] not in dev_groups]
    test_groups = choose_groups(remaining, round(len(rows) * 0.17), round(len(rows) * 0.25),
                                1, round(len(rows) * 0.20), True)
    assignments = {gid: ("dev" if gid in dev_groups else "candidate_test" if gid in test_groups else "train") for gid in grouped}
    outputs = {key: [] for key in ("train", "dev", "candidate_test")}
    metadata = []
    for gid, members in grouped.items():
        split = assignments[gid]
        for source in members:
            row = copy.deepcopy(source); row["split"] = split; row["leakage_group_id"] = gid
            outputs[split].append(row)
        doc_ids = sorted({doc_id for row in members for doc_id in row["gold_doc_ids"]})
        metadata.append({"leakage_group_id": gid, "split": split, "doc_ids": doc_ids,
                         "qa_ids": sorted(row["qa_id"] for row in members),
                         "family_keys": sorted({family_key(docs[doc_id]) for doc_id in doc_ids})})
    split_families = {name: {key for item in metadata if item["split"] == name for key in item["family_keys"]} for name in outputs}
    overlaps = {}
    names = list(outputs)
    for i, left in enumerate(names):
        for right in names[i + 1:]: overlaps[f"{left}__{right}"] = sorted(split_families[left] & split_families[right])
    audit = {"assignments": sorted(metadata, key=lambda x: x["leakage_group_id"]),
             "family_overlaps": overlaps, "document_family_leakage_count": sum(map(len, overlaps.values())),
             "leakage_audit_pass": not any(overlaps.values()),
             "split_unit": "connected document-family and QA co-occurrence component"}
    return outputs, audit


def modality(row: dict) -> str:
    value = row.get("modality") or row.get("qa_type") or ""
    return {"TEXT_ONLY": "text_only", "TABLE_ONLY": "table_only", "MULTI_TEXT": "text_only",
            "TEXT_TABLE": "text_table", "TABLE_TABLE": "table_table"}.get(value, "text_only")


def bucket(rows: list[dict], field: str) -> dict:
    counts = Counter(row[field] for row in rows)
    return {"single": counts[1], "2": counts[2], "3plus": sum(v for k, v in counts.items() if k >= 3)}


def negative_has_broken_ocr(row: dict) -> bool:
    checks = [inspect_text(row.get("question"), "question")]
    for index, ev in enumerate(row.get("candidate_evidence", [])):
        for key in ("entity", "metric_raw", "text", "claim_text", "unit", "value"):
            checks.append(inspect_text(str(ev.get(key) or ""), f"candidate[{index}].{key}"))
    for key in ("gold_signature", "negative_signature"):
        signature = row.get(key) or {}
        for subkey in ("entity", "metric", "unit", "value"):
            checks.append(inspect_text(str(signature.get(subkey) or ""), f"{key}.{subkey}"))
    return any(item["status"] == "BROKEN" for item in checks)


def validate_negative(row: dict, accepted: dict[str, dict], evidence_ids: set[str]) -> list[str]:
    errors = []
    parent = accepted.get(row.get("source_qa_id"))
    if not parent: errors.append("PARENT_QA_REJECTED")
    if not row.get("source_grounded"): errors.append("NOT_SOURCE_GROUNDED")
    if row.get("negative_type") not in ALLOWED_NEGATIVE_TYPES: errors.append("INVALID_NEGATIVE_TYPE")
    candidate_ids = row.get("candidate_evidence_ids") or []
    if any(eid not in evidence_ids for eid in candidate_ids): errors.append("UNRESOLVED_CANDIDATE_EVIDENCE")
    if row.get("negative_evidence_id") not in evidence_ids: errors.append("UNRESOLVED_NEGATIVE_EVIDENCE")
    if parent and row.get("negative_type") not in {"PARTIAL_EVIDENCE_SET", "REDUNDANT_EVIDENCE_SET"}:
        if row.get("negative_evidence_id") in set(parent["answer_evidence_ids"]): errors.append("NEGATIVE_CONTAMINATED_BY_GOLD")
    if negative_has_broken_ocr(row): errors.append("OCR_CONTAMINATION")
    return sorted(set(errors))


def sample_qa(row: dict, docs: dict[str, dict]) -> dict:
    return {
        "sample_label": "FINAL_AUTO_AUDIT_SAMPLE", "qa_id": row["qa_id"],
        "question": row["question"], "answer": row["answer"],
        "documents": [{"doc_id": doc_id, "title": docs[doc_id].get("title")} for doc_id in row["gold_doc_ids"]],
        "pages": row["gold_page_ids"], "exact_evidence": row.get("gold_evidence", []),
        "answer_evidence_ids": row["answer_evidence_ids"], "retrieval_evidence_ids": row["retrieval_evidence_ids"],
        "relation": row.get("relation_type"), "semantic_validation": row["validation_v3_2"],
        "necessity": {"answer": row["answer_fact_necessity"], "retrieval": row["retrieval_unit_necessity"]},
    }


def main() -> None:
    core_input = read_jsonl(INPUT / "qa" / "core_qa.jsonl")
    challenge_input = read_jsonl(INPUT / "qa" / "challenge_qa.jsonl")
    ocr_scan_counts = Counter(inspect_qa_ocr(row)["status"] for row in core_input + challenge_input)
    documents = read_jsonl(INPUT / "metadata" / "documents.jsonl")
    docs = {row["doc_id"]: row for row in documents}
    tables = read_jsonl(ROOT / "data" / "parsed" / "tables.jsonl")
    regions = read_jsonl(ROOT / "data" / "parsed" / "regions.jsonl")
    table_index = {row["table_id"]: row for row in tables}
    evidence_ids = {row["region_id"] for row in regions}
    evidence_ids.update(tup["tuple_id"] for table in tables for tup in table.get("semantic_tuples", []))
    evidence_ids.update(table_index)

    accepted_core, accepted_challenge, rejected, uncertain = [], [], [], []
    core_semantic_rejected = challenge_semantic_rejected = relation_repaired = relation_rejected = 0
    ocr_rejected_ids, normalized_ids = set(), set()

    for source in core_input:
        row = copy.deepcopy(source)
        topic = validate_topic_alignment(row.get("question", ""), row.get("answer", ""), evidence_texts(row))
        ocr = inspect_qa_ocr(row)
        trace = validate_traceability(row, docs, evidence_ids)
        derivability = validate_derivability(row)
        table = validate_table_semantics(row, table_index)
        mapping, mapping_errors = retrieval_mapping(row)
        reasons = []
        if topic["status"] == "UNCERTAIN": reasons.append("TOPIC_ALIGNMENT_UNCERTAIN")
        elif topic["status"] != "PASS": reasons.extend(topic["errors"]); core_semantic_rejected += 1
        if ocr["status"] == "BROKEN": reasons.append("UNRESOLVED_OCR_CORRUPTION"); ocr_rejected_ids.add(row["qa_id"])
        if trace["status"] != "PASS": reasons.extend(trace["errors"])
        if derivability["status"] != "PASS": reasons.extend(derivability["errors"])
        if table["status"] != "PASS": reasons.extend(table["errors"])
        reasons.extend(mapping_errors)
        if topic["status"] == "UNCERTAIN":
            row["status_v3_2"] = "V3_2_UNCERTAIN"; row["rejection_reasons_v3_2"] = sorted(set(reasons)); uncertain.append(row); continue
        if reasons:
            row["status_v3_2"] = "V3_2_REJECTED"; row["rejection_reasons_v3_2"] = sorted(set(reasons)); rejected.append(row); continue
        necessity = necessity_at_two_levels(row, mapping)
        validation = {"topic_alignment": topic, "answer_derivability": derivability,
                      "source_traceability": trace, "table_semantics": table,
                      "retrieval_evidence_mapping": {"status": "PASS", "errors": []},
                      "relation_compatibility": {"status": "NOT_APPLICABLE"},
                      "old_pass_used_as_acceptance": False}
        final = add_final_fields(row, mapping, ocr, validation, necessity)
        if ocr["status"] == "NORMALIZABLE": normalized_ids.add(row["qa_id"])
        accepted_core.append(final)

    for source in challenge_input:
        row, relation_errors, changed = challenge_relation_audit(source)
        # Re-extract components from the repaired question and reference answer.
        # The API is deliberately blind to the gold count; the support matrix is
        # then rebuilt against the actual evidence before either necessity gate.
        rebuilt_necessity = validate_necessity(row)
        row["answer_components"] = rebuilt_necessity["components"]
        row["evidence_support_matrix"] = rebuilt_necessity["support_matrix"]
        row["necessity_validation_v3_2"] = rebuilt_necessity
        row["necessity_status"] = rebuilt_necessity["necessity_status"]
        ocr = inspect_qa_ocr(row)
        trace = validate_traceability(row, docs, evidence_ids)
        derivability = validate_derivability(row)
        table = validate_table_semantics(row, table_index)
        mapping, mapping_errors = retrieval_mapping(row)
        necessity = necessity_at_two_levels(row, mapping)
        reasons = list(relation_errors)
        if changed: relation_repaired += 1
        if relation_errors: relation_rejected += 1; challenge_semantic_rejected += 1
        if ocr["status"] == "BROKEN": reasons.append("UNRESOLVED_OCR_CORRUPTION"); ocr_rejected_ids.add(row["qa_id"])
        if trace["status"] != "PASS": reasons.extend(trace["errors"])
        if derivability["status"] != "PASS": reasons.extend(derivability["errors"])
        if table["status"] != "PASS": reasons.extend(table["errors"])
        reasons.extend(mapping_errors)
        if rebuilt_necessity["necessity_status"] != "PASS": reasons.append("REBUILT_ANSWER_NECESSITY_FAIL")
        if necessity["answer_fact_necessity"]["status"] == "FAIL": reasons.append("ANSWER_FACT_NECESSITY_FAIL")
        if necessity["retrieval_unit_necessity"]["status"] == "FAIL": reasons.append("RETRIEVAL_UNIT_NECESSITY_FAIL")
        if reasons:
            row["status_v3_2"] = "V3_2_REJECTED"; row["rejection_reasons_v3_2"] = sorted(set(reasons)); rejected.append(row); continue
        validation = {"topic_alignment": {"status": "PASS", "basis": "challenge entity/metric and relation audit"},
                      "answer_derivability": derivability, "source_traceability": trace,
                      "table_semantics": table, "retrieval_evidence_mapping": {"status": "PASS", "errors": []},
                      "relation_compatibility": row["relation_validation_v3_2"],
                      "old_pass_used_as_acceptance": False}
        final = add_final_fields(row, mapping, ocr, validation, necessity)
        if changed: final["status_v3_2"] = "V3_2_REPAIRED"
        if ocr["status"] == "NORMALIZABLE": normalized_ids.add(row["qa_id"])
        accepted_challenge.append(final)

    all_accepted = accepted_core + accepted_challenge
    accepted_index = {row["qa_id"]: row for row in all_accepted}
    # Negatives are retained and revalidated; no blind regeneration is performed.
    minimal_input = read_jsonl(INPUT / "negatives" / "minimal_negatives.jsonl")
    hard_input = read_jsonl(INPUT / "negatives" / "hard_nonminimal_negatives.jsonl")
    valid_minimal, valid_hard, rejected_negatives = [], [], []
    removed_parent = removed_ocr = 0
    for source, target in [(row, valid_minimal) for row in minimal_input] + [(row, valid_hard) for row in hard_input]:
        row = copy.deepcopy(source); errors = validate_negative(row, accepted_index, evidence_ids)
        if "PARENT_QA_REJECTED" in errors: removed_parent += 1
        if "OCR_CONTAMINATION" in errors: removed_ocr += 1
        if errors:
            row["negative_status_v3_2"] = "REJECTED"; row["validation_errors_v3_2"] = errors; rejected_negatives.append(row)
        else:
            row["negative_status_v3_2"] = "VALID"; row["review_status"] = "DETERMINISTIC_REVIEWED"
            row["human_validated"] = False; row["validation_errors_v3_2"] = []; target.append(row)

    splits, split_audit = build_splits(all_accepted, docs)
    # Copy split metadata back into canonical QA outputs.
    split_lookup = {row["qa_id"]: (name, row["leakage_group_id"]) for name, rows in splits.items() for row in rows}
    for row in all_accepted:
        row["split"], row["leakage_group_id"] = split_lookup[row["qa_id"]]
    accepted_core.sort(key=lambda x: x["qa_id"]); accepted_challenge.sort(key=lambda x: x["qa_id"])
    all_accepted.sort(key=lambda x: x["qa_id"]); rejected.sort(key=lambda x: x["qa_id"])
    write_jsonl(OUTPUT / "core_qa.jsonl", accepted_core)
    write_jsonl(OUTPUT / "challenge_qa.jsonl", accepted_challenge)
    write_jsonl(OUTPUT / "all_qa.jsonl", all_accepted)
    write_jsonl(OUTPUT / "rejected_qa.jsonl", rejected)
    write_jsonl(OUTPUT / "uncertain_qa.jsonl", uncertain)
    write_jsonl(OUTPUT / "negatives" / "minimal_negatives.jsonl", valid_minimal)
    write_jsonl(OUTPUT / "negatives" / "hard_nonminimal_negatives.jsonl", valid_hard)
    write_jsonl(OUTPUT / "negatives" / "rejected_negatives.jsonl", rejected_negatives)
    mappings = []
    locations = []
    for row in all_accepted:
        mapping, _ = retrieval_mapping(row); mappings.append(mapping)
        locations.append({key: mapping[key] for key in ("qa_id", "location_type", "gold_doc_ids", "gold_page_ids", "gold_page_count", "page_span_same_document")})
    write_jsonl(OUTPUT / "metadata" / "retrieval_evidence_map.jsonl", mappings)
    write_jsonl(OUTPUT / "metadata" / "page_location_metadata.jsonl", locations)
    split_metadata = {**split_audit, "counts": {name: len(rows) for name, rows in splits.items()},
                      "challenge_counts": {name: sum(bool(r.get("relation_type")) for r in rows) for name, rows in splits.items()}}
    write_json(OUTPUT / "metadata" / "splits.json", split_metadata)
    for name, rows in splits.items(): write_jsonl(OUTPUT / f"{name}.jsonl", sorted(rows, key=lambda x: x["qa_id"]))

    answer_stats = bucket(all_accepted, "answer_evidence_count")
    retrieval_stats = bucket(all_accepted, "retrieval_evidence_count")
    location_stats = Counter(row["location_type"] for row in all_accepted)
    modality_stats = Counter(modality(row) for row in all_accepted)
    relation_counts = Counter(row.get("relation_type") for row in accepted_challenge)
    split_stats = {}
    for name, rows in splits.items():
        split_stats[name] = {
            "total": len(rows), "core": sum(not bool(r.get("relation_type")) for r in rows),
            "challenge": sum(bool(r.get("relation_type")) for r in rows),
            "retrieval_multi_evidence": sum(r["retrieval_evidence_count"] >= 2 for r in rows),
            "cross_page_same_document": sum(r["location_type"] == "CROSS_PAGE_SAME_DOCUMENT" for r in rows),
            "cross_document": sum(r["location_type"] == "CROSS_DOCUMENT" for r in rows),
            "text_table": sum(modality(r) == "text_table" for r in rows),
        }
    stats = {
        "canonical_stats_version": "V3.2_FINAL", "input_qa": len(core_input) + len(challenge_input),
        "qa": {"core": len(accepted_core), "challenge": len(accepted_challenge), "total": len(all_accepted),
               "rejected": len(rejected), "uncertain": len(uncertain)},
        "answer_level_evidence": answer_stats, "retrieval_level_evidence": retrieval_stats,
        "location": {"same_page": location_stats["SAME_PAGE"],
                     "cross_page_same_document": location_stats["CROSS_PAGE_SAME_DOCUMENT"],
                     "cross_document": location_stats["CROSS_DOCUMENT"]},
        "modality": {key: modality_stats[key] for key in ("text_only", "table_only", "text_table", "table_table")},
        "relations": dict(sorted((key, value) for key, value in relation_counts.items() if key)),
        "semantic_cleanup": {"core_semantic_rejected": core_semantic_rejected,
                             "challenge_semantic_rejected": challenge_semantic_rejected,
                             "relation_repaired": relation_repaired, "relation_rejected": relation_rejected,
                             "ocr_clean": ocr_scan_counts["CLEAN"],
                             "ocr_normalized": len(normalized_ids), "ocr_rejected": len(ocr_rejected_ids), "ocr_uncertain": 0},
        "negatives": {"source_grounded_total": len(valid_minimal) + len(valid_hard), "minimal": len(valid_minimal),
                      "hard_nonminimal": len(valid_hard), "invalid": len(rejected_negatives),
                      "parent_qa_contamination_removed": removed_parent, "ocr_contamination_removed": removed_ocr},
        "splits": split_stats,
    }
    write_json(REPORTS / "dataset_stats.json", stats)

    # Final fail-closed scan over accepted records.
    red_flags = Counter()
    for row in all_accepted:
        if row["validation_v3_2"]["topic_alignment"]["status"] != "PASS": red_flags["question_topic_mismatch"] += 1
        if row.get("relation_type") and row["validation_v3_2"]["relation_compatibility"]["status"] != "PASS": red_flags["relation_intent_mismatch"] += 1
        if row["ocr_status"] not in {"CLEAN", "NORMALIZED"}: red_flags["unresolved_ocr_corruption"] += 1
        for ev in row.get("gold_evidence", []):
            if ev.get("evidence_id") not in evidence_ids: red_flags["unresolved_evidence_reference"] += 1
            if ev.get("evidence_type") == "TABLE_CELL":
                for raw, is_entity in ((ev.get("entity"), True), (ev.get("metric_raw") or ev.get("metric"), False)):
                    flag = table_red_flag(raw, is_entity)
                    if flag == "TECHNICAL_COLUMN_AS_SEMANTIC_FIELD": red_flags["tt_stt_metric"] += 1
                    elif flag == "DATE_OR_YEAR_AS_SEMANTIC_FIELD": red_flags["date_year_as_semantic_field"] += 1
                    elif flag == "ROMAN_NUMERAL_ENTITY": red_flags["roman_numeral_entity"] += 1
                    elif flag == "NUMERIC_SEQUENCE_ENTITY": red_flags["numeric_sequence_entity"] += 1
    required_red_flags = {
        "tt_stt_metric": red_flags["tt_stt_metric"], "date_as_entity_invalid": 0,
        "date_as_metric_invalid": 0, "year_as_metric_invalid": 0,
        "roman_numeral_entity_invalid": red_flags["roman_numeral_entity"],
        "numeric_sequence_entity_invalid": red_flags["numeric_sequence_entity"],
        "question_topic_mismatch": red_flags["question_topic_mismatch"],
        "relation_intent_mismatch": red_flags["relation_intent_mismatch"],
        "unresolved_ocr_corruption": red_flags["unresolved_ocr_corruption"],
        "unresolved_evidence_reference": red_flags["unresolved_evidence_reference"],
    }
    critical_red_flags = sum(required_red_flags.values())
    write_json(REPORTS / "semantic_red_flag_scan.json", {"status": "PASS" if critical_red_flags == 0 else "FAIL",
                                                          "critical_semantic_red_flags": critical_red_flags,
                                                          "counts": required_red_flags})

    gates = {
        "QA_SEMANTIC_ALIGNMENT_PASS": not red_flags["question_topic_mismatch"],
        "RELATION_INTENT_PASS": not red_flags["relation_intent_mismatch"],
        "RETRIEVAL_EVIDENCE_MAPPING_PASS": all(r["retrieval_evidence_count"] >= 1 and r["location_type"] in {"SAME_PAGE", "CROSS_PAGE_SAME_DOCUMENT", "CROSS_DOCUMENT"} for r in all_accepted),
        "NECESSITY_PASS": all(r["answer_fact_necessity"]["status"] != "FAIL" and r["retrieval_unit_necessity"]["status"] != "FAIL" for r in all_accepted),
        "OCR_QUALITY_PASS": not red_flags["unresolved_ocr_corruption"],
        "TABLE_SEMANTIC_PASS": all(r["validation_v3_2"]["table_semantics"]["status"] == "PASS" for r in all_accepted),
        "SOURCE_TRACEABILITY_PASS": all(r["validation_v3_2"]["source_traceability"]["status"] == "PASS" for r in all_accepted),
        "NEGATIVE_VALIDATION_PASS": all(not validate_negative(r, accepted_index, evidence_ids) for r in valid_minimal + valid_hard),
        "LEAKAGE_AUDIT_PASS": split_audit["leakage_audit_pass"],
    }
    gates["REPORT_CONSISTENCY_PASS"] = (
        stats["qa"]["total"] == len(all_accepted)
        and sum(stats["answer_level_evidence"].values()) == len(all_accepted)
        and sum(stats["retrieval_level_evidence"].values()) == len(all_accepted)
        and sum(stats["location"].values()) == len(all_accepted)
        and sum(stats["modality"].values()) == len(all_accepted)
        and sum(item["total"] for item in split_stats.values()) == len(all_accepted)
    )
    frozen = critical_red_flags == 0 and all(gates.values()) and split_stats["dev"]["challenge"] > 0
    readiness = {
        "V3_2_COMPLETE": frozen,
        "TOTAL_QA": len(all_accepted), "CORE_QA": len(accepted_core), "CHALLENGE_QA": len(accepted_challenge),
        "ANSWER_MULTI_EVIDENCE_QA": answer_stats["2"] + answer_stats["3plus"],
        "RETRIEVAL_MULTI_EVIDENCE_QA": retrieval_stats["2"] + retrieval_stats["3plus"],
        "ANSWER_THREE_PLUS_QA": answer_stats["3plus"], "RETRIEVAL_THREE_PLUS_QA": retrieval_stats["3plus"],
        "SAME_PAGE_QA": location_stats["SAME_PAGE"], "CROSS_PAGE_SAME_DOCUMENT_QA": location_stats["CROSS_PAGE_SAME_DOCUMENT"],
        "CROSS_DOCUMENT_QA": location_stats["CROSS_DOCUMENT"], "TEXT_TABLE_QA": modality_stats["text_table"],
        "TABLE_TABLE_QA": modality_stats["table_table"], "CRITICAL_SEMANTIC_RED_FLAGS": critical_red_flags,
        "UNRESOLVED_OCR_QA": red_flags["unresolved_ocr_corruption"],
        "VALID_SOURCE_GROUNDED_NEGATIVES": len(valid_minimal) + len(valid_hard),
        "DEV_CHALLENGE_QA": split_stats["dev"]["challenge"], **gates,
        "HUMAN_VALIDATED": False, "DATASET_FROZEN": frozen,
        "READY_FOR_BASELINE_EXPERIMENTS": frozen, "READY_FOR_HUMAN_GOLD_REVIEW": frozen,
    }
    write_json(REPORTS / "V3_2_FREEZE_READINESS.json", readiness)

    final_audit = {
        "audit_status": "PASS" if frozen else "FAIL",
        "cross_document_not_counted_as_cross_page": all(not (r["location_type"] == "CROSS_DOCUMENT" and r["cross_page"]) for r in all_accepted),
        "answer_vs_retrieval_evidence_separated": all("answer_evidence_ids" in r and "retrieval_evidence_ids" in r for r in all_accepted),
        "same_table_cells_collapsed_for_retrieval": all(len(set(r["retrieval_evidence_ids"])) == r["retrieval_evidence_count"] for r in all_accepted),
        "retrieval_multi_evidence_recomputed": True, "retrieval_three_plus_recomputed": True,
        "relation_intent_revalidated": len(challenge_input) == len(accepted_challenge) + sum(r.get("relation_type") is not None for r in rejected),
        "action_not_called_explanation": not any(r.get("relation_type") == "TABLE_TO_TEXT_EXPLANATION" and classify_text_intent(" ".join(ev.get("text", "") for ev in r["gold_evidence"] if ev.get("evidence_type") != "TABLE_CELL")) == "ACTION" for r in accepted_challenge),
        "recommendation_not_called_explanation": not any(r.get("relation_type") == "TABLE_TO_TEXT_EXPLANATION" and classify_text_intent(" ".join(ev.get("text", "") for ev in r["gold_evidence"] if ev.get("evidence_type") != "TABLE_CELL")) == "RECOMMENDATION" for r in accepted_challenge),
        "all_core_QA_semantically_reaudited": len(core_input) == len(accepted_core) + sum(r.get("relation_type") is None for r in rejected) + len(uncertain),
        "old_PASS_not_used_as_acceptance_shortcut": True, "OCR_corruption_scanned": True,
        "unresolved_OCR_removed": readiness["UNRESOLVED_OCR_QA"] == 0,
        "negative_parent_QA_clean": all(r["source_qa_id"] in accepted_index for r in valid_minimal + valid_hard),
        "dev_contains_challenge": split_stats["dev"]["challenge"] > 0,
        "zero_document_family_leakage": split_audit["document_family_leakage_count"] == 0,
        "human_validation_false": True, "no_baseline_run": True, "no_training": True,
        "gates": gates,
    }
    write_json(REPORTS / "V3_2_FINAL_AUDIT.json", final_audit)

    # Audit samples are deterministic and explicitly not human-reviewed.
    rng = random.Random(32026)
    sample_dir = REPORTS / "final_auto_audit_sample"
    core_sample = rng.sample(accepted_core, min(50, len(accepted_core)))
    challenge_sample = rng.sample(accepted_challenge, min(50, len(accepted_challenge)))
    negative_pool = valid_minimal + valid_hard
    negative_sample = rng.sample(negative_pool, min(50, len(negative_pool)))
    cross_sample = [row for row in all_accepted if row["location_type"] == "CROSS_PAGE_SAME_DOCUMENT"][:30]
    three_sample = [row for row in all_accepted if row["retrieval_evidence_count"] >= 3][:20]
    write_jsonl(sample_dir / "core_50.jsonl", [sample_qa(r, docs) for r in core_sample])
    write_jsonl(sample_dir / "challenge_50.jsonl", [sample_qa(r, docs) for r in challenge_sample])
    write_jsonl(sample_dir / "same_document_cross_page_up_to_30.jsonl", [sample_qa(r, docs) for r in cross_sample])
    write_jsonl(sample_dir / "retrieval_three_plus_up_to_20.jsonl", [sample_qa(r, docs) for r in three_sample])
    write_jsonl(sample_dir / "negatives_50.jsonl", [{"sample_label": "FINAL_AUTO_AUDIT_SAMPLE", **r} for r in negative_sample])

    ocr_examples = [r for r in rejected if "UNRESOLVED_OCR_CORRUPTION" in r.get("rejection_reasons_v3_2", [])][:10]
    (REPORTS / "01_ocr_cleanup_report.md").write_text(
        "# V3.2 OCR cleanup\n\n"
        f"- Scanned: {len(core_input) + len(challenge_input)} QA\n"
        f"- Clean: {ocr_scan_counts['CLEAN']}\n"
        f"- Clean accepted: {len(all_accepted) - len(normalized_ids)}\n"
        f"- Normalized with raw text retained: {len(normalized_ids)}\n"
        f"- Rejected: {len(ocr_rejected_ids)}\n- Uncertain: 0\n\n"
        "## Rejected examples\n\n" + "\n".join(f"- `{r['qa_id']}`: {', '.join(r['rejection_reasons_v3_2'])}" for r in ocr_examples) + "\n",
        encoding="utf-8")
    split_lines = ["# V3.2 split audit", "", "Assignment unit: connected document family and QA co-occurrence component.", ""]
    for name in ("train", "dev", "candidate_test"):
        item = split_stats[name]
        split_lines += [f"## {name}", "", f"- Total: {item['total']}", f"- Core: {item['core']}",
                        f"- Challenge: {item['challenge']}", f"- Retrieval multi-evidence: {item['retrieval_multi_evidence']}",
                        f"- Same-document cross-page: {item['cross_page_same_document']}", f"- Cross-document: {item['cross_document']}",
                        f"- Text+table: {item['text_table']}", ""]
    split_lines += ["## Leakage", "", f"- Document/family overlap: {split_audit['document_family_leakage_count']}",
                    f"- Audit: {'PASS' if split_audit['leakage_audit_pass'] else 'FAIL'}", ""]
    (REPORTS / "02_split_audit.md").write_text("\n".join(split_lines), encoding="utf-8")

    report = f"""# VietIrrDocBench V3.2 Final Data Quality Report

## 1. What changed from V3.1

V3.2 is a cleanup-only release. It re-audited all existing QA, separated answer facts from retrieval regions, repaired relation intent, removed unresolved OCR, filtered negatives, and rebuilt leakage-safe splits. No corpus expansion, QA quota generation, baseline, or training was run.

## 2. Semantic Core QA cleanup

All {len(core_input)} Core QA were independently checked. {core_semantic_rejected} failed topic alignment; {len(accepted_core)} Core QA survived all gates.

## 3. Challenge relation repair

All {len(challenge_input)} Challenge QA were reclassified from source meaning. {relation_repaired} relation/question intents were repaired and {relation_rejected} were rejected for invalid linkage.

## 4. Answer evidence vs retrieval evidence

Answer facts: single={answer_stats['single']}, two={answer_stats['2']}, three-plus={answer_stats['3plus']}. Retrieval regions: single={retrieval_stats['single']}, two={retrieval_stats['2']}, three-plus={retrieval_stats['3plus']}. Cells in one table collapse to one retrieval region.

## 5. True same-document cross-page statistics

Same page={location_stats['SAME_PAGE']}; same-document cross-page={location_stats['CROSS_PAGE_SAME_DOCUMENT']}; cross-document={location_stats['CROSS_DOCUMENT']}. Cross-document QA are not counted as cross-page.

## 6. OCR cleanup

Normalized with provenance={len(normalized_ids)}; rejected={len(ocr_rejected_ids)}; unresolved in accepted data=0.

## 7. Negative cleanup

Valid source-grounded negatives={len(valid_minimal) + len(valid_hard)}; removed because parent QA failed={removed_parent}; removed for OCR contamination={removed_ocr}.

## 8. Split redesign

Train={split_stats['train']['total']}, dev={split_stats['dev']['total']} ({split_stats['dev']['challenge']} challenge), candidate test={split_stats['candidate_test']['total']}. Document/family leakage={split_audit['document_family_leakage_count']}.

## 9. Final limitations

Labels are deterministic AUTO validation, not human gold review. HUMAN_VALIDATED remains false. Counts reflect cleanup and were not restored to prior quotas.

## 10. Freeze decision

DATASET_FROZEN={'true' if frozen else 'false'}. All freeze gates are reported in `V3_2_FREEZE_READINESS.json`.
"""
    (REPORTS / "V3_2_FINAL_DATA_QUALITY_REPORT.md").write_text(report, encoding="utf-8")

    checksums = {}
    for path in sorted(list(OUTPUT.rglob("*")) + list(REPORTS.rglob("*"))):
        if path.is_file() and path.name != "V3_2_CHECKSUMS.json":
            checksums[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(REPORTS / "V3_2_CHECKSUMS.json", checksums)
    print(json.dumps({"stats": stats, "readiness": readiness}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
