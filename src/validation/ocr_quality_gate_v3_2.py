"""Detect unresolved OCR corruption in V3.2 semantic fields."""

from __future__ import annotations

import re
import unicodedata


MOJIBAKE = ("\u00c3\u0192", "\u00c3\u201a", "\u00c3\u00a1\u00c2\u00bb",
            "\u00c3\u201e", "\u00c3\u2020", "\u00c3\u00a2\u00e2\u201a\u00ac", "\ufffd")
MOJIBAKE_UTF8_PAIR = re.compile(r"\u00c3[\u0080-\u00bf]")
IN_WORD_SYMBOL = re.compile(r"(?i)(?<=[a-zÀ-ỹ])[?<>~&](?=[a-zÀ-ỹ])")
BROKEN_FRAGMENT = re.compile(r"(?i)\b(?:bal-i\?|hi>\s*nu&c|di>ng|hil?\s+d\(i|hb\s+ka\s+la)\b")
GARBLED_NUMBER_WORD = re.compile(r"(?i)\b[a-zÀ-ỹ]{2,}\s*[~<>]\s*\d+[a-zÀ-ỹ]*\b")
ISOLATED_ANGLE = re.compile(r"(?:^|\s)[<>](?:\s|$)")


def inspect_text(value: str | None, field: str) -> dict:
    raw = value or ""
    normalized = unicodedata.normalize("NFC", raw)
    signals = []
    if any(marker in raw for marker in MOJIBAKE) or MOJIBAKE_UTF8_PAIR.search(raw):
        signals.append("MOJIBAKE_SEQUENCE")
    if IN_WORD_SYMBOL.search(raw):
        signals.append("SYMBOL_INSIDE_WORD")
    if BROKEN_FRAGMENT.search(raw):
        signals.append("KNOWN_BROKEN_FRAGMENT")
    if GARBLED_NUMBER_WORD.search(raw):
        signals.append("GARBLED_WORD_NUMBER")
    if ISOLATED_ANGLE.search(raw):
        signals.append("ISOLATED_ANGLE_SYMBOL")
    if "…" in raw or "..." in raw:
        signals.append("TRUNCATED_ELLIPSIS")
    # A question mark is legitimate only as terminal punctuation, not inside tokens.
    if "?" in raw.rstrip("?"):
        signals.append("INTERNAL_QUESTION_MARK")
    signals = sorted(set(signals))
    status = "BROKEN" if signals else ("NORMALIZABLE" if raw != normalized else "CLEAN")
    return {
        "field": field, "status": status, "signals": signals,
        "raw_text": raw, "normalized_text": normalized,
        "normalization_basis": "Unicode NFC canonical composition" if raw != normalized and not signals else None,
    }


def inspect_qa_ocr(row: dict) -> dict:
    checks = [inspect_text(row.get("question"), "question"), inspect_text(row.get("answer"), "answer")]
    for index, ev in enumerate(row.get("gold_evidence", [])):
        checks.extend((
            inspect_text(ev.get("entity"), f"evidence[{index}].entity"),
            inspect_text(ev.get("metric_raw"), f"evidence[{index}].metric_raw"),
            inspect_text(ev.get("claim_text") or ev.get("text"), f"evidence[{index}].text"),
        ))
    broken = [item for item in checks if item["status"] == "BROKEN"]
    normalizable = [item for item in checks if item["status"] == "NORMALIZABLE"]
    return {
        "status": "BROKEN" if broken else ("NORMALIZABLE" if normalizable else "CLEAN"),
        "broken_fields": broken, "normalizable_fields": normalizable,
        "scanned_field_count": len(checks),
    }
