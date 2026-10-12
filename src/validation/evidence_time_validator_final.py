"""Source-prioritized evidence-time validation for the final semantic patch."""

from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date
from typing import Any


ALLOWED_TIME_TYPES = {
    "OBSERVATION_DATE", "MEASUREMENT_DATE", "FORECAST_DATE", "REFERENCE_PERIOD",
    "COMPARISON_PERIOD", "REPORT_DATE", "RANGE", "UNKNOWN",
}


def fold(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "")).lower()
    return "".join(c for c in text if unicodedata.category(c) != "Mn").replace("\u0111", "d")


def metric_raw(evidence: dict) -> str:
    tup = evidence.get("semantic_tuple") or {}
    return str(evidence.get("metric_raw") or (tup.get("metric") or {}).get("raw") or
               evidence.get("metric_label") or evidence.get("metric") or "")


def _iso(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _document_time(evidence: dict) -> dict:
    period = evidence.get("period") or {}
    return {"raw": period.get("raw"), "normalized_start": period.get("start"),
            "normalized_end": period.get("end"), "basis": period.get("basis") or "evidence period metadata"}


def _year_from_document(document_time: dict) -> int | None:
    for key in ("normalized_start", "normalized_end"):
        value = document_time.get(key)
        if isinstance(value, str) and re.match(r"^\d{4}-", value):
            return int(value[:4])
    match = re.search(r"\b(20\d{2})\b", str(document_time.get("raw") or ""))
    return int(match.group(1)) if match else None


def _header_time(raw: str, year_hint: int | None) -> dict | None:
    value = fold(raw)
    range_match = re.search(
        r"(\d{1,2})/(\d{1,2})(?:/(20\d{2}))?\s*(?:-|den|\u00f7)\s*(?:\d{1,2}h\s*)?(\d{1,2})/(\d{1,2})(?:/(20\d{2}))?",
        value,
    )
    if range_match:
        d1, m1, y1, d2, m2, y2 = range_match.groups()
        year = int(y2 or y1 or year_hint or 0)
        start = _iso(int(y1 or year), int(m1), int(d1))
        end = _iso(int(y2 or year), int(m2), int(d2))
        if start and end:
            return {"raw": range_match.group(0), "normalized_start": start, "normalized_end": end,
                    "source": "semantic_tuple.metric.raw", "source_priority": 1}
    month_match = re.search(r"thang\s+(\d{1,2})/(20\d{2})", value)
    if month_match:
        month, year = map(int, month_match.groups())
        return {"raw": month_match.group(0), "normalized_start": _iso(year, month, 1),
                "normalized_end": _iso(year, month, calendar.monthrange(year, month)[1]),
                "source": "semantic_tuple.metric.raw", "source_priority": 1}
    point_matches = list(re.finditer(r"(?<!\d)(\d{1,2})/(\d{1,2})(?:/(20\d{2}))?(?!\d)", value))
    if point_matches:
        match = point_matches[-1]
        day, month, year = match.groups()
        year = int(year or year_hint or 0)
        normalized = _iso(year, int(month), int(day))
        if normalized:
            return {"raw": match.group(0), "normalized_start": normalized, "normalized_end": normalized,
                    "source": "semantic_tuple.metric.raw", "source_priority": 1}
    return None


def annotate_evidence_time(evidence: dict, allow_reference_period: bool = True) -> dict:
    document_time = _document_time(evidence)
    raw = metric_raw(evidence)
    raw_fold = fold(raw)
    extracted = _header_time(raw, _year_from_document(document_time))
    if extracted:
        if "thuc do" in raw_fold:
            time_type = "OBSERVATION_DATE"
        elif "du bao" in raw_fold:
            time_type = "FORECAST_DATE"
        elif extracted["normalized_start"] != extracted["normalized_end"]:
            time_type = "RANGE"
        elif "so sanh" in raw_fold or "luy tich" in raw_fold:
            time_type = "COMPARISON_PERIOD"
        else:
            time_type = "MEASUREMENT_DATE"
        status = "PASS"
        evidence_time = {**extracted, "normalization_basis": "explicit date/range in metric header"}
    else:
        tuple_time = ((evidence.get("semantic_tuple") or {}).get("time") or {})
        tuple_raw = tuple_time.get("raw")
        tuple_extracted = _header_time(str(tuple_raw or ""), _year_from_document(document_time)) if tuple_raw else None
        if tuple_extracted:
            evidence_time = {**tuple_extracted, "source": "semantic_tuple.time.raw", "source_priority": 2,
                             "normalization_basis": "explicit semantic tuple time"}
            time_type, status = "MEASUREMENT_DATE", "PASS"
        elif allow_reference_period and document_time.get("normalized_start") and document_time.get("normalized_end") and (
                document_time["normalized_start"] != document_time["normalized_end"]):
            evidence_time = {**document_time, "source": "explicit report reference period", "source_priority": 5,
                             "normalization_basis": "metric has no point date; value is indexed by the explicit report period"}
            time_type, status = "REFERENCE_PERIOD", "PASS"
        else:
            evidence_time = None
            time_type, status = "UNKNOWN", "UNCERTAIN"
    return {"status": status, "document_reporting_time": document_time,
            "evidence_time": evidence_time, "time_type": time_type, "metric_raw": raw}


def _dates_in_text(text: str) -> set[str]:
    value = fold(text)
    results: set[str] = set()
    for day, month, year in re.findall(r"ngay\s+(\d{1,2})\s+thang\s+(\d{1,2})\s+nam\s+(20\d{2})", value):
        normalized = _iso(int(year), int(month), int(day))
        if normalized:
            results.add(normalized)
    for day, month, year in re.findall(r"(?<!\d)(\d{1,2})/(\d{1,2})/(20\d{2})(?!\d)", value):
        normalized = _iso(int(year), int(month), int(day))
        if normalized:
            results.add(normalized)
    return results


def _descriptor(raw: str, fallback: str) -> str:
    value = fold(raw)
    if "muc nuoc lon nhat thuc do" in value:
        return "m\u1ef1c n\u01b0\u1edbc l\u1edbn nh\u1ea5t th\u1ef1c \u0111o"
    if "muc nuoc lon nhat du bao" in value:
        return "m\u1ef1c n\u01b0\u1edbc l\u1edbn nh\u1ea5t d\u1ef1 b\u00e1o"
    if "dung tich cuoi thang" in value:
        return "t\u1ef7 l\u1ec7 dung t\u00edch cu\u1ed1i th\u00e1ng d\u1ef1 b\u00e1o so v\u1edbi thi\u1ebft k\u1ebf"
    if "dung tich cuoi tuan" in value:
        return "t\u1ef7 l\u1ec7 dung t\u00edch cu\u1ed1i tu\u1ea7n d\u1ef1 b\u00e1o so v\u1edbi thi\u1ebft k\u1ebf"
    if "dien tich dap ung" in value:
        return "di\u1ec7n t\u00edch \u0111\u00e1p \u1ee9ng"
    return fallback or "gi\u00e1 tr\u1ecb"


def _time_phrase(annotation: dict) -> str:
    item = annotation["evidence_time"]
    start, end = item["normalized_start"], item["normalized_end"]
    if start == end:
        year, month, day = start.split("-")
        return f"ng\u00e0y {int(day):02d}/{int(month):02d}/{year}"
    raw = item.get("raw") or ""
    if re.search(r"thang\s+\d{1,2}/20\d{2}", fold(raw)):
        month, year = re.search(r"(\d{1,2})/(20\d{2})", fold(raw)).groups()
        return f"th\u00e1ng {int(month):02d}/{year}"
    sy, sm, sd = start.split("-")
    ey, em, ed = end.split("-")
    if sy == ey and sm == em and sd == "01" and int(ed) >= 28:
        return f"th\u00e1ng {int(sm):02d}/{sy}"
    return f"t\u1eeb {int(sd):02d}/{int(sm):02d}/{sy} \u0111\u1ebfn {int(ed):02d}/{int(em):02d}/{ey}"


def _expected_dates(annotations: list[dict]) -> set[str]:
    return {a["evidence_time"]["normalized_start"] for a in annotations
            if a.get("evidence_time") and a["evidence_time"]["normalized_start"] == a["evidence_time"]["normalized_end"]}


def validate_qa_time(row: dict) -> dict:
    if row.get("relation_type") != "SAME_ENTITY_DIFFERENT_TIME":
        return {"status": "SKIP_NOT_APPLICABLE", "evidence": [], "errors": [],
                "proposed_question": None, "proposed_answer": None}
    evidence = row.get("gold_evidence") or []
    annotations = [annotate_evidence_time(item) for item in evidence]
    errors = []
    if any(item["status"] != "PASS" or not item.get("evidence_time") for item in annotations):
        errors.append("MISSING_REQUIRED_EVIDENCE_TIME")
        return {"status": "UNCERTAIN", "evidence": annotations, "errors": errors,
                "proposed_question": None, "proposed_answer": None}
    expected_points = _expected_dates(annotations)
    question_points = _dates_in_text(row.get("question", ""))
    answer_points = _dates_in_text(row.get("answer", ""))
    point_question_mismatch = bool(expected_points and expected_points != question_points)
    point_answer_mismatch = bool(expected_points and expected_points != answer_points)
    period_phrases = [_time_phrase(item) for item in annotations
                      if item["evidence_time"]["normalized_start"] != item["evidence_time"]["normalized_end"]]
    question_fold, answer_fold = fold(row.get("question")), fold(row.get("answer"))
    period_question_mismatch = any(fold(phrase) not in question_fold for phrase in period_phrases)
    period_answer_mismatch = any(fold(phrase) not in answer_fold for phrase in period_phrases)
    if point_question_mismatch or period_question_mismatch:
        errors.append("QUESTION_TIME_MISMATCH")
    if point_answer_mismatch or period_answer_mismatch:
        errors.append("ANSWER_TIME_MISMATCH")
    if not errors:
        return {"status": "PASS", "evidence": annotations, "errors": [],
                "question_time": sorted(question_points), "answer_time": sorted(answer_points),
                "proposed_question": None, "proposed_answer": None}

    entities = [item.get("entity") or "" for item in evidence]
    if not entities or len({fold(x) for x in entities}) != 1:
        return {"status": "REJECT", "evidence": annotations,
                "errors": errors + ["ENTITY_NOT_STABLE_FOR_TEMPORAL_REPAIR"],
                "proposed_question": None, "proposed_answer": None}
    entity = entities[0]
    items, answer_sentences = [], []
    for ev, annotation in zip(evidence, annotations):
        descriptor = _descriptor(annotation["metric_raw"], ev.get("metric_label") or ev.get("metric"))
        time_phrase = _time_phrase(annotation)
        items.append(f"{descriptor} {time_phrase}")
        unit = str(ev.get("unit") or "").strip()
        # Preserve the dataset's source rendering (including the space before
        # percent) so value/unit support remains exactly traceable.
        rendered_value = f"{ev.get('value')}{(' ' + unit) if unit else ''}"
        if "dung tich cuoi" in fold(annotation["metric_raw"]):
            temporal_context = (f"trong {time_phrase}" if fold(time_phrase).startswith("thang ")
                                else f"trong giai \u0111o\u1ea1n {time_phrase}")
            answer_sentences.append(
                f"{entity} c\u00f3 t\u1ef7 l\u1ec7 dung t\u00edch tr\u1eef {rendered_value} {temporal_context}."
            )
        else:
            answer_sentences.append(f"{descriptor[:1].upper() + descriptor[1:]} {time_phrase} c\u1ee7a {entity} l\u00e0 {rendered_value}.")
    joined = " v\u00e0 ".join(items) if len(items) == 2 else ", ".join(items[:-1]) + " v\u00e0 " + items[-1]
    proposed_question = f"Theo chu\u1ed7i t\u00e0i li\u1ec7u li\u00ean quan, {joined} c\u1ee7a {entity} l\u1ea7n l\u01b0\u1ee3t l\u00e0 bao nhi\u00eau?"
    return {"status": "REPAIR", "evidence": annotations, "errors": errors,
            "question_time": sorted(question_points), "answer_time": sorted(answer_points),
            "proposed_question": proposed_question, "proposed_answer": " ".join(answer_sentences),
            "repair_basis": "metric/header evidence dates override document publication/reporting dates"}
