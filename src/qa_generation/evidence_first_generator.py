from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from src.common.io_utils import sha256_record


NUMBER = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
UNIT = re.compile(r"(?:mg/?l|m³/s|m3/s|triệu\s*m³|triệu\s*m3|m³|m3|mm|ha|%|‰|cm|\bm\b)", re.I)
FORECAST_WORDS = ("dự báo", "dự kiến", "tuần tới", "tháng tới")
OBSERVED_WORDS = ("hiện tại", "hiện trạng", "thực đo", "đã qua")
GENERIC_LABELS = {
    "tổng", "trung bình", "bình quân", "cộng", "toàn vùng", "toàn hệ thống", "ghi chú",
    "qcvn 08:2023", "qcvn", "max", "min", "tháng", "tuần", "ngày", "năm",
}
GARBLED = re.compile(r"(?:�|á»|Ã|Â|Ä|Æ|â€|\bD~|\bL9c\b|mrra|d~n|cuBi|\bVu\b|\bƣ)", re.I)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _sentences(text: str) -> list[str]:
    text = _clean(text.replace("\n", " "))
    protected = text.replace("TP.", "TP§").replace("Tp.", "Tp§").replace("T.P.", "T§P§")
    parts = re.split(r"(?<=[.!?])\s+", protected)
    restored = [part.replace("TP§", "TP.").replace("Tp§", "Tp.").replace("T§P§", "T.P.") for part in parts]
    return [_clean(part) for part in restored if 45 <= len(_clean(part)) <= 700]


def _clean_source_text(value: str) -> bool:
    value = _clean(value)
    return bool(value) and not GARBLED.search(value) and value.count("?") <= 1


def _metric_terms(text: str) -> set[str]:
    lowered = text.lower()
    groups = {
        "rainfall": ("mưa",), "water_level": ("mực nước", "mntb"),
        "flow": ("lưu lượng", "dòng chảy"), "storage": ("dung tích", "w trữ"),
        "salinity": ("độ mặn", "mặn"), "area": ("diện tích",),
        "quality": ("chất lượng", "ph", "bod", "cod", "tss", "coliform", "ni tơ", "t-n", "do "),
        "supply": ("cấp nước", "đáp ứng", "nhu cầu nước"),
    }
    return {name for name, terms in groups.items() if any(term in lowered for term in terms)}


def _unit(header: str, value: str) -> list[str]:
    return sorted(set(match.group(0) for match in UNIT.finditer(f"{header} {value}")))


def _value_type(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in FORECAST_WORDS):
        return "FORECAST"
    if any(word in lowered for word in OBSERVED_WORDS):
        return "OBSERVED"
    if any(word in lowered for word in ("ngưỡng", "giới hạn", "mức b", "qcvn")):
        return "THRESHOLD"
    if any(word in lowered for word in ("kế hoạch", "nhiệm vụ", "mục tiêu")):
        return "PLANNED"
    return "UNKNOWN"


def _metric(header: str) -> str:
    h = header.lower()
    rules = [
        ("WaterLevel", ("mực nước", "mntb")), ("ReservoirStorage", ("dung tích", "w trữ")),
        ("StoragePercentage", ("%", "tỷ lệ")), ("Inflow", ("lưu lượng đến", "dòng chảy đến")),
        ("Outflow", ("lưu lượng xả", "q xả")), ("Rainfall", ("mưa",)),
        ("Salinity", ("mặn",)), ("IrrigatedArea", ("diện tích", " ha")),
        ("WaterDemand", ("nhu cầu",)), ("WaterSupply", ("cấp nước", "đáp ứng")),
        ("WaterQuality", ("ph", "do", "bod", "cod", "tss", "coliform", "ni tơ", "t-n", "wqi")),
    ]
    for metric, keys in rules:
        if any(key in h for key in keys):
            return metric
    return header


def _period(doc: dict) -> dict:
    return doc.get("reporting_period") or {"raw_period": None, "normalized_start": None, "normalized_end": None, "period_type": "UNKNOWN"}


