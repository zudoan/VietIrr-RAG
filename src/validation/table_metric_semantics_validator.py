"""Validate that table questions preserve the complete source metric meaning.

The validator is deliberately narrower than a general paraphrase model.  It
uses deterministic source-header signatures and only proposes a repair when
the intended metric is unambiguous and the numeric answer/evidence can remain
unchanged.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.validation.ocr_quality_gate_v3_2_final import KNOWN_RECONSTRUCTIONS


def fold(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "")).lower()
    text = "".join(c for c in text if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"\s+", " ", text).strip()


def metric_raw(evidence: dict) -> str:
    tup = evidence.get("semantic_tuple") or {}
    raw = evidence.get("metric_raw") or (tup.get("metric") or {}).get("raw")
    return str(raw or evidence.get("metric_label") or evidence.get("metric") or "")


def _signature(raw: str) -> dict:
    normalized = KNOWN_RECONSTRUCTIONS.get(raw, (raw, None))[0]
    value = fold(normalized)

    rules = (
        (r"cao trinh day cong", "BOTTOM_ELEVATION_GATE", "cao trình đáy cống", ("cao trinh", "day", "cong")),
        (r"cao trinh day", "BOTTOM_ELEVATION", "cao trình đáy", ("cao trinh", "day")),
        (r"muc nuoc lon nhat du bao", "WATER_LEVEL_MAX_FORECAST", "mực nước lớn nhất dự báo", ("lon nhat", "du bao")),
        (r"muc nuoc lon nhat thuc do", "WATER_LEVEL_MAX_OBSERVED", "mực nước lớn nhất thực đo", ("lon nhat", "thuc do")),
        (r"du bao muc nuoc trieu.*max", "TIDAL_LEVEL_MAX_FORECAST", "mực nước triều lớn nhất dự báo", ("trieu", "lon nhat", "du bao")),
        (r"muc nuoc bq thang", "WATER_LEVEL_MONTHLY_MEAN", "mực nước bình quân tháng", ("binh quan", "thang")),
        (r"do man max", "SALINITY_MAX", "độ mặn lớn nhất", ("lon nhat",)),
        (r"dung tich hien tai so voi thiet ke", "STORAGE_CURRENT_VS_DESIGN", "tỷ lệ dung tích hiện tại so với thiết kế", ("hien tai", "so voi thiet ke")),
        (r"dung tich cuoi thang so voi tk", "STORAGE_END_MONTH_FORECAST_VS_DESIGN", "tỷ lệ dung tích cuối tháng dự báo so với thiết kế", ("cuoi thang", "du bao", "so voi thiet ke")),
        (r"dung tich cuoi tuan so voi tk", "STORAGE_END_WEEK_FORECAST_VS_DESIGN", "tỷ lệ dung tích cuối tuần dự báo so với thiết kế", ("cuoi tuan", "du bao", "so voi thiet ke")),
        (r"dung tich cuoi vu so voi tk", "STORAGE_END_SEASON_FORECAST_VS_DESIGN", "tỷ lệ dung tích cuối vụ dự báo so với thiết kế", ("cuoi vu", "du bao", "so voi thiet ke")),
        (r"dung tich so voi thiet ke", "STORAGE_VS_DESIGN", "tỷ lệ dung tích so với thiết kế", ("so voi thiet ke",)),
        (r"dung tich.*(?:thiet ke|toan bo)", "STORAGE_DESIGN", "dung tích toàn bộ theo thiết kế", ("thiet ke",)),
        (r"dung tich hien tai", "STORAGE_CURRENT", "dung tích hiện tại", ("hien tai",)),
        (r"luu luong binh quan.*tuan truoc", "DISCHARGE_PREVIOUS_WEEK_MEAN", "lưu lượng bình quân tuần trước", ("binh quan", "tuan truoc")),
        (r"so sanh luong mua luy tich", "RAINFALL_CUMULATIVE_COMPARISON", "mức chênh lệch lượng mưa lũy tích so với cùng kỳ trung bình nhiều năm", ("luy tich", "cung ky", "trung binh")),
        (r"luong mua luy tich tu 1\.1\.2019", "RAINFALL_CUMULATIVE_FROM_2019_01_01", "lượng mưa lũy tích từ 1/1/2019", ("luy tich", "1/1/2019")),
        (r"luong mua luy tich tu dau nam", "RAINFALL_CUMULATIVE_YTD", "lượng mưa lũy tích từ đầu năm", ("luy tich", "dau nam")),
        (r"luong mua tu 01/01/2019 den 17/7/2019", "RAINFALL_PERIOD_2019_01_01_07_17", "lượng mưa từ 01/01/2019 đến 17/7/2019", ("01/01/2019", "17/7/2019")),
        (r"luong mua tu 1/1/ - 16/7/2019", "RAINFALL_PERIOD_2019_01_01_07_16", "lượng mưa từ 1/1 đến 16/7/2019", ("1/1", "16/7/2019")),
        (r"luong mua tu 12/07/2019- 17/07/2019", "RAINFALL_PERIOD_2019_07_12_07_17", "lượng mưa từ 12/07/2019 đến 17/07/2019", ("12/07/2019", "17/07/2019")),
        (r"luong mua trong thang 5", "RAINFALL_MAY_PERIOD", "lượng mưa trong tháng 5, từ 1/5 đến 28/5/2019", ("thang 5", "1/5", "28/5/2019")),
        (r"luong mua tuan truoc", "RAINFALL_PREVIOUS_WEEK", "lượng mưa tuần trước", ("tuan truoc",)),
        (r"luong mua \(thang/tuan\) truoc", "RAINFALL_PREVIOUS_MONTH_WEEK", "lượng mưa tháng/tuần trước", ("thang/tuan", "truoc")),
        (r"du bao luong mua", "RAINFALL_NEXT_FORECAST", "lượng mưa tháng/tuần tới dự báo", ("du bao", "toi")),
        (r"luong mua trong tuan", "RAINFALL_WEEK_PERIOD", "lượng mưa trong tuần", ("trong tuan",)),
        (r"luong mua trong thang/tuan", "RAINFALL_MONTH_WEEK", "lượng mưa trong tháng/tuần", ("thang/tuan",)),
        (r"tai luong.*bod", "BOD5_LOAD", "tải lượng BOD5", ("tai luong", "bod5")),
        (r"tai luong.*tss", "TSS_LOAD", "tải lượng ô nhiễm TSS", ("tai luong", "tss")),
        (r"\bbod\s*5\b|\bbod5\b", "BOD5_CONCENTRATION", "BOD5", ("bod5",)),
        (r"dien tich dap ung", "AREA_SERVED", "diện tích đáp ứng", ("dap ung",)),
        (r"dien tich san xuat", "AREA_PRODUCTION", "diện tích sản xuất", ("san xuat",)),
        (r"tong dien tich", "AREA_TOTAL", "tổng diện tích", ("tong",)),
    )
    for pattern, key, phrase, qualifiers in rules:
        if re.search(pattern, value):
            return {"key": key, "phrase": phrase, "qualifiers": list(qualifiers),
                    "raw": raw, "normalized_raw": normalized}

    # Metrics with no semantic qualifier beyond their canonical name are valid.
    generic = fold(normalized)
    return {"key": f"GENERIC:{generic}", "phrase": normalized, "qualifiers": [],
            "raw": raw, "normalized_raw": normalized}


def _unit_error(signature: dict, evidence: dict) -> str | None:
    unit = fold(evidence.get("unit") or ((evidence.get("semantic_tuple") or {}).get("unit") or {}).get("raw"))
    if signature["key"] in {"BOD5_LOAD", "TSS_LOAD"} and "kg/ngay" not in unit:
        return f"{signature['key']}:SOURCE_HEADER_KG_PER_DAY_BUT_TUPLE_UNIT_{unit or 'MISSING'}"
    return None


def _replace_metric_phrase(question: str, phrase: str, signature_key: str) -> str | None:
    replacements = {
        "BOTTOM_ELEVATION_GATE": r"mực nước",
        "BOTTOM_ELEVATION": r"mực nước",
        "WATER_LEVEL_MAX_FORECAST": r"mực nước",
        "WATER_LEVEL_MAX_OBSERVED": r"mực nước",
        "TIDAL_LEVEL_MAX_FORECAST": r"mực nước",
        "WATER_LEVEL_MONTHLY_MEAN": r"mực nước",
        "SALINITY_MAX": r"độ mặn",
        "STORAGE_CURRENT_VS_DESIGN": r"(?:tỷ lệ )?dung tích trữ",
        "STORAGE_END_MONTH_FORECAST_VS_DESIGN": r"(?:tỷ lệ )?dung tích trữ",
        "STORAGE_END_WEEK_FORECAST_VS_DESIGN": r"(?:tỷ lệ )?dung tích trữ",
        "STORAGE_END_SEASON_FORECAST_VS_DESIGN": r"(?:tỷ lệ )?dung tích trữ",
        "STORAGE_VS_DESIGN": r"(?:tỷ lệ )?dung tích trữ",
        "STORAGE_DESIGN": r"dung tích trữ",
        "STORAGE_CURRENT": r"dung tích trữ",
        "DISCHARGE_PREVIOUS_WEEK_MEAN": r"lưu lượng",
        "RAINFALL_MAY_PERIOD": r"lượng mưa",
        "RAINFALL_CUMULATIVE_COMPARISON": r"lượng mưa",
        "RAINFALL_CUMULATIVE_FROM_2019_01_01": r"lượng mưa",
        "RAINFALL_CUMULATIVE_YTD": r"lượng mưa",
        "RAINFALL_PERIOD_2019_01_01_07_17": r"lượng mưa",
        "RAINFALL_PERIOD_2019_01_01_07_16": r"lượng mưa",
        "RAINFALL_PERIOD_2019_07_12_07_17": r"lượng mưa",
        "RAINFALL_PREVIOUS_WEEK": r"lượng mưa",
        "RAINFALL_PREVIOUS_MONTH_WEEK": r"lượng mưa",
        "RAINFALL_NEXT_FORECAST": r"lượng mưa",
        "RAINFALL_WEEK_PERIOD": r"lượng mưa",
        "RAINFALL_MONTH_WEEK": r"lượng mưa",
        "BOD5_CONCENTRATION": r"BOD(?!\s*5)",
        "AREA_SERVED": r"diện tích",
        "AREA_PRODUCTION": r"diện tích",
        "AREA_TOTAL": r"diện tích",
    }
    pattern = replacements.get(signature_key)
    if not pattern:
        return None
    result, count = re.subn(pattern, phrase, question, count=1, flags=re.I)
    return result if count else None


def _qualifier_present(qualifier: str, question_fold: str) -> bool:
    aliases = {
        "trung binh": ("trung binh", "tbnn"),
        "so voi thiet ke": ("so voi thiet ke", "so voi tk"),
        "1/1/2019": ("1/1/2019", "1.1.2019", "01/01/2019"),
        "thang/tuan": ("thang/tuan", "thang/ tuan"),
    }
    return any(item in question_fold for item in aliases.get(qualifier, (fold(qualifier),)))


def _compatible_multi_phrase(keys: set[str]) -> str | None:
    if keys <= {"WATER_LEVEL_MAX_FORECAST", "WATER_LEVEL_MAX_OBSERVED"}:
        return "mực nước lớn nhất dự báo/thực đo tương ứng"
    if keys <= {"STORAGE_END_MONTH_FORECAST_VS_DESIGN", "STORAGE_END_WEEK_FORECAST_VS_DESIGN"}:
        return "tỷ lệ dung tích cuối tháng/cuối tuần dự báo so với thiết kế tương ứng"
    return None


def validate_table_metric_semantics(row: dict) -> dict:
    table_evidence = [e for e in row.get("gold_evidence") or [] if e.get("evidence_type") == "TABLE_CELL"]
    if not table_evidence:
        return {"status": "SKIP_NOT_APPLICABLE", "errors": [], "signatures": [], "proposed_question": None}

    signatures = [_signature(metric_raw(e)) for e in table_evidence]
    errors = [error for sig, ev in zip(signatures, table_evidence) if (error := _unit_error(sig, ev))]
    if errors:
        return {"status": "REJECT", "errors": errors, "signatures": signatures,
                "proposed_question": None, "basis": "source header/unit contradiction"}

    keys = sorted({sig["key"] for sig in signatures})
    phrases = sorted({sig["phrase"] for sig in signatures})
    question_fold = fold(row.get("question"))
    missing = sorted({qualifier for sig in signatures for qualifier in sig["qualifiers"]
                      if not _qualifier_present(qualifier, question_fold)})

    # Different day suffixes share one signature; genuinely different metric
    # families cannot be safely rewritten by a single deterministic phrase.
    multi_phrase = _compatible_multi_phrase(set(keys)) if len(keys) > 1 else None
    if len(keys) > 1 and missing and not multi_phrase:
        return {"status": "REJECT", "errors": ["MULTIPLE_METRIC_FAMILIES_WITH_OMITTED_QUALIFIERS"],
                "signatures": signatures, "missing_qualifiers": missing,
                "proposed_question": None, "basis": "ambiguous multi-metric rewrite"}
    if not missing:
        return {"status": "KEEP", "errors": [], "signatures": signatures,
                "missing_qualifiers": [], "proposed_question": None,
                "basis": "all source metric qualifiers are present in the question"}

    if multi_phrase:
        proposed, count = re.subn(r"mực nước|(?:tỷ lệ )?dung tích trữ", multi_phrase,
                                  row.get("question", ""), count=1, flags=re.I)
        proposed = proposed if count else None
    else:
        proposed = _replace_metric_phrase(row.get("question", ""), phrases[0], keys[0]) if len(keys) == 1 else None
    if not proposed or proposed == row.get("question"):
        return {"status": "REJECT", "errors": ["QUALIFIER_LOSS_NOT_SAFELY_REPAIRABLE"],
                "signatures": signatures, "missing_qualifiers": missing,
                "proposed_question": None, "basis": "no deterministic metric-phrase replacement"}

    proposed_fold = fold(proposed)
    still_missing = sorted({qualifier for sig in signatures for qualifier in sig["qualifiers"]
                            if not _qualifier_present(qualifier, proposed_fold)})
    if still_missing:
        return {"status": "REJECT", "errors": ["REPAIR_STILL_LOSES_QUALIFIERS"],
                "signatures": signatures, "missing_qualifiers": still_missing,
                "proposed_question": proposed, "basis": "post-repair fail-closed check"}
    return {"status": "REPAIR", "errors": [], "signatures": signatures,
            "missing_qualifiers": missing, "proposed_question": proposed,
            "basis": "deterministic replacement from an unambiguous source metric header"}
