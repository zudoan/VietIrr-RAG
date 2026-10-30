"""Data models for Stage 3 Evidence-Targeted Correction MVP.

Defines:
- CorrectionGoal: targeted objective based on missing evidence slots.
- CorrectionPlan: interpretable blueprint for targeted corrective retrieval.
- CorrectionAttempt: structured trace of a single retrieval and reverification round.
- CorrectionResult: complete before/after audit for offline evaluation.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from viirr_ontology.schema.evidence import EvidenceSet
from viirr_ontology.verifier.models import ClaimVerificationStatus, ReasonCode, VerificationResult


class CorrectionGoal(str, Enum):
    """Categorized corrective retrieval goals driven by missing evidence."""

    RESOLVE_MISSING_UNIT = "RESOLVE_MISSING_UNIT"
    RESOLVE_MISSING_CONDITION = "RESOLVE_MISSING_CONDITION"
    RESOLVE_MISSING_VERSION = "RESOLVE_MISSING_VERSION"
    RESOLVE_MISSING_AUTHORITY = "RESOLVE_MISSING_AUTHORITY"
    RESOLVE_MISSING_RELATION = "RESOLVE_MISSING_RELATION"
    GENERIC_MISSING_SLOTS = "GENERIC_MISSING_SLOTS"


@dataclass
class CorrectionPlan:
    """Interpretable blueprint specifying targeted queries and scope constraints."""

    correction_goal: str
    target_claim_id: str
    missing_slots: list[str] = field(default_factory=list)
    required_evidence_types: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    subject_constraints: list[str] = field(default_factory=list)
    parameter_constraints: list[str] = field(default_factory=list)
    document_scope: Optional[str] = None
    temporal_scope: Optional[str] = None
    allowed_retrieval_strategy: str = "targeted_focused_slot_retrieval"
    max_attempts: int = 2
    reason_for_correction: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CorrectionAttempt:
    """Audit record of a single corrective retrieval step and reverification."""

    attempt_number: int
    query_used: str
    retrieved_evidence_ids: list[str] = field(default_factory=list)
    provenance_valid: bool = True
    verification_verdict: str = "INSUFFICIENT"
    reason_codes: list[str] = field(default_factory=list)
    missing_slots_remaining: list[str] = field(default_factory=list)
    candidates_inspected: int = 0
    candidates_admitted: int = 0
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CorrectionResult:
    """Comprehensive before/after outcome of the evidence-targeted correction process."""

    target_claim_id: str
    initial_status: str
    final_status: str
    initial_reason_codes: list[str] = field(default_factory=list)
    final_reason_codes: list[str] = field(default_factory=list)
    attempts_made: int = 0
    max_attempts: int = 2
    stop_reason: str = "COMPLETED"
    attempts: list[CorrectionAttempt] = field(default_factory=list)
    final_evidence_set: Optional[EvidenceSet] = None
    final_verification_result: Optional[VerificationResult] = None
    newly_retrieved_evidence_ids: list[str] = field(default_factory=list)
    corrected_missing_slots: list[str] = field(default_factory=list)
    retrieval_calls: int = 0
    total_candidates_inspected: int = 0
    total_candidates_admitted: int = 0
    verifier_calls: int = 0
    total_latency_ms: float = 0.0

    @property
    def success(self) -> bool:
        """Indicate whether corrective retrieval achieved SUPPORTED verdict."""
        return self.final_status == "SUPPORTED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_claim_id": self.target_claim_id,
            "initial_status": self.initial_status,
            "final_status": self.final_status,
            "initial_reason_codes": list(self.initial_reason_codes),
            "final_reason_codes": list(self.final_reason_codes),
            "attempts_made": self.attempts_made,
            "max_attempts": self.max_attempts,
            "stop_reason": self.stop_reason,
            "attempts": [a.to_dict() for a in self.attempts],
            "newly_retrieved_evidence_ids": list(self.newly_retrieved_evidence_ids),
            "corrected_missing_slots": list(self.corrected_missing_slots),
            "retrieval_calls": self.retrieval_calls,
            "total_candidates_inspected": self.total_candidates_inspected,
            "total_candidates_admitted": self.total_candidates_admitted,
            "verifier_calls": self.verifier_calls,
            "total_latency_ms": round(self.total_latency_ms, 3),
        }