def _provenance(doc: dict, row_label: str, header: str, value: str) -> dict:
    period = _period(doc)
    return {
        "entities": [row_label], "reservoirs": [], "basins": doc.get("basin", []), "stations": [],
        "metrics": [_metric(header)], "periods": [period], "units": _unit(header, value),
        "document_version": doc.get("version_status"), "raw_value": value,
        "normalized_value": value, "source_basis": "table_cell", "confidence": "HIGH", "value_type": _value_type(header),
    }


def _row_label(row: list[str]) -> tuple[int, str] | None:
    for index, raw in enumerate(row[:3]):
        value = _clean(raw)
        if not value or re.fullmatch(r"\d+[.)]?", value):
            continue
        if len(value) > 120 or value.lower() in GENERIC_LABELS or not _clean_source_text(value):
            return None
        return index, value
    return None


def _explicit_entity_mention(sentence: str, label: str) -> bool:
    escaped = re.escape(label)
    patterns = (
        rf"^(?:[+\-]\s*)?{escaped}\b(?!\s*\))",
        rf"\b(?:trạm|hồ|cống|sông|kênh|đập)\s+{escaped}\b",
        rf"[.;:]\s*(?:trạm|hồ|cống|sông|kênh|đập)?\s*{escaped}\b",
    )
    return any(re.search(pattern, sentence, re.I) for pattern in patterns)


def _narrative_role(sentence: str) -> str:
    lowered = sentence.lower()
    if "kiến nghị" in lowered or "khuyến cáo" in lowered:
        return "RECOMMENDATION"
    if any(word in lowered for word in FORECAST_WORDS):
        return "FORECAST"
    if "do " in lowered or "nguyên nhân" in lowered:
        return "CAUSE"
    return "STATUS"


def _eligible_cells(table: dict) -> list[dict]:
    if table.get("quality_label") != "GOOD":
        return []
    cells: list[dict] = []
    headers = table.get("headers", [])
    for row_index, row in enumerate(table.get("rows", [])):
        labelled = _row_label(row)
        if not labelled:
            continue
        label_index, label = labelled
        for column_index, raw in enumerate(row):
            value = _clean(raw)
            header = _clean(headers[column_index] if column_index < len(headers) else "")
            if column_index == label_index or not value or not header or len(value) > 120:
                continue
            if not _clean_source_text(value) or not _clean_source_text(header):
                continue
            if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", label) and column_index < 2:
                continue
            if not NUMBER.search(value) and value.lower() not in {"đảm bảo", "không đảm bảo", "tăng", "giảm", "ổn định", "đạt", "không đạt"}:
                continue
            cells.append({"row_index": row_index, "column_index": column_index, "row_label": label, "column_label": header, "raw_cell": value})
    return cells


def _evidence(table: dict, cell: dict, doc: dict, role: str = "VALUE") -> dict:
    return {
        "region_id": f"REG_{table['table_id']}", "page_id": table["page_id"], "page_number": table["page_number"],
        "region_type": "table", "role": role, "source_text": table["normalized_representation"],
        "provenance_signature": _provenance(doc, cell["row_label"], cell["column_label"], cell["raw_cell"]),
        "table_trace": {"table_id": table["table_id"], **cell},
    }


def _base_qa(qa_id: str, doc: dict, question: str, answer: str, evidence: list[dict], components: list[dict], tags: list[str], reasoning: list[str]) -> dict:
    pages = sorted(set(item["page_number"] for item in evidence))
    result = {
        "qa_id": qa_id, "doc_id": doc["doc_id"], "question": question, "answer": answer,
        "gold_evidence": evidence, "gold_pages": pages, "gold_page_count": len(pages),
        "page_span": (max(pages) - min(pages)) if pages else 0, "same_page": len(pages) == 1,
        "cross_page": len(pages) > 1, "answer_components": components,
        "cross_section": "UNKNOWN",
        "question_types": ["factoid"], "reasoning_types": reasoning, "research_tags": tags,
        "application_tags": ["water_resource_status"], "validation_status": "PENDING", "human_status": "NOT_REVIEWED",
        "generator": "canonical_evidence_first_v1",
    }
    result["record_sha256"] = sha256_record(result)
    return result


