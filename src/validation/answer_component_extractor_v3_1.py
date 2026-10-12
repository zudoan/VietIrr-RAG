"""Blind answer-component extraction for V3.1.

The extractor accepts only question and reference answer. Gold evidence IDs and
gold evidence count are deliberately absent from the API.
"""

from __future__ import annotations

import hashlib
import re

from src.structure.semantic_table_parser import clean, fold


def extract_answer_components(question: str, reference_answer: str) -> list[dict]:
    question = clean(question)
    answer = clean(reference_answer)
    if not question or not answer:
        return []
    spans = [clean(part) for part in re.split(r"(?<=[.!?;])\s+", answer) if clean(part)]
    if not spans:
        spans = [answer]
    components = []
    for index, span in enumerate(spans, 1):
        numeric = bool(re.search(r"\d", span))
        # A short numeric answer inherits its semantic slot from the question
        # (for example, "mực nước của X ... bao nhiêu?"). This remains blind
        # to evidence and gold count while yielding a complete component.
        semantic_text = span
        if numeric and sum(ch.isalpha() for ch in span) < 10:
            semantic_text = f"{question.rstrip('?')} — {span}"
        components.append({
            "component_id": f"C{index}",
            "text": semantic_text,
            "answer_span": span,
            "component_type": "QUANTITATIVE_VALUE" if numeric else "TEXTUAL_CLAIM",
            "semantic_key": hashlib.sha256(f"{fold(question)}|{fold(span)}".encode()).hexdigest()[:16],
            "extraction_basis": "question_and_reference_answer_only",
        })
    return components
