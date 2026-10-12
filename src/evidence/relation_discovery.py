"""Discover explicit, source-grounded evidence relations for V3.1.

No candidate is created from page distance, region order, hash rotation, or
same-document membership alone. Every returned relation has a semantic bridge.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Iterable

from src.structure.semantic_table_parser import clean, fold


METRIC_LABELS = {
    "WaterLevel": ("mực nước", ("muc nuoc", "cao trinh")),
    "Discharge": ("lưu lượng", ("luu luong", "dong chay")),
    "Rainfall": ("lượng mưa", ("luong mua",)),
    "ReservoirStorage": ("dung tích trữ", ("dung tich", "tru luong")),
    "Area": ("diện tích", ("dien tich",)),
    "Salinity": ("độ mặn", ("do man", "xam nhap man")),
    "Temperature": ("nhiệt độ", ("nhiet do",)),
    "PH": ("pH", ("ph",)),
    "DissolvedOxygen": ("oxy hòa tan", ("oxy hoa tan", " do ")),
    "BOD": ("BOD", ("bod",)), "COD": ("COD", ("cod",)), "TSS": ("TSS", ("tss",)),
    "Ammonium": ("amoni", ("amoni", "nh4")), "Nitrate": ("nitrat", ("nitrat", "no3")),
    "Phosphate": ("phosphat", ("phosphat", "po4")),
    "WaterDemand": ("nhu cầu nước", ("nhu cau nuoc",)),
}

ROLE_CUES = {
    "FORECAST": ("du bao", "du kien", "tuan toi", "ky toi", "se "),
    "EXPLANATION": ("nguyen nhan", " do ", " vi ", "anh huong", "dan den", "gay "),
    "ACTION": (" can ", "de nghi", "phai ", "khuyen cao", "chu dong", "thuc hien", "yeu cau"),
    "CONDITION": (" neu ", " khi ", "trong truong hop", "dieu kien", "truong hop"),
    "EXCEPTION": (" ngoai tru", " tru ", "truong hop dac biet"),
    "RULE": ("quy dinh", "khong duoc", "duoc phep", "trach nhiem", "bat buoc"),
    "INTERPRETATION": ("cho thay", "dam bao", "bao dam", "dap ung", "thieu hut", "du nuoc"),
    "STATUS": ("hien tai", "ghi nhan", "da ", " dat ", "co xu the", "tinh hinh", "muc nuoc"),
}

BLOCKED_RELATION_ENTITIES = {
    "lon nhat", "nho nhat", "trung vi", "trung binh", "cao nhat", "thap nhat",
    "maximum", "minimum", "max", "min", "tong", "tong cong", "ho chua", "dap dang",
}

PAIR_RELATIONS = {
    ("STATUS", "EXPLANATION"): "STATUS_TO_EXPLANATION",
    ("STATUS", "FORECAST"): "STATUS_TO_FORECAST",
    ("CONDITION", "ACTION"): "CONDITION_TO_ACTION",
    ("CONDITION", "RULE"): "RULE_TO_CONDITION",
    ("RULE", "EXCEPTION"): "RULE_TO_EXCEPTION",
    ("STATUS", "ACTION"): "STATE_TO_RECOMMENDATION",
    ("INTERPRETATION", "ACTION"): "STATE_TO_RECOMMENDATION",
}


def stable_id(prefix: str, values: Iterable[str]) -> str:
    payload = "|".join(values)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:18]}"


def normalized_family(title: str, source_group: str) -> str:
    value = fold(title)
    value = re.sub(r"\b(?:20\d{2}|\d{1,2})\b", "#", value)
    value = re.sub(r"\b(?:ngay|tuan|thang|ky|dot)\s*#", "SERIES", value)
    value = re.sub(r"[^a-z0-9#]+", " ", value)
    tokens = [t for t in value.split() if t not in {"bao", "cao", "ban", "tin", "nam"}]
    return f"{source_group}::{' '.join(tokens[:14])}"


def exact_period(doc: dict) -> dict:
    title = clean(doc.get("title"))
    m = re.search(r"ngày\s*(\d{1,2})\s*tháng\s*(\d{1,2})\s*năm\s*(20\d{2})", title, re.I)
    if m:
        day, month, year = map(int, m.groups())
        iso = f"{year:04d}-{month:02d}-{day:02d}"
        return {"raw": m.group(0), "start": iso, "end": iso, "confidence": 0.99, "basis": "explicit document-title date"}
    period = doc.get("document_reporting_period") or {}
    return {
        "raw": period.get("raw_period"), "start": period.get("normalized_start"),
        "end": period.get("normalized_end"),
        "confidence": (doc.get("reporting_period_provenance") or {}).get("confidence", 0.0),
        "basis": (doc.get("reporting_period_provenance") or {}).get("source", "unresolved"),
    }


def display_unit(tup: dict) -> str:
    unit = tup.get("unit") or {}
    return "triệu m3" if unit.get("normalized") == "million_m3" else clean(unit.get("raw") or unit.get("normalized"))


def semantic_metric_label(tup: dict) -> str:
    metric = tup["metric"]["canonical"]
    raw = fold(tup["metric"].get("raw"))
    unit = (tup.get("unit") or {}).get("normalized")
    if metric == "Area":
        if "dap ung" in raw:
            return "diện tích đáp ứng"
        if "gieo trong" in raw:
            return "diện tích gieo trồng"
        if "san xuat" in raw:
            return "diện tích sản xuất"
        if "tong dien tich" in raw:
            return "tổng diện tích"
    if metric == "Rainfall" and unit == "%":
        return "mức chênh lệch lượng mưa so với kỳ đối chiếu"
    if metric == "ReservoirStorage":
        if unit == "%":
            return "tỷ lệ dung tích trữ"
        if "thiet ke" in raw:
            return "dung tích thiết kế"
        if "hien tai" in raw:
            return "dung tích hiện tại"
    return METRIC_LABELS.get(metric, (metric, ()))[0]


def make_table_evidence(table: dict, tup: dict, doc: dict) -> dict:
    period = exact_period(doc)
    entity = clean(tup["entity"]["raw"])
    metric = tup["metric"]["canonical"]
    value = clean(tup["value"]["raw"])
    unit = display_unit(tup)
    return {
        "evidence_id": tup["tuple_id"], "evidence_type": "TABLE_CELL",
        "doc_id": table["doc_id"], "document_title": doc["title"],
        "document_type": doc["document_type_v3_1"], "source_group": doc.get("source_group"),
        "page_id": table["page_id"], "page_number": table["page_number"], "table_id": table["table_id"],
        "cell_ref": tup["cell_ref"], "semantic_tuple": tup,
        "entity": entity, "entity_canonical": tup["entity"]["canonical"],
        "metric": metric, "metric_label": semantic_metric_label(tup),
        "metric_raw": clean(tup["metric"]["raw"]), "value": value,
        "unit": unit, "unit_normalized": (tup.get("unit") or {}).get("normalized"),
        "period": period, "role": "VALUE",
        "text": f"{entity} | {clean(tup['metric']['raw'])} | {value} {unit}".strip(),
    }


def valid_relation_entity(raw: str, canonical: str) -> bool:
    if fold(canonical) in BLOCKED_RELATION_ENTITIES:
        return False
    first_alpha = next((ch for ch in clean(raw) if ch.isalpha()), "")
    if first_alpha and first_alpha.islower():
        return False
    if any(mark in clean(raw) for mark in ("\\", "|", "{", "}", "~", "?", "!", ":", ";")):
        return False
    return len(re.sub(r"[^a-z0-9]", "", fold(canonical))) >= 3


def valid_sentence(value: str) -> bool:
    value = clean(value)
    if not 55 <= len(value) <= 430 or any(mark in value for mark in ("\\", "|", "{", "}", "~")):
        return False
    if "..." in value or value.count("(") != value.count(")") or value.endswith(":"):
        return False
    if not re.search(r"[.!?;]$", value):
        return False
    if sum(ch.isalpha() for ch in value) / max(len(value), 1) < 0.58:
        return False
    if len(re.findall(r"(?<!\w)\d[\d.,/%-]*", value)) > 5:
        return False
    return True


def sentence_roles(sentence: str) -> list[str]:
    padded = f" {fold(sentence)} "
    roles = []
    if "du bao" in padded and any(cue in padded for cue in (" se ", "tuan toi", "ky toi", "thoi gian toi", "co xu the", "du kien")):
        roles.append("FORECAST")
    if any(cue in padded for cue in ("nguyen nhan", "do anh huong", "do luu luong", "vi vay", "dan den", "gay ra", "la do")):
        roles.append("EXPLANATION")
    if any(cue in padded for cue in ("can chu dong", "can thuc hien", "can tang", "can giam", "de nghi", "phai ", "khuyen cao", "kien nghi", "chu dong")):
        roles.append("ACTION")
    if any(cue in padded for cue in (" neu ", " khi ", "trong truong hop", "voi dieu kien")):
        roles.append("CONDITION")
    if any(cue in padded for cue in ("ngoai tru", " tru ", "truong hop dac biet")):
        roles.append("EXCEPTION")
    if any(cue in padded for cue in ("quy dinh", "khong duoc", "duoc phep", "trach nhiem", "bat buoc")):
        roles.append("RULE")
    if any(cue in padded for cue in ("cho thay", "dam bao", "bao dam", "dap ung", "thieu hut", "du nuoc")):
        roles.append("INTERPRETATION")
    if any(cue in padded for cue in ("hien tai", "ghi nhan", " da ", " dat ", "co xu the", "tinh hinh", "muc nuoc")):
        roles.append("STATUS")
    return roles


def sentence_metric(sentence: str) -> str | None:
    padded = f" {fold(sentence)} "
    for metric, (_, cues) in METRIC_LABELS.items():
        if any(cue in padded for cue in cues):
            return metric
    return None


def region_sentences(region: dict) -> list[str]:
    text = clean(region.get("normalized_text"))
    return [s for s in (clean(x) for x in re.split(r"(?<=[.!?;])\s+", text)) if valid_sentence(s)]


def discover_relations(docs: list[dict], regions: list[dict], tables: list[dict]) -> list[dict]:
    doc_map = {doc["doc_id"]: doc for doc in docs if doc.get("document_type_v3_1") != "supporting_reference"}
    table_evidence = []
    by_table: dict[str, list[dict]] = defaultdict(list)
    entity_by_doc: dict[str, dict[str, str]] = defaultdict(dict)
    for table in tables:
        if table.get("doc_id") not in doc_map or table.get("structural_quality") != "GOOD" or table.get("semantic_quality") != "GOOD":
            continue
        for tup in table.get("semantic_tuples", []):
            if not tup.get("qa_eligible") or tup["metric"]["canonical"] not in METRIC_LABELS:
                continue
            if not valid_relation_entity(tup["entity"]["raw"], tup["entity"]["canonical"]):
                continue
            ev = make_table_evidence(table, tup, doc_map[table["doc_id"]])
            table_evidence.append(ev); by_table[table["table_id"]].append(ev)
            if len(re.sub(r"\W", "", ev["entity_canonical"])) >= 4:
                entity_by_doc[ev["doc_id"]][ev["entity_canonical"]] = ev["entity"]

    relations: list[dict] = []
    seen_sets: set[tuple[str, ...]] = set()

    def add(relation_type: str, evidence: list[dict], shared_entity: str | None, shared_metric: str | None,
            shared_period: str | None, basis: list[str], confidence: float, extra: dict | None = None) -> None:
        ids = tuple(ev["evidence_id"] for ev in evidence)
        canonical_set = tuple(sorted(ids))
        if len(ids) < 2 or len(set(ids)) != len(ids) or canonical_set in seen_sets:
            return
        row = {
            "relation_id": stable_id("REL", ids), "relation_type": relation_type,
            "evidence_ids": list(ids), "shared_entity": shared_entity, "shared_metric": shared_metric,
            "shared_period": shared_period, "relation_basis": basis,
            "relation_confidence": round(confidence, 3), "validation_status": "PENDING",
            "evidence": evidence,
        }
        if extra:
            row.update(extra)
        relations.append(row); seen_sets.add(canonical_set)

    # Same table/column context: directly comparable entities at one period.
    for table_id, evidence in by_table.items():
        groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        for ev in evidence:
            groups[(ev["metric"], ev["unit_normalized"] or "", fold(ev["metric_raw"]))].append(ev)
        for (metric, _, context), rows in groups.items():
            rows = sorted(rows, key=lambda x: x["entity_canonical"])
            comparable = [row for row in rows if row.get("entity_canonical")]
            if len(comparable) >= 3:
                triple = comparable[:3]
                if len({row["entity_canonical"] for row in triple}) == 3 and len({row["value"] for row in triple}) >= 2:
                    add("TABLE_TO_TABLE_COMPARISON", triple, None, metric,
                        triple[0]["period"].get("raw"),
                        ["same source comparative table", "same semantic metric column", "same unit and reporting context", "three named comparison entities"],
                        0.97, {"comparison_context": context, "dependency_pattern": "three-entity same-context comparison"})
            made = 0
            for left, right in zip(rows, rows[1:]):
                if left["entity_canonical"] == right["entity_canonical"] or left["value"] == right["value"]:
                    continue
                add("TABLE_TO_TABLE_COMPARISON", [left, right], None, metric,
                    left["period"].get("raw"),
                    ["same source table", "same semantic metric column", "same unit and reporting context", "different named entities"],
                    0.97, {"comparison_context": context})
                made += 1
                if made >= 4:
                    break

    # Same entity/metric in a verified document series at distinct periods.
    series_groups: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    for ev in table_evidence:
        doc = doc_map[ev["doc_id"]]
        family = normalized_family(doc["title"], doc.get("source_group", ""))
        if ev["period"].get("start"):
            series_groups[(family, ev["entity_canonical"], ev["metric"], ev["unit_normalized"] or "")].append(ev)
    for (_, entity, metric, _), rows in series_groups.items():
        unique = {}
        for ev in rows:
            unique[(ev["period"]["start"], ev["value"])] = ev
        ordered = sorted(unique.values(), key=lambda x: (x["period"]["start"], x["evidence_id"]))
        for left, right in zip(ordered, ordered[1:]):
            if left["period"]["start"] == right["period"]["start"] or left["value"] == right["value"]:
                continue
            add("SAME_ENTITY_DIFFERENT_TIME", [left, right], left["entity"], metric, None,
                ["same normalized entity", "same canonical metric and unit", "same verified document series", "distinct explicit reporting periods"], 0.98)
        if len(ordered) >= 3:
            for i in range(len(ordered) - 2):
                triple = ordered[i:i + 3]
                if len({ev["period"]["start"] for ev in triple}) == 3 and len({ev["value"] for ev in triple}) >= 2:
                    add("SAME_ENTITY_DIFFERENT_TIME", triple, triple[0]["entity"], metric, None,
                        ["same normalized entity", "same canonical metric and unit", "three explicit reporting periods", "verified time series"], 0.98,
                        {"dependency_pattern": "T1 value + T2 value + T3 value"})
                    break

    # Native-text sentences with explicit entity and discourse role.
    text_evidence: list[dict] = []
    for region in regions:
        doc_id = region.get("doc_id")
        if doc_id not in doc_map or region.get("text_extraction") != "NATIVE_TEXT" or not region.get("qa_eligible"):
            continue
        entities = entity_by_doc.get(doc_id, {})
        for index, sentence in enumerate(region_sentences(region)):
            fs = fold(sentence)
            anchors = [(canonical, raw) for canonical, raw in entities.items() if canonical in fs]
            metric = sentence_metric(sentence)
            roles = sentence_roles(sentence)
            if not roles or (not anchors and not metric):
                continue
            text_evidence.append({
                "evidence_id": region["region_id"], "claim_id": f"{region['region_id']}_S{index:02d}",
                "evidence_type": "TEXT_REGION", "doc_id": doc_id, "document_title": doc_map[doc_id]["title"],
                "document_type": doc_map[doc_id]["document_type_v3_1"], "source_group": doc_map[doc_id].get("source_group"),
                "page_id": region["page_id"], "page_number": region["page_number"],
                "section_id": region.get("section_id"), "text": region["normalized_text"],
                "claim_text": sentence, "roles": roles, "role": roles[0], "metric": metric,
                "anchors": [{"canonical": c, "raw": r} for c, r in anchors],
                "period": exact_period(doc_map[doc_id]),
            })

    # Table-to-text only with an explicit entity and metric bridge.
    texts_by_doc: dict[str, list[dict]] = defaultdict(list)
    for ev in text_evidence:
        texts_by_doc[ev["doc_id"]].append(ev)
    per_doc_tt = defaultdict(int)
    for tev in table_evidence:
        if per_doc_tt[tev["doc_id"]] >= 10:
            continue
        for text_ev in texts_by_doc.get(tev["doc_id"], []):
            anchor_names = {a["canonical"] for a in text_ev["anchors"]}
            if tev["entity_canonical"] not in anchor_names or text_ev.get("metric") != tev["metric"]:
                continue
            roles = set(text_ev["roles"])
            if "FORECAST" in roles:
                rel_type = "TABLE_TO_TEXT_FORECAST"
            elif roles & {"EXPLANATION", "INTERPRETATION", "ACTION"}:
                rel_type = "TABLE_TO_TEXT_EXPLANATION"
            else:
                continue
            add(rel_type, [tev, text_ev], tev["entity"], tev["metric"], tev["period"].get("raw"),
                ["same normalized entity explicitly present in text", "same canonical metric explicitly present in text", f"text discourse role: {text_ev['role']}"], 0.94)
            per_doc_tt[tev["doc_id"]] += 1
            break

    # Complementary text roles must share a concrete entity anchor.
    anchored: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for ev in text_evidence:
        for anchor in ev["anchors"]:
            anchored[(ev["doc_id"], anchor["canonical"])].append(ev)
    per_anchor = defaultdict(int)
    for (doc_id, anchor), rows in anchored.items():
        if len(rows) < 2:
            continue
        role_index: dict[str, list[dict]] = defaultdict(list)
        for ev in rows:
            for role in ev["roles"]:
                role_index[role].append(ev)
        raw_anchor = next(a["raw"] for ev in rows for a in ev["anchors"] if a["canonical"] == anchor)
        for (role_a, role_b), rel_type in PAIR_RELATIONS.items():
            if per_anchor[(doc_id, anchor)] >= 2:
                break
            match = next(((a, b) for a in role_index.get(role_a, []) for b in role_index.get(role_b, [])
                          if a["evidence_id"] != b["evidence_id"] and a["claim_text"] != b["claim_text"]), None)
            if not match:
                continue
            left, right = match
            add(rel_type, [left, right], raw_anchor, left.get("metric") or right.get("metric"), None,
                ["same normalized named entity", f"complementary discourse roles: {role_a} -> {role_b}", "source-verbatim claims"], 0.91)
            per_anchor[(doc_id, anchor)] += 1

    return relations
