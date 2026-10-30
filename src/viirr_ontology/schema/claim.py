"""TechnicalClaim data models for Stage 2.

This module defines:
- ClaimPolarity: enum distinguishing affirmed, negated, uncertain, and unknown statements.
- ClaimCondition: structured condition or constraint (operator, value, unit).
- TechnicalClaim: a structured technical statement extracted from an answer or query,
  designed for downstream ontology constraint verification.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class ClaimPolarity(str, Enum):
    """Polarity of a technical or legal assertion."""

    AFFIRMED = "AFFIRMED"    # e.g., "trạm X31 đạt 3.2 mg/L", "được phép quyết định"
    NEGATED = "NEGATED"      # e.g., "trạm X31 không đạt 3.2 mg/L", "không được quyết định"
    UNCERTAIN = "UNCERTAIN"  # e.g., "chưa xác định được", "chưa công bố", "dự kiến"
    UNKNOWN = "UNKNOWN"      # Missing polarity or extraction failure (NEVER assumed affirmed)


@dataclass(frozen=True)
class ClaimCondition:
    """A condition or threshold qualifying a technical claim.

    Examples:
    - Operator: "GE" (>=), Value: "5.0", Unit: "%"
    - Operator: "LE" (<=), Value: "85.0", Unit: "m"
    """

    operator: str  # EQ, GE, GT, LE, LT, BETWEEN, IN
    value: str
    unit: str = ""
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClaimCondition:
        return cls(**data)


@dataclass(frozen=True)
class EvidenceCitation:
    """An explicit citation preserving the full P5 evidence identity."""

    doc_id: str
    page_number: int
    evidence_id: str

    def __post_init__(self) -> None:
        if not self.doc_id.strip() or not self.evidence_id.strip():
            raise ValueError("Citation doc_id and evidence_id must be non-empty")
        if self.page_number < 1:
            raise ValueError("Citation page_number must be >= 1")

    def citation_key(self) -> tuple[str, int, str]:
        return self.doc_id, self.page_number, self.evidence_id

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceCitation:
        return cls(**data)


@dataclass
class TechnicalClaim:
    """A structured technical claim extracted from a generated answer or query.

    Structured fields isolate entity, parameter, value, unit, condition, and scope,
    enabling deterministic ontology constraint validation without regex guesswork.

    Addresses documented defects:
    - P5-KNOWN-01: Full multi-word jurisdiction preservation (e.g. 'tỉnh Đồng Nai' vs 'tỉnh Đồng Tháp').
    - P5-KNOWN-02: Explicit action and polarity separation (e.g. action='quyết định', polarity=NEGATED).
    - Unsafe fallback fix: Default polarity is UNKNOWN; invalid polarity raises ValueError.
    """

    claim_id: str
    claim_text: str
    subject: str = ""
    parameter: str = ""
    value: Optional[str] = None
    unit: Optional[str] = None
    temporal_scope: Optional[str] = None
    conditions: list[ClaimCondition] = field(default_factory=list)
    document_scope: Optional[str] = None
    evidence_ids: list[str] = field(default_factory=list)
    evidence_citations: list[EvidenceCitation] = field(default_factory=list)
    polarity: ClaimPolarity = ClaimPolarity.UNKNOWN
    observation_type: Optional[str] = None  # ACTUAL_OBSERVED, FORECAST_ESTIMATE, DESIGN_SPECIFICATION, UNKNOWN
    jurisdiction: Optional[str] = None
    action: Optional[str] = None
    extraction_status: str = "MANUAL"
    extraction_provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_text": self.claim_text,
            "subject": self.subject,
            "parameter": self.parameter,
            "value": self.value,
            "unit": self.unit,
            "temporal_scope": self.temporal_scope,
            "conditions": [c.to_dict() for c in self.conditions],
            "document_scope": self.document_scope,
            "evidence_ids": list(self.evidence_ids),
            "evidence_citations": [citation.to_dict() for citation in self.evidence_citations],
            "polarity": self.polarity.value if isinstance(self.polarity, ClaimPolarity) else str(self.polarity),
            "observation_type": self.observation_type,
            "jurisdiction": self.jurisdiction,
            "action": self.action,
            "extraction_status": self.extraction_status,
            "extraction_provenance": self.extraction_provenance,
        }

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TechnicalClaim:
        payload = dict(data)
        conditions_data = payload.get("conditions", [])
        payload["conditions"] = [ClaimCondition.from_dict(c) for c in conditions_data]
        citations_data = payload.get("evidence_citations", [])
        payload["evidence_citations"] = [
            c if isinstance(c, EvidenceCitation) else EvidenceCitation.from_dict(c)
            for c in citations_data
        ]

        raw_polarity = payload.get("polarity")
        if raw_polarity is None:
            polarity = ClaimPolarity.UNKNOWN
        elif isinstance(raw_polarity, ClaimPolarity):
            polarity = raw_polarity
        elif isinstance(raw_polarity, str):
            normalized = raw_polarity.strip().upper()
            try:
                polarity = ClaimPolarity(normalized)
            except ValueError:
                raise ValueError(
                    f"Invalid claim polarity '{raw_polarity}'. "
                    f"Must be one of {[p.value for p in ClaimPolarity]}"
                )
        else:
            raise ValueError(
                f"Invalid claim polarity type: expected str or ClaimPolarity, "
                f"got {type(raw_polarity).__name__}"
            )
        payload["polarity"] = polarity
        return cls(**payload)

    @classmethod
    def from_json(cls, json_str: str) -> TechnicalClaim:
        return cls.from_dict(json.loads(json_str))
