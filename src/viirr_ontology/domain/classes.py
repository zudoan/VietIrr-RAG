"""Domain dataclasses corresponding to the Hydraulic Domain Ontology entities.

These Python dataclasses serve as application-facing representations of the RDF/OWL
concepts defined in `ontology/viirr_hydraulic_v0_1.ttl`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class HydraulicStructure:
    """A physical hydraulic structure or monitoring entity."""

    structure_id: str
    canonical_name: str
    structure_type: str  # e.g., Reservoir, Dam, MonitoringStation, SluiceGate
    basin: Optional[str] = None
    administrative_location: Optional[str] = None
    aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TechnicalParameter:
    """A physical, hydrological, volumetric, or water quality parameter."""

    parameter_id: str
    canonical_name: str
    parameter_group: str  # WaterLevel, StorageCapacity, Discharge, WaterQualityParameter
    allowed_dimensions: list[str] = field(default_factory=list)
    default_unit: Optional[str] = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DesignCondition:
    """A limiting operational or design boundary condition."""

    condition_id: str
    condition_type: str  # FloodSeasonCondition, DrySeasonCondition, DesignFloodFrequency
    description: str = ""
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StandardDocument:
    """A normative technical standard or legal operating procedure."""

    document_id: str
    document_number: str
    title: str
    issuing_authority: str
    publication_date: Optional[str] = None
    version_status: str = "CURRENT"  # CURRENT, SUPERSEDED, AMENDED
    supersedes_doc_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MeasurementAssertion:
    """N-ary fact reification connecting structure, parameter, value, unit, condition, and source.

    Solves the binary triple limitation of standard RDF by keeping the full context together.
    """

    assertion_id: str
    structure_id: str
    parameter_name: str
    numeric_value: float
    unit: str
    temporal_scope: Optional[str] = None
    condition: Optional[str] = None
    source_document_id: Optional[str] = None
    source_evidence_id: Optional[str] = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Jurisdiction:
    """Administrative or territorial jurisdiction with multi-word preservation."""

    name: str
    level: str = "Tỉnh/Thành phố"  # Trung ương, Bộ ngành, Tỉnh/Thành phố
    parent_jurisdiction: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceValidationRecord:
    """Traceable validation record bound to an actual evidence source.

    Distinguishes mechanically confirmed source-text matching from domain-expert validation.
    Prevents self-declared 'VERIFIED_SOURCE' strings from bypassing audit.
    """

    source_document_id: str
    citation_key: str  # e.g., "IRR_CP_2019_ee0bca33:P0004:REG_IRR_CP_2019_ee0bca33_P0004_B025"
    source_content_hash: Optional[str] = None  # SHA-256 fingerprint of source text
    verification_method: str = "UNVERIFIED"  # STRUCTURAL_SCHEMA, MECHANICAL_TEXT_MATCH, EXPERT_CONFIRMED, PENDING_EXPERT_REVIEW, UNVERIFIED
    verification_outcome: str = "UNCONFIRMED"  # VALID, REVOKED, UNCONFIRMED, INVALID_SOURCE, HASH_MISMATCH
    verified_at: Optional[str] = None
    verifier_identity: Optional[str] = None
    notes: str = ""

    def is_valid(self) -> bool:
        if self.verification_outcome != "VALID":
            return False
        return self.verification_method in {
            "STRUCTURAL_SCHEMA",
            "EXPERT_CONFIRMED",
            "MECHANICAL_TEXT_MATCH",
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> Optional[SourceValidationRecord]:
        if not data:
            return None
        return cls(**data)


@dataclass(frozen=True)
class VerificationConstraint:
    """Source-grounded constraint definition for verification.

    Separates structural/unit rules (valid by schema) from source-dependent factual/legal rules
    which require verified document authority and auditable provenance.
    """

    constraint_id: str
    name: str
    description: str
    constraint_type: str  # SCHEMA_TYPE, UNIT_COMPATIBILITY, SOURCE_VERIFIED_FACT, LEGAL_APPLICABILITY
    applicable_class: str
    applicable_conditions: Optional[str] = None
    document_id: Optional[str] = None
    document_version: Optional[str] = None
    page_number: Optional[int] = None
    region_id: Optional[str] = None
    source_reference: str = ""
    validation_status: str = "DRAFT_UNVERIFIED"  # VERIFIED_SOURCE vs DRAFT_UNVERIFIED
    explanation: str = ""
    expected_behavior_when_missing: str = ""
    quoted_evidence: str = ""
    applicable_article: str = ""
    audit_notes: str = ""
    validation_record: Optional[SourceValidationRecord] = None

    def is_structural(self) -> bool:
        """Returns True if this is a schema or unit dimension rule (not dependent on a PDF fact)."""
        return self.constraint_type in {"SCHEMA_TYPE", "UNIT_COMPATIBILITY"}

    def is_source_dependent(self) -> bool:
        """Returns True if this rule depends on external document authority (fact or legal rule)."""
        return self.constraint_type in {"SOURCE_VERIFIED_FACT", "LEGAL_APPLICABILITY"}

    def audit_provenance(
        self,
        trusted_doc_ids: Optional[set[str]] = None,
        trusted_hashes: Optional[dict[str, str]] = None,
    ) -> tuple[bool, str]:
        """Auditable validation procedure verifying genuine source grounds before rule activation.

        A rule MUST NOT become active merely because its validation_status string claims VERIFIED_SOURCE,
        or because document_id / source_reference are non-empty strings.
        It must possess a valid, non-revoked SourceValidationRecord backed by verifiable corpus evidence.

        Returns:
            (is_valid, explanation_or_failure_reason)
        """
        if self.validation_status != "VERIFIED_SOURCE":
            return False, f"Constraint '{self.constraint_id}' is marked '{self.validation_status}' (not VERIFIED_SOURCE)"

        if self.is_structural():
            return True, f"Structural rule '{self.constraint_id}' is valid by schema definition"

        # 1. Require a traceable validation record
        if not self.validation_record:
            return False, f"Rule '{self.constraint_id}' lacks a traceable SourceValidationRecord"

        if self.validation_record.source_document_id != self.document_id:
            return False, (
                f"Validation record document '{self.validation_record.source_document_id}' does not match "
                f"constraint document '{self.document_id}'"
            )

        if not self.validation_record.citation_key.startswith(f"{self.document_id}:"):
            return False, f"Validation citation key is not bound to document '{self.document_id}'"

        if not self.validation_record.is_valid():
            if self.validation_record.verification_outcome == "REVOKED":
                return False, f"Validation record for rule '{self.constraint_id}' is REVOKED"
            if self.validation_record.verification_method == "PENDING_EXPERT_REVIEW":
                return False, f"Rule '{self.constraint_id}' has PENDING_EXPERT_REVIEW and cannot be active"
            return False, f"Rule '{self.constraint_id}' has invalid validation record: {self.validation_record.verification_outcome} / {self.validation_record.verification_method}"

        # 2. Source-dependent factual or legal rule requirements
        if not self.document_id or not self.document_id.strip():
            return False, f"Rule '{self.constraint_id}' has missing document_id"

        doc_upper = self.document_id.upper()
        if any(bad in doc_upper for bad in ["UNRESOLVED", "DOC_FAKE", "FAKE", "PLACEHOLDER", "TEST_FAKE"]):
            return False, f"Rule '{self.constraint_id}' has fake or unresolved document_id: '{self.document_id}'"

        if not self.source_reference or not self.source_reference.strip():
            return False, f"Rule '{self.constraint_id}' has empty source_reference"

        ref_lower = self.source_reference.lower()
        has_article_or_table = any(
            k in ref_lower for k in ["điều", "dieu", "bảng", "bang", "phụ lục", "phu luc", "khoản", "khoan"]
        )
        if not has_article_or_table and not self.applicable_article:
            return False, (
                f"Source reference '{self.source_reference}' lacks specific article/table citation "
                f"for rule '{self.constraint_id}'"
            )

        # 3. Check against trusted doc index if provided
        if trusted_doc_ids is None or self.document_id not in trusted_doc_ids:
            return False, f"Document ID '{self.document_id}' is not in a supplied trusted corpus registry"

        # 4. Check content hash if provided
        if not self.validation_record.source_content_hash:
            return False, f"Rule '{self.constraint_id}' lacks a source content hash"
        if trusted_hashes is None:
            return False, f"No trusted source hashes supplied for rule '{self.constraint_id}'"
        expected_hash = trusted_hashes.get(self.validation_record.citation_key) or trusted_hashes.get(self.document_id)
        if not expected_hash:
            return False, f"No trusted hash exists for document '{self.document_id}'"
        if self.validation_record.source_content_hash != expected_hash:
            return False, f"Content hash mismatch for rule '{self.constraint_id}': record={self.validation_record.source_content_hash} vs expected={expected_hash}"

        return True, f"Rule '{self.constraint_id}' verified against {self.document_id} ({self.source_reference}) via {self.validation_record.verification_method}"

    def is_verified(self) -> bool:
        """Only constraints that pass the auditable provenance check are considered verified."""
        is_valid, _ = self.audit_provenance()
        return is_valid

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationConstraint:
        payload = dict(data)
        payload.setdefault("quoted_evidence", "")
        payload.setdefault("applicable_article", "")
        payload.setdefault("audit_notes", "")
        rec_data = payload.get("validation_record")
        if isinstance(rec_data, dict):
            payload["validation_record"] = SourceValidationRecord.from_dict(rec_data)
        elif rec_data is None and payload.get("constraint_type") in {"SCHEMA_TYPE", "UNIT_COMPATIBILITY"}:
            payload["validation_record"] = SourceValidationRecord(
                source_document_id=payload.get("document_id") or "SCHEMA_SPEC",
                citation_key=payload.get("document_id") or "SCHEMA_SPEC",
                verification_method="STRUCTURAL_SCHEMA",
                verification_outcome="VALID",
            )
        return cls(**payload)
