"""Fail-closed OCR audit for the V3.2 final-freeze patch.

The earlier gate only inspected a few flattened evidence fields.  This gate
also walks the complete semantic tuple and records every normalization with
its raw value and an explicit reconstruction basis.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


KNOWN_RECONSTRUCTIONS = {
    "Dung tich bg to~m m3 (tri~u ) — Thi St kS": (
        "Dung tích hồ toàn bộ (triệu m3) — Thiết kế",
        "Reconstructed from the table's two-level header: the following columns are "
        "Hiện tại and Tỷ lệ hiện tại (%), and the source rows contain design capacity values.",
    ),
    "Dung tich toan b(.> m3 (tri~u ) — ThiSt k6": (
        "Dung tích toàn bộ (triệu m3) — Thiết kế",
        "Reconstructed from the table's two-level header and adjacent Hiện tại/percentage columns.",
    ),
    "Dung tich hi ~n t~1i ltricu m3' — Wtb": (
        "Dung tích hiện tại (triệu m3) — Wtb",
        "Reconstructed from the Wtb capacity heading, its million-m3 unit, and adjacent reservoir rows.",
    ),
    "Dung tich hi9n t;,1i — Wtb (trieu m3)": (
        "Dung tích hiện tại — Wtb (triệu m3)",
        "Reconstructed from the Wtb heading, million-m3 unit, and adjacent reservoir-capacity columns.",
    ),
    "Dien tich dap irng (ha)": (
        "Diện tích đáp ứng (ha)",
        "Vietnamese OCR diacritic restoration supported by the Area canonical metric and hectare unit.",
    ),
}

ROMAN_SECTION = re.compile(r"^(?:[IVXLCDM]+(?:\s+[IVXLCDM]+)*)$", re.I)
MOJIBAKE_MARKERS = ("\ufffd", "Ãƒ", "Ã‚", "Ã¡Â»", "Ã„", "Ã†", "Ã¢â‚¬", "â€¦")
IN_WORD_DAMAGE = re.compile(r"(?iu)(?<=[a-zà-ỹ])[?<>~&](?=[a-zà-ỹ0-9])|(?<=[a-zà-ỹ0-9])[?<>~&](?=[a-zà-ỹ])")
OCR_SYMBOLS = re.compile(r"[~<>]|\(\.>|\b(?:tri~u|thiSt|t~1i|to~m)\b", re.I)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def inspect_value(value: Any, path: str, semantic_role: str | None = None) -> dict:
    raw = _text(value)
    nfc = unicodedata.normalize("NFC", raw)
    signals: list[str] = []
    normalized = raw
    basis = None

    if raw in KNOWN_RECONSTRUCTIONS:
        normalized, basis = KNOWN_RECONSTRUCTIONS[raw]
        signals.append("KNOWN_HEADER_RECONSTRUCTION")
        status = "NORMALIZED"
    else:
        embedded = [(damaged, repair) for damaged, (repair, _) in KNOWN_RECONSTRUCTIONS.items()
                    if damaged in raw]
        if embedded:
            normalized = raw
            for damaged, repair in embedded:
                normalized = normalized.replace(damaged, repair)
            basis = "Embedded known header reconstruction; each replacement is listed in the controlled mapping."
            signals.append("KNOWN_EMBEDDED_HEADER_RECONSTRUCTION")
        if raw != nfc:
            normalized = unicodedata.normalize("NFC", normalized)
            basis = basis or "Unicode NFC canonical composition only."
        if any(marker in raw for marker in MOJIBAKE_MARKERS):
            signals.append("MOJIBAKE_SEQUENCE")
        if (IN_WORD_DAMAGE.search(raw) or OCR_SYMBOLS.search(raw)) and not embedded:
            signals.append("DAMAGED_TOKEN_OR_SYMBOL")
        if "?" in raw.rstrip().rstrip("?"):
            signals.append("INTERNAL_QUESTION_MARK")
        if semantic_role == "entity" and ROMAN_SECTION.fullmatch(raw.strip()):
            signals.append("ROMAN_SECTION_LABEL_AS_ENTITY")
        if any(signal in {"MOJIBAKE_SEQUENCE", "DAMAGED_TOKEN_OR_SYMBOL", "INTERNAL_QUESTION_MARK",
                          "ROMAN_SECTION_LABEL_AS_ENTITY"} for signal in signals):
            status = "REJECT"
        elif raw != normalized:
            status = "NORMALIZED"
        else:
            status = "CLEAN"

    return {
        "path": path,
        "semantic_role": semantic_role,
        "status": status,
        "signals": sorted(set(signals)),
        "raw": raw,
        "normalized": normalized,
        "normalization_basis": basis,
    }


def _append(checks: list[dict], value: Any, path: str, role: str | None = None) -> None:
    # Missing optional time fields are not OCR content.
    if value is not None:
        checks.append(inspect_value(value, path, role))


def inspect_evidence(evidence: dict, prefix: str = "evidence") -> dict:
    checks: list[dict] = []
    for key, role in (
        ("entity", "entity"), ("entity_canonical", "entity"),
        ("metric", "metric"), ("metric_label", "metric"),
        ("metric_raw", "metric"), ("unit", "unit"),
        ("unit_normalized", "unit"), ("value", "value"),
        ("text", "evidence_text"), ("claim_text", "evidence_text"),
        ("source_text", "evidence_text"),
    ):
        _append(checks, evidence.get(key), f"{prefix}.{key}", role)

    tup = evidence.get("semantic_tuple") or {}
    for section, role in (("entity", "entity"), ("metric", "metric"),
                          ("time", "time"), ("unit", "unit"), ("value", "value")):
        part = tup.get(section) or {}
        if isinstance(part, dict):
            for key in ("raw", "canonical", "normalized", "normalized_start", "normalized_end"):
                _append(checks, part.get(key), f"{prefix}.semantic_tuple.{section}.{key}", role)

    rejected = [item for item in checks if item["status"] == "REJECT"]
    normalized = [item for item in checks if item["status"] == "NORMALIZED"]
    status = "REJECT" if rejected else ("NORMALIZED" if normalized else "CLEAN")
    return {"status": status, "checks": checks, "rejected_fields": rejected,
            "normalizations": normalized, "scanned_field_count": len(checks)}


def inspect_qa_ocr(row: dict) -> dict:
    checks = [
        inspect_value(row.get("question"), "question", "question"),
        inspect_value(row.get("answer"), "answer", "answer"),
    ]
    for index, evidence in enumerate(row.get("gold_evidence") or []):
        checks.extend(inspect_evidence(evidence, f"gold_evidence[{index}]")["checks"])

    rejected = [item for item in checks if item["status"] == "REJECT"]
    normalized = [item for item in checks if item["status"] == "NORMALIZED"]
    status = "REJECT" if rejected else ("NORMALIZED" if normalized else "CLEAN")
    return {
        "status": status,
        "scanned_field_count": len(checks),
        "rejected_fields": rejected,
        "normalizations": normalized,
        "checks": checks,
        "uncertain_fields": [],
    }
