"""Conservative semantic table parser used by the V3 benchmark rebuild.

The parser is deliberately fail-closed: a structurally readable cell is not a
QA candidate until its entity, metric, value and (when relevant) period/unit
are independently meaningful in the irrigation and water-resources domain.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


DIMENSION_TYPES = {"INDEX", "ENTITY", "METRIC", "TIME", "VALUE", "UNIT", "CATEGORY", "NOTE", "UNKNOWN"}
TECHNICAL_HEADERS = {
    "tt", "stt", "stt.", "số tt", "so tt", "số thứ tự", "so thu tu", "thứ tự", "thu tu",
    "index", "id", "mã", "ma", "no", "no.",
}
ENTITY_HINTS = (
    "tỉnh", "thành phố", "huyện", "xã", "trạm", "hồ", "sông", "kênh", "cống",
    "lưu vực", "vùng", "hệ thống", "công trình", "địa điểm", "điểm", "tuyến",
)
TIME_HINTS = ("ngày", "tháng", "năm", "tuần", "kỳ", "thời gian", "giai đoạn", "period")
NOTE_HINTS = ("ghi chú", "nhận xét", "note", "mô tả", "diễn giải")
UNIT_PATTERN = re.compile(
    r"(?<!\w)(triệu\s*m\s*[³3]|m\s*[³3]/s|m3/s|m\s*[³3]|m3|m\s*[²2]|ha|"
    r"km\s*[²2]|km2|mm|cm|m|%|‰|mg/l|g/l|µg/l|ntu|tỷ\s*đồng|°c|độ\s*c)(?!\w)", re.I
)
NUMBER = re.compile(r"^[<>≤≥~≈]?\s*-?\d[\d.,]*(?:\s*[-–]\s*-?\d[\d.,]*)?\s*(?:%|‰)?$")
DATE_LIKE = re.compile(r"^(?:\d{1,2}[/-]){1,2}\d{2,4}$|^20\d{2}$")
ROMAN = re.compile(r"^[IVXLCDM]+$", re.I)


METRIC_RULES = [
    (("mực nước", "cao trình"), "WaterLevel"),
    (("lưu lượng", "dòng chảy", "lưu lượng xả"), "Discharge"),
    (("lượng mưa",), "Rainfall"),
    (("dung tích", "trữ lượng", "lượng nước trữ"), "ReservoirStorage"),
    (("diện tích",), "Area"),
    (("tss", "chất rắn lơ lửng"), "TSS"),
    (("độ mặn", "xâm nhập mặn", "salinity"), "Salinity"),
    (("nhiệt độ",), "Temperature"),
    (("oxy hòa tan",), "DissolvedOxygen"),
    (("amoni",), "Ammonium"),
    (("nitrat",), "Nitrate"),
    (("phosphat",), "Phosphate"),
    (("số hộ",), "AffectedHouseholds"),
    (("sản lượng",), "Production"),
    (("nhu cầu nước",), "WaterDemand"),
]


def fold(text: Any) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    value = value.replace("đ", "d")
    return re.sub(r"\s+", " ", value).strip()


def clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def is_index_value(value: str) -> bool:
    v = clean(value)
    return bool(re.fullmatch(r"\d{1,3}[.)]?", v) or ROMAN.fullmatch(v))


def is_valid_entity(value: str) -> bool:
    v = clean(value)
    fv = fold(v)
    if not v or len(v) < 2 or len(v) > 180:
        return False
    if NUMBER.fullmatch(v) or DATE_LIKE.fullmatch(v) or ROMAN.fullmatch(v):
        return False
    compact = re.sub(r"[^a-z0-9]", "", fv)
    if len(compact) < 3:
        return False
    if fv in TECHNICAL_HEADERS or compact in {"tong", "t0ng", "t6ng", "tfing", "tongcong", "t0ngcong", "t6ngcong", "cong", "trungbinh", "max", "min"}:
        return False
    if any(ch in v for ch in "~{}|\\^"):
        return False
    if any(ch.isdigit() for ch in v) and not re.fullmatch(r"[A-ZĐ]{1,6}\d{1,4}(?:[-/.][A-Z0-9]+)?", v):
        return False
    return any(ch.isalpha() for ch in v)


def canonical_metric(raw: str, context: str = "") -> tuple[str | None, float, str]:
    candidate = clean(raw)
    folded_candidate = fold(candidate)
    if not candidate or folded_candidate in TECHNICAL_HEADERS or re.match(r"^(?:s?tt|index|no\.?)(?:\s|$)", folded_candidate) or len(candidate) > 180:
        return None, 0.0, "technical/header field"
    if sum(ch.isalpha() or ch.isdigit() or ch.isspace() or ch in "%/().,-³²µ°" for ch in candidate) / len(candidate) < 0.85:
        return None, 0.0, "corrupted metric label"
    # Chemical symbols are case-sensitive raw-header tokens. Folding Vietnamese
    # "độ" or "đo" to "do" must never create DissolvedOxygen.
    symbol_rules = [
        (r"(?<![A-Za-z0-9])pH(?![A-Za-z0-9])", "PH"),
        (r"(?<![A-Za-z0-9])DO(?![A-Za-z0-9])", "DissolvedOxygen"),
        (r"(?<![A-Za-z0-9])BOD(?:5)?(?![A-Za-z0-9])", "BOD"),
        (r"(?<![A-Za-z0-9])COD(?![A-Za-z0-9])", "COD"),
        (r"(?<![A-Za-z0-9])TSS(?![A-Za-z0-9])", "TSS"),
        (r"(?<![A-Za-z0-9])NH4(?:\+)?(?![A-Za-z0-9])", "Ammonium"),
        (r"(?<![A-Za-z0-9])NO3(?:-)?(?![A-Za-z0-9])", "Nitrate"),
        (r"(?<![A-Za-z0-9])PO4(?:3-)?(?![A-Za-z0-9])", "Phosphate"),
    ]
    for pattern, canonical in symbol_rules:
        if re.search(pattern, candidate):
            return canonical, 0.98, f"case-sensitive raw symbol mapping: {canonical}"
    for needles, canonical in METRIC_RULES:
        for needle in needles:
            n = fold(needle)
            # Short chemical symbols must match a token, not arbitrary substrings.
            if len(n) <= 3:
                matched = bool(re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", folded_candidate))
            else:
                matched = n in folded_candidate
            if matched:
                return canonical, 0.96, f"raw-header keyword mapping: {canonical}"
    return None, 0.0, "no supported domain metric mapping"


def extract_unit(*texts: str) -> tuple[str | None, str | None, float]:
    joined = " ".join(clean(t) for t in texts if t)
    # PDF font encodings commonly corrupt "triệu" as tri~u/tri¢u. Detect the
    # complete compound before the generic m3 branch so its scale is retained.
    folded_joined = fold(joined)
    million = (
        re.search(r"tri.{0,4}u.{0,12}m\s*[³3]|m\s*[³3].{0,12}tri.{0,4}u", folded_joined, re.I)
        or re.search(r"\(\s*10\s*6\s*m\s*[³3]\s*\)", folded_joined, re.I)
    )
    if million:
        return "triệu m3", "million_m3", 0.92
    match = UNIT_PATTERN.search(joined)
    if not match:
        return None, None, 0.0
    raw = match.group(1)
    f = fold(raw).replace(" ", "")
    mapping = {
        "trieum3": "million_m3", "trieum³": "million_m3",
        "m3/s": "m3/s", "m³/s": "m3/s", "m3": "m3", "m³": "m3", "m2": "m2",
        "m²": "m2", "km2": "km2", "km²": "km2", "ha": "ha", "mm": "mm",
        "cm": "cm", "m": "m", "%": "%", "‰": "permille", "mg/l": "mg/L",
        "g/l": "g/L", "µg/l": "µg/L", "ntu": "NTU", "°c": "°C",
    }
    return raw, mapping.get(f, clean(raw)), 0.95


def metric_unit_compatible(metric: str, unit: str | None) -> bool:
    """Fail closed when an explicit unit contradicts the canonical metric."""
    if unit is None:
        return True
    allowed = {
        "WaterLevel": {"m", "cm"},
        "Discharge": {"m3/s"},
        "Rainfall": {"mm", "%"},
        "ReservoirStorage": {"m3", "million_m3", "%"},
        "Area": {"ha", "km2", "m2"},
        "Salinity": {"permille", "g/L", "mg/L", "%"},
        "Temperature": {"°C"},
        "PH": set(),
        "DissolvedOxygen": {"mg/L", "g/L"},
        "BOD": {"mg/L", "g/L"},
        "COD": {"mg/L", "g/L"},
        "TSS": {"mg/L", "g/L"},
        "Ammonium": {"mg/L", "g/L", "µg/L"},
        "Nitrate": {"mg/L", "g/L", "µg/L"},
        "Phosphate": {"mg/L", "g/L", "µg/L"},
        "AffectedHouseholds": set(),
        "Production": set(),
        "WaterDemand": {"m3", "m3/s", "%"},
    }
    expected = allowed.get(metric)
    return expected is None or unit in expected


def classify_dimension(header: str, values: list[str] | None = None) -> dict:
    raw = clean(header)
    f = fold(raw)
    values = [clean(v) for v in (values or []) if clean(v)]
    if f in TECHNICAL_HEADERS or re.fullmatch(r"(s?t?t|index|no\.?)", f):
        dtype, confidence, basis = "INDEX", 0.99, "technical column blocklist"
    elif any(fold(h) in f for h in NOTE_HINTS):
        dtype, confidence, basis = "NOTE", 0.96, "note header"
    elif any(fold(h) in f for h in TIME_HINTS):
        dtype, confidence, basis = "TIME", 0.94, "time header"
    elif any(fold(h) in f for h in ENTITY_HINTS):
        dtype, confidence, basis = "ENTITY", 0.94, "entity header"
    else:
        metric, metric_conf, metric_basis = canonical_metric(raw)
        if metric:
            dtype, confidence, basis = "METRIC", metric_conf, metric_basis
        elif values and sum(bool(NUMBER.fullmatch(v)) for v in values) / len(values) >= 0.65:
            dtype, confidence, basis = "VALUE", 0.82, "numeric value distribution"
        elif values and sum(is_valid_entity(v) for v in values) / len(values) >= 0.70:
            dtype, confidence, basis = "ENTITY", 0.75, "categorical entity distribution"
        else:
            dtype, confidence, basis = "UNKNOWN", 0.25, "insufficient semantic evidence"
    return {"raw": raw, "dimension_type": dtype, "confidence": round(confidence, 3), "basis": basis}


def normalize_time(raw: str) -> dict:
    value = clean(raw)
    # An unresolved header/caption is context, not a temporal provenance value.
    # Keep raw null until an explicit date/month/year has actually been parsed.
    result = {"raw": None, "normalized_start": None, "normalized_end": None, "period_type": "UNKNOWN", "confidence": 0.0, "basis": "unresolved"}
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](20\d{2})", value)
    if m:
        d, mo, y = map(int, m.groups())
        iso = f"{y:04d}-{mo:02d}-{d:02d}"
        result.update(raw=value, normalized_start=iso, normalized_end=iso, period_type="DATE", confidence=0.94, basis="explicit date")
        return result
    m = re.search(r"(?:tháng|thang)\s*(\d{1,2})[/-]?(20\d{2})", fold(value))
    if m:
        mo, y = map(int, m.groups())
        import calendar
        result.update(raw=value, normalized_start=f"{y:04d}-{mo:02d}-01", normalized_end=f"{y:04d}-{mo:02d}-{calendar.monthrange(y, mo)[1]:02d}", period_type="MONTH", confidence=0.9, basis="explicit month")
        return result
    m = re.search(r"\b(20\d{2})\b", value)
    if m:
        y = int(m.group(1))
        result.update(raw=value, normalized_start=f"{y:04d}-01-01", normalized_end=f"{y:04d}-12-31", period_type="YEAR", confidence=0.75, basis="explicit year")
    return result


@dataclass
class SemanticTableParser:
    minimum_tuple_confidence: float = 0.78

    def parse(self, table: dict) -> dict:
        headers = [clean(h) for h in table.get("headers", table.get("column_labels", []))]
        cells = table.get("cells", [])
        context = clean(f"{table.get('caption', '')} {' '.join(headers)}")
        values_by_col: dict[int, list[str]] = {}
        for cell in cells:
            values_by_col.setdefault(int(cell.get("column_index", 0)), []).append(clean(cell.get("raw_cell")))
        dimensions = [classify_dimension(header, values_by_col.get(i, [])) for i, header in enumerate(headers)]
        entity_cols = [i for i, d in enumerate(dimensions) if d["dimension_type"] == "ENTITY"]
        tuples = []
        rejection_counts: dict[str, int] = {}
        for cell in cells:
            col = int(cell.get("column_index", 0))
            value = clean(cell.get("raw_cell"))
            if not value or not NUMBER.fullmatch(value):
                continue
            header = headers[col] if col < len(headers) else clean(cell.get("column_label"))
            metric_raw = header
            metric, metric_conf, metric_basis = canonical_metric(metric_raw, context)
            if not metric:
                rejection_counts["INVALID_METRIC"] = rejection_counts.get("INVALID_METRIC", 0) + 1
                continue
            entity_raw = clean(cell.get("row_label"))
            if not is_valid_entity(entity_raw) and entity_cols:
                row_idx = int(cell.get("row_index", 0))
                entity_cell = next((c for c in cells if int(c.get("row_index", -1)) == row_idx and int(c.get("column_index", -1)) == entity_cols[0]), None)
                entity_raw = clean(entity_cell.get("raw_cell")) if entity_cell else entity_raw
            if not is_valid_entity(entity_raw):
                rejection_counts["INVALID_ENTITY"] = rejection_counts.get("INVALID_ENTITY", 0) + 1
                continue
            unit_raw, unit_normalized, unit_conf = extract_unit(header, table.get("caption", ""), value)
            if not unit_raw:
                rejection_counts["MISSING_UNIT"] = rejection_counts.get("MISSING_UNIT", 0) + 1
                continue
            if unit_raw and not metric_unit_compatible(metric, unit_normalized):
                rejection_counts["INCOMPATIBLE_METRIC_UNIT"] = rejection_counts.get("INCOMPATIBLE_METRIC_UNIT", 0) + 1
                continue
            period = normalize_time(f"{header} {table.get('caption', '')}")
            confidence = min(0.96, (metric_conf + 0.92 + (unit_conf or 0.8) + (period["confidence"] or 0.8)) / 4)
            if confidence < self.minimum_tuple_confidence:
                rejection_counts["LOW_CONFIDENCE"] = rejection_counts.get("LOW_CONFIDENCE", 0) + 1
                continue
            tuples.append({
                "tuple_id": f"{table.get('table_id', 'TABLE')}_R{int(cell.get('row_index', 0)):03d}_C{col:03d}",
                "cell_ref": {"row_index": int(cell.get("row_index", 0)), "column_index": col},
                "entity": {"raw": entity_raw, "canonical": fold(entity_raw), "confidence": 0.92, "basis": "row/entity dimension"},
                "metric": {"raw": metric_raw, "canonical": metric, "confidence": round(metric_conf, 3), "basis": metric_basis},
                "time": period,
                "value": {"raw": value, "normalized": value.replace(" ", ""), "value_type": "NUMERIC", "confidence": 0.98},
                "unit": {"raw": unit_raw, "normalized": unit_normalized, "confidence": round(unit_conf, 3), "basis": "header/caption" if unit_raw else "not stated"},
                "semantic_confidence": round(confidence, 3),
                "qa_eligible": True,
            })
        result = dict(table)
        result["semantic_dimensions"] = dimensions
        if table.get("quality_label") != "GOOD":
            tuples = []
            rejection_counts["STRUCTURAL_QUALITY_NOT_GOOD"] = rejection_counts.get("STRUCTURAL_QUALITY_NOT_GOOD", 0) + 1
        result["semantic_tuples"] = tuples
        result["semantic_quality"] = "GOOD" if len(tuples) >= 2 else ("PARTIAL" if tuples else "REJECT")
        result["semantic_rejection_counts"] = rejection_counts
        return result
