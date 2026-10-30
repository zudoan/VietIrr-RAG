"""Data contracts and schemas for Stage 2.4 Claim Verification.

Defines:
- ClaimVerificationStatus: 3-way outcome (SUPPORTED, CONTRADICTED, INSUFFICIENT).
- ReasonCode: Deterministic, machine-readable explanation codes.
- VerificationResult: Comprehensive per-claim verification result.
- AnswerVerificationResult: Aggregate answer-level verification decision.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class ClaimVerificationStatus(str, Enum):
    """The deterministic verification outcome for a technical claim."""

    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class ReasonCode(str, Enum):
    """Deterministic, machine-readable reason codes for verification decisions."""

    # Evidence & Provenance
    EVIDENCE_MATCH_EXACT = "EVIDENCE_MATCH_EXACT"
    EVIDENCE_MULTI_REGION_MATCH = "EVIDENCE_MULTI_REGION_MATCH"
    PROVENANCE_VALID = "PROVENANCE_VALID"
    PROVENANCE_INVALID = "PROVENANCE_INVALID"
    PROVENANCE_MISSING = "PROVENANCE_MISSING"
    CITATION_IDENTITY_MISMATCH = "CITATION_IDENTITY_MISMATCH"
    EVIDENCE_RELATION_MISSING = "EVIDENCE_RELATION_MISSING"
    DOCUMENT_MISMATCH = "DOCUMENT_MISMATCH"
    DOCUMENT_VERSION_CONFLICT = "DOCUMENT_VERSION_CONFLICT"
    AMENDMENT_APPLIED = "AMENDMENT_APPLIED"

    # Entity Identity
    ENTITY_MATCHED = "ENTITY_MATCHED"
    ENTITY_MISMATCH = "ENTITY_MISMATCH"
    ENTITY_UNKNOWN = "ENTITY_UNKNOWN"

    # Technical Parameter Identity
    PARAMETER_MATCHED = "PARAMETER_MATCHED"
    PARAMETER_MISMATCH = "PARAMETER_MISMATCH"
    PARAMETER_AMBIGUOUS = "PARAMETER_AMBIGUOUS"

    # Numeric Value & Unit
    UNIT_COMPATIBLE = "UNIT_COMPATIBLE"
    UNIT_INCOMPATIBLE = "UNIT_INCOMPATIBLE"
    UNIT_CONVERSION_APPLIED = "UNIT_CONVERSION_APPLIED"
    VALUE_MATCHED = "VALUE_MATCHED"
    VALUE_CONTRADICTED = "VALUE_CONTRADICTED"
    VALUE_OUT_OF_BOUNDS = "VALUE_OUT_OF_BOUNDS"

    # Conditions & Boundary Scope
    CONDITION_MATCHED = "CONDITION_MATCHED"
    CONDITION_CONTRADICTED = "CONDITION_CONTRADICTED"
    CONDITION_MISSING = "CONDITION_MISSING"
    TEMPORAL_SCOPE_MISMATCH = "TEMPORAL_SCOPE_MISMATCH"

    # Legal & Governance (P5-KNOWN-01 & P5-KNOWN-02)
    JURISDICTION_MATCHED = "JURISDICTION_MATCHED"
    JURISDICTION_MISMATCH = "JURISDICTION_MISMATCH"
    JURISDICTION_UNKNOWN = "JURISDICTION_UNKNOWN"
    POLARITY_MATCHED = "POLARITY_MATCHED"
    POLARITY_CONTRADICTED = "POLARITY_CONTRADICTED"
    POLARITY_UNKNOWN = "POLARITY_UNKNOWN"
    ACTION_MATCHED = "ACTION_MATCHED"
    ACTION_MISMATCH = "ACTION_MISMATCH"

    # Constraints
    CONSTRAINT_CHECKED_PASS = "CONSTRAINT_CHECKED_PASS"
    CONSTRAINT_VIOLATED = "CONSTRAINT_VIOLATED"
    CONSTRAINT_UNVERIFIED_IGNORED = "CONSTRAINT_UNVERIFIED_IGNORED"

    # Scope
    CLAIM_OUT_OF_SCOPE = "CLAIM_OUT_OF_SCOPE"
    ONTOLOGY_SCOPE_MISMATCH = "ONTOLOGY_SCOPE_MISMATCH"

    # Information Slots
    MISSING_REQUIRED_SLOT = "MISSING_REQUIRED_SLOT"
    INCOMPLETE_CLAIM_EXTRACTION = "INCOMPLETE_CLAIM_EXTRACTION"


@dataclass
class VerificationResult:
    """Detailed verification record for an individual TechnicalClaim."""

    claim_id: str
    status: ClaimVerificationStatus
    supporting_evidence_ids: list[str] = field(default_factory=list)
    conflicting_evidence_ids: list[str] = field(default_factory=list)
    checked_constraints: list[str] = field(default_factory=list)
    violated_constraints: list[str] = field(default_factory=list)
    missing_constraints: list[str] = field(default_factory=list)
    missing_evidence_slots: list[str] = field(default_factory=list)
    applicability_scope: dict[str, Any] = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)
    explanation: str = ""
    provenance_trace: list[dict[str, Any]] = field(default_factory=list)
    verifier_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        return {
            "claim_id": self.claim_id,
            "status": self.status.value if isinstance(self.status, ClaimVerificationStatus) else str(self.status),
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "conflicting_evidence_ids": list(self.conflicting_evidence_ids),
            "checked_constraints": list(self.checked_constraints),
            "violated_constraints": list(self.violated_constraints),
            "missing_constraints": list(self.missing_constraints),
            "missing_evidence_slots": list(self.missing_evidence_slots),
            "applicability_scope": dict(self.applicability_scope),
            "reason_codes": list(self.reason_codes),
            "explanation": self.explanation,
            "provenance_trace": [dict(p) for p in self.provenance_trace],
            "verifier_metadata": dict(self.verifier_metadata),
        }

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationResult:
        payload = dict(data)
        raw_status = payload.get("status")
        if isinstance(raw_status, str):
            payload["status"] = ClaimVerificationStatus(raw_status)
        return cls(**payload)


@dataclass
class AnswerVerificationResult:
    """Aggregate answer-level verification decision across multiple claims.

    Invariant:
    - If ANY claim is CONTRADICTED -> aggregate status is CONTRADICTED.
    - Elif ANY claim is INSUFFICIENT -> aggregate status is INSUFFICIENT.
    - Only if ALL claims are SUPPORTED -> aggregate status is SUPPORTED.
    Supported claims must NEVER hide an unsupported or contradicted claim.
    """

    aggregate_status: ClaimVerificationStatus
    claim_results: list[VerificationResult] = field(default_factory=list)
    summary_explanation: str = ""
    total_claims: int = 0
    supported_count: int = 0
    contradicted_count: int = 0
    insufficient_count: int = 0
    out_of_scope_count: int = 0
    p5_comparison: Optional[dict[str, Any]] = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "aggregate_status": self.aggregate_status.value
            if isinstance(self.aggregate_status, ClaimVerificationStatus)
            else str(self.aggregate_status),
            "claim_results": [r.to_dict() for r in self.claim_results],
            "summary_explanation": self.summary_explanation,
            "total_claims": self.total_claims,
            "supported_count": self.supported_count,
            "contradicted_count": self.contradicted_count,
            "insufficient_count": self.insufficient_count,
            "out_of_scope_count": self.out_of_scope_count,
            "p5_comparison": self.p5_comparison,
            "execution_time_ms": self.execution_time_ms,
        }

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnswerVerificationResult:
        payload = dict(data)
        raw_status = payload.get("aggregate_status")
        if isinstance(raw_status, str):
            payload["aggregate_status"] = ClaimVerificationStatus(raw_status)
        raw_claims = payload.get("claim_results", [])
        payload["claim_results"] = [VerificationResult.from_dict(c) for c in raw_claims]
        return cls(**payload)
