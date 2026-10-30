"""Provisional end-to-end RAG components for VietIrr-RAG P4."""

from .pipeline import (
    ContextBuild,
    Evidence,
    GenerationResult,
    build_grounded_prompt,
    build_prompt,
    enforce_citation_grounding,
    evaluate_answer,
    expand_grounded_evidence,
    expand_table_evidence,
    parse_generation,
    select_context_evidence,
)

__all__ = [
    "ContextBuild",
    "Evidence",
    "GenerationResult",
    "build_grounded_prompt",
    "build_prompt",
    "enforce_citation_grounding",
    "evaluate_answer",
    "expand_grounded_evidence",
    "expand_table_evidence",
    "parse_generation",
    "select_context_evidence",
]