def generate_core(documents: list[dict], tables: list[dict], limit: int = 300) -> list[dict]:
    docs = {doc["doc_id"]: doc for doc in documents if doc["acceptance_status"] == "ACCEPT"}
    per_doc: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for table in sorted(tables, key=lambda x: (x["doc_id"], x["page_number"], x["table_id"])):
        doc = docs.get(table["doc_id"])
        if not doc:
            continue
        cells = _eligible_cells(table)
        numeric = [cell for cell in cells if NUMBER.search(cell["raw_cell"])]
        for cell in (numeric or cells)[:2]:
            per_doc[doc["doc_id"]].append((table, cell))
    result: list[dict] = []
    doc_ids = sorted(per_doc)
    offsets = defaultdict(int)
    while len(result) < limit:
        progressed = False
        for doc_id in doc_ids:
            if offsets[doc_id] >= len(per_doc[doc_id]):
                continue
            progressed = True
            table, cell = per_doc[doc_id][offsets[doc_id]]
            offsets[doc_id] += 1
            doc = docs[doc_id]
            period = (_period(doc).get("raw_period") or "kỳ báo cáo của tài liệu")
            question = f"Theo {doc['title']}, trong {period}, {cell['column_label']} của {cell['row_label']} là bao nhiêu?"
            answer = f"{cell['row_label']}: {cell['column_label']} = {cell['raw_cell']}."
            component = {"component_id": "C1", "requirement": f"{cell['column_label']} của {cell['row_label']}", "answer_content": cell["raw_cell"]}
            qa_id = f"QA_CORE_{len(result)+1:05d}"
            result.append(_base_qa(qa_id, doc, question, answer, [_evidence(table, cell, doc)], [component], ["single_evidence", "table_only", "numerical"], ["table_lookup"]))
            if len(result) >= limit:
                return result
        if not progressed:
            break
    return result


def generate_text_table_challenges(documents: list[dict], tables: list[dict], regions: list[dict], limit: int = 30) -> list[dict]:
    docs = {doc["doc_id"]: doc for doc in documents if doc["acceptance_status"] == "ACCEPT"}
    paragraph_by_doc: dict[str, list[dict]] = defaultdict(list)
    for region in regions:
        if region.get("region_type") in {"paragraph", "list"}:
            paragraph_by_doc[region["doc_id"]].append(region)
    result: list[dict] = []
    used_docs: defaultdict[str, int] = defaultdict(int)
    for table in sorted(tables, key=lambda x: (x["doc_id"], x["page_number"])):
        if len(result) >= limit:
            break
        doc = docs.get(table["doc_id"])
        if not doc or used_docs[doc["doc_id"]] >= 2:
            continue
        for cell in _eligible_cells(table):
            label = cell["row_label"]
            if len(label) < 4 or label.lower() in GENERIC_LABELS:
                continue
            table_metrics = _metric_terms(cell["column_label"])
            if not table_metrics:
                continue
            candidates = []
            for region in paragraph_by_doc[doc["doc_id"]]:
                distance = abs(region["page_number"] - table["page_number"])
                if distance > 1 or label.lower() not in region["normalized_text"].lower():
                    continue
                if not (table_metrics & _metric_terms(region["normalized_text"])):
                    continue
                for sentence in _sentences(region["normalized_text"]):
                    if label.lower() not in sentence.lower() or cell["raw_cell"] in sentence:
                        continue
                    if not _explicit_entity_mention(sentence, label):
                        continue
                    if sentence in table["normalized_representation"]:
                        continue
                    if not _clean_source_text(sentence) or sentence[-1] not in ".!?;:":
                        continue
                    candidates.append((0 if distance == 1 else 1, distance, -len(sentence), region, sentence))
            if not candidates:
                continue
            _, _, _, paragraph, sentence = sorted(candidates, key=lambda x: x[:3])[0]
            period = (_period(doc).get("raw_period") or "kỳ báo cáo")
            question = f"Trong {period}, bảng ghi {cell['column_label']} của {label} là bao nhiêu, và đoạn thuyết minh liên quan nêu thông tin nào?"
            answer = f"Giá trị trong bảng: {cell['column_label']} của {label} là {cell['raw_cell']}. Thuyết minh liên quan: {sentence}"
            table_ev = _evidence(table, cell, doc)
            para_ev = {
                "region_id": paragraph["region_id"], "page_id": paragraph["page_id"], "page_number": paragraph["page_number"],
                "region_type": paragraph["region_type"], "role": _narrative_role(sentence), "source_text": paragraph["normalized_text"],
                "provenance_signature": {**_provenance(doc, label, cell["column_label"], sentence), "source_basis": "narrative_statement"},
            }
            components = [
                {"component_id": "C1", "requirement": f"{cell['column_label']} của {label}", "answer_content": cell["raw_cell"]},
                {"component_id": "C2", "requirement": f"nhận định liên quan đến {label}", "answer_content": sentence},
            ]
            tags = ["multi_evidence", "text_table", "numerical"]
            if table["page_number"] != paragraph["page_number"]:
                tags.append("cross_page")
            qa_id = f"QA_CHALLENGE_TT_{len(result)+1:04d}"
            result.append(_base_qa(qa_id, doc, question, answer, [table_ev, para_ev], components, tags, ["table_lookup", "evidence_composition"]))
            used_docs[doc["doc_id"]] += 1
            break
    return result


def generate_table_table_challenges(documents: list[dict], tables: list[dict], start_index: int = 1, limit: int = 80) -> list[dict]:
    docs = {doc["doc_id"]: doc for doc in documents if doc["acceptance_status"] == "ACCEPT"}
    grouped: dict[tuple[str, str], list[tuple[dict, dict]]] = defaultdict(list)
    for table in tables:
        for cell in _eligible_cells(table):
            grouped[(table["doc_id"], cell["row_label"].lower())].append((table, cell))
    result: list[dict] = []
    for (doc_id, _), items in sorted(grouped.items()):
        doc = docs.get(doc_id)
        if not doc:
            continue
        chosen = None
        for left_index, (left_table, left_cell) in enumerate(items):
            for right_table, right_cell in items[left_index + 1:]:
                if left_table["page_number"] == right_table["page_number"]:
                    continue
                lhead, rhead = left_cell["column_label"].lower(), right_cell["column_label"].lower()
                temporal_pair = (any(w in lhead for w in OBSERVED_WORDS) and any(w in rhead for w in FORECAST_WORDS)) or (any(w in rhead for w in OBSERVED_WORDS) and any(w in lhead for w in FORECAST_WORDS))
                shared_metric = _metric(lhead) == _metric(rhead) and _metric(lhead) not in {lhead, rhead}
                if temporal_pair or shared_metric:
                    chosen = (left_table, left_cell, right_table, right_cell, temporal_pair)
                    break
            if chosen:
                break
        if not chosen:
            continue
        lt, lc, rt, rc, temporal_pair = chosen
        label = lc["row_label"]
        question = f"Đối với {label}, tài liệu cho biết {lc['column_label']} là bao nhiêu và {rc['column_label']} là bao nhiêu?"
        answer = f"{lc['column_label']}: {lc['raw_cell']}; {rc['column_label']}: {rc['raw_cell']}."
        components = [
            {"component_id": "C1", "requirement": lc["column_label"], "answer_content": lc["raw_cell"]},
            {"component_id": "C2", "requirement": rc["column_label"], "answer_content": rc["raw_cell"]},
        ]
        qa_id = f"QA_CHALLENGE_TBT_{start_index + len(result):04d}"
        tags = ["multi_evidence", "table_table", "cross_page", "numerical"]
        if temporal_pair:
            tags.append("temporal")
        result.append(_base_qa(qa_id, doc, question, answer, [_evidence(lt, lc, doc), _evidence(rt, rc, doc)], components, tags, ["comparison", "evidence_composition"]))
        if len(result) >= limit:
            break
    return result


def generate_candidates(documents: list[dict], tables: list[dict], regions: list[dict]) -> tuple[list[dict], list[dict]]:
    core = generate_core(documents, tables)
    text_table = generate_text_table_challenges(documents, tables, regions)
    table_table = generate_table_table_challenges(documents, tables, start_index=len(text_table) + 1)
    return core, text_table + table_table
