"""Evidence data models for Stage 2.

This module defines:
- EvidenceItem: an enriched, traceable unit of evidence.
- EvidenceRelation: explicit structural or semantic relationship between evidence items.
- InformationSlot: technical slot requirement definition (required/covered/missing/verified).
- EvidenceSet: a collection of evidence items and relations for a given query.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional


VALID_CONTENT_TYPES = {
    "text",
    "table",
    "legal_clause",
    "caption",
    "heading",
    "list",
    "page",
    "unknown",
}

VALID_RELATION_TYPES = {
    "table_row_to_header",
    "table_to_caption",
    "table_to_note",
    "clause_to_condition",
    "evidence_to_version",
    "parent_to_child",
    "cross_page_continuation",
    "unknown",
}

VALID_SUPPORT_STATUSES = {
    "UNVERIFIED",
    "SUPPORTED",
    "MISSING",
    "INVALID_REFERENCE",
    "CONTRADICTED",
}


@dataclass(frozen=True)
class EvidenceItem:
    """Standardized traceable evidence unit for Stage 2.

    Preserves 100% of P5 Evidence fields while supporting optional verified metadata
    such as bounding box, document identifier, publication date, and verified document version.
    """

    evidence_id: str
    doc_id: str
    page_id: str
    page_number: int
    content_type: str = "text"
    text: str = ""
    source: str = ""
    region_id: Optional[str] = None
    bbox: Optional[tuple[float, float, float, float]] = None
    document_number: Optional[str] = None
    document_version: Optional[str] = None
    publication_date: Optional[str] = None
    legal_status: Optional[str] = None
    rank: Optional[int] = None
    score: Optional[float] = None
    context_group: Optional[str] = None
    context_role: Optional[str] = None
    truncated: bool = False
    provenance_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError(f"page_number must be >= 1, got {self.page_number}")
        if self.bbox is not None:
            if len(self.bbox) != 4:
                raise ValueError(f"bbox must be a 4-tuple of (x0, y0, x1, y1), got {self.bbox}")
            for coord in self.bbox:
                if not isinstance(coord, (int, float)):
                    raise ValueError(f"bbox coordinates must be numbers, got {self.bbox}")
                if not math.isfinite(coord):
                    raise ValueError(f"bbox coordinates must be finite numbers, got {self.bbox}")
                if coord < 0:
                    raise ValueError(f"bbox coordinates must be non-negative, got {self.bbox}")
            x0, y0, x1, y1 = self.bbox
            if x1 < x0 or y1 < y0:
                raise ValueError(
                    f"Structurally impossible bbox with inverted coordinates: "
                    f"x0={x0}, y0={y0}, x1={x1}, y1={y1}"
                )
        if self.content_type not in VALID_CONTENT_TYPES:
            object.__setattr__(self, "content_type", "unknown")

    def citation_key(self) -> tuple[str, int, str]:
        """Stable 3-tuple identifier matching P5 citation identity."""
        return self.doc_id, self.page_number, self.evidence_id

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        data = asdict(self)
        if self.bbox is not None:
            data["bbox"] = list(self.bbox)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceItem:
        """Construct EvidenceItem from dictionary, validating fields."""
        payload = dict(data)
        if "bbox" in payload and payload["bbox"] is not None:
            payload["bbox"] = tuple(float(x) for x in payload["bbox"])
        if "provenance_metadata" not in payload or payload["provenance_metadata"] is None:
            payload["provenance_metadata"] = {}
        return cls(**payload)


@dataclass(frozen=True)
class EvidenceRelation:
    """Explicit structural or semantic link between two evidence items.

    Relationships must be justified by document layout or explicit textual cues;
    proximity alone must never be marked as a verified relation.
    """

    source_id: str
    target_id: str
    relation_type: str
    description: str = ""
    confidence: float = 1.0
    verified: bool = False
    provenance_source: str = ""

    def __post_init__(self) -> None:
        if self.relation_type not in VALID_RELATION_TYPES:
            object.__setattr__(self, "relation_type", "unknown")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {self.confidence}")
        if self.verified and not self.provenance_source.strip():
            raise ValueError("Verified EvidenceRelation must have a non-empty provenance_source")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceRelation:
        return cls(**data)


@dataclass(frozen=True)
class InformationSlot:
    """A required or optional informational slot for answering a technical question.

    Distinguishes reference existence (pointing to an evidence item) from verified support
    (confirmed by domain or extraction logic).
    """

    slot_id: str
    name: str
    required: bool = True
    covered_by_evidence_id: Optional[str] = None
    description: str = ""
    support_status: str = "UNVERIFIED"
    verified_support: bool = False

    def __post_init__(self) -> None:
        if self.support_status not in VALID_SUPPORT_STATUSES:
            object.__setattr__(self, "support_status", "UNVERIFIED")

        # Problem B: Contradictory slot verification state
        # A contradicted or missing/invalid state must NEVER be marked as verified support.
        if self.support_status == "CONTRADICTED" and self.verified_support:
            raise ValueError(
                f"Contradictory slot verification state in slot '{self.slot_id}': "
                f"support_status cannot be 'CONTRADICTED' while verified_support is True"
            )
        if self.support_status in ("MISSING", "INVALID_REFERENCE") and self.verified_support:
            raise ValueError(
                f"Invalid slot verification state in slot '{self.slot_id}': "
                f"support_status cannot be '{self.support_status}' while verified_support is True"
            )
        # If verified_support is True and support_status is default UNVERIFIED, normalize to SUPPORTED
        if self.verified_support and self.support_status == "UNVERIFIED":
            object.__setattr__(self, "support_status", "SUPPORTED")

    def has_valid_reference(self, evidence_set: Optional[EvidenceSet] = None) -> bool:
        """Check if the referenced evidence ID exists in the provided EvidenceSet."""
        if not self.covered_by_evidence_id:
            return False
        if evidence_set is not None:
            return evidence_set.get_item(self.covered_by_evidence_id) is not None
        return True

    def is_covered(self, evidence_set: Optional[EvidenceSet] = None) -> bool:
        """Slot is only covered if it references an existing item AND has verified support.

        Never counts a slot as verified coverage merely because its ID field is populated,
        nor if the slot is contradicted or merely asserted as supported without verification.
        """
        if self.support_status in ("CONTRADICTED", "INVALID_REFERENCE", "MISSING"):
            return False
        if not self.has_valid_reference(evidence_set):
            return False
        return bool(self.verified_support and self.support_status == "SUPPORTED")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InformationSlot:
        return cls(**data)


@dataclass
class EvidenceSet:
    """A collection of related evidence items assembled for a technical query.

    Tracks evidence relations, required slots, covered slots, referenced unverified slots,
    and missing slots.
    Note: A missing slot indicates incomplete evidence, NOT a contradiction.
    """

    query_id: str
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    evidence_relations: list[EvidenceRelation] = field(default_factory=list)
    required_slots: list[InformationSlot] = field(default_factory=list)
    covered_slots: list[InformationSlot] = field(default_factory=list)
    missing_slots: list[InformationSlot] = field(default_factory=list)
    referenced_unverified_slots: list[InformationSlot] = field(default_factory=list)
    invalid_reference_slots: list[InformationSlot] = field(default_factory=list)
    completeness_status: str = "UNKNOWN"
    assembly_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Enforce identity, reference, and relation invariants upon direct instantiation."""
        raw_items = list(self.evidence_items)
        raw_relations = list(self.evidence_relations)
        self.evidence_items = []
        self.evidence_relations = []
        for item in raw_items:
            self.add_item(item)
        for rel in raw_relations:
            self.add_relation(rel)
        self.update_slot_coverage()

    def add_item(self, item: EvidenceItem) -> None:
        """Add an evidence item while enforcing citation identity consistency.

        Does not silently discard different records sharing the same evidence_id.
        Raises ValueError if conflicting records share the same evidence_id.
        """
        for existing in self.evidence_items:
            if existing.evidence_id == item.evidence_id:
                if (
                    existing.citation_key() == item.citation_key()
                    and existing.text == item.text
                    and existing.content_type == item.content_type
                ):
                    return  # Exact duplicate: idempotent ignore
                raise ValueError(
                    f"Conflicting evidence items sharing ID '{item.evidence_id}': "
                    f"existing=({existing.citation_key()}, text_len={len(existing.text)}) vs "
                    f"new=({item.citation_key()}, text_len={len(item.text)})"
                )
        self.evidence_items.append(item)

    def get_item(self, evidence_id: str) -> Optional[EvidenceItem]:
        """Retrieve an evidence item by its evidence_id."""
        for item in self.evidence_items:
            if item.evidence_id == evidence_id:
                return item
        return None

    def get_item_by_citation(
        self, doc_id: str, page_number: int, evidence_id: str
    ) -> Optional[EvidenceItem]:
        """Retrieve evidence only when the complete P5 citation identity matches."""
        expected = (doc_id, page_number, evidence_id)
        for item in self.evidence_items:
            if item.citation_key() == expected:
                return item
        return None

    def add_relation(self, relation: EvidenceRelation, allow_orphaned: bool = False) -> None:
        """Add an evidence relationship, rejecting orphaned links unless explicitly allowed."""
        if not allow_orphaned:
            item_ids = {it.evidence_id for it in self.evidence_items}
            missing = []
            if relation.source_id not in item_ids:
                missing.append(f"source '{relation.source_id}'")
            if relation.target_id not in item_ids:
                missing.append(f"target '{relation.target_id}'")
            if missing:
                raise ValueError(
                    f"Orphaned evidence relation rejected: {', '.join(missing)} not in EvidenceSet"
                )
        if relation.verified and not relation.provenance_source.strip():
            raise ValueError(
                f"Verified relation {relation.source_id}->{relation.target_id} "
                f"must have a non-empty provenance_source"
            )
        self.evidence_relations.append(relation)

    def update_slot_coverage(self) -> None:
        """Compute covered, referenced unverified, and missing slots from required_slots.

        Never counts a slot as verified coverage merely because its ID field is populated.
        Verifies that referenced evidence exists in this EvidenceSet.
        Properly handles required vs optional slots (Problem C): missing optional slots
        do NOT prevent completeness.
        """
        item_ids = {item.evidence_id for item in self.evidence_items}
        covered: list[InformationSlot] = []
        referenced_unverified: list[InformationSlot] = []
        missing: list[InformationSlot] = []
        invalid_references: list[InformationSlot] = []

        for slot in self.required_slots:
            ref_id = slot.covered_by_evidence_id
            if not ref_id:
                if slot.required:
                    missing.append(slot)
            elif ref_id not in item_ids:
                # Referenced ID does not exist in this set
                invalid_slot = InformationSlot(
                    slot_id=slot.slot_id,
                    name=slot.name,
                    required=slot.required,
                    covered_by_evidence_id=ref_id,
                    description=slot.description,
                    support_status="INVALID_REFERENCE",
                    verified_support=False,
                )
                invalid_references.append(invalid_slot)
                if slot.required:
                    missing.append(invalid_slot)
            elif slot.support_status == "CONTRADICTED":
                # Contradicted slot cannot be covered
                contra_slot = InformationSlot(
                    slot_id=slot.slot_id,
                    name=slot.name,
                    required=slot.required,
                    covered_by_evidence_id=ref_id,
                    description=slot.description,
                    support_status="CONTRADICTED",
                    verified_support=False,
                )
                if slot.required:
                    missing.append(contra_slot)
            elif slot.verified_support and slot.support_status == "SUPPORTED":
                covered_slot = InformationSlot(
                    slot_id=slot.slot_id,
                    name=slot.name,
                    required=slot.required,
                    covered_by_evidence_id=ref_id,
                    description=slot.description,
                    support_status="SUPPORTED",
                    verified_support=True,
                )
                covered.append(covered_slot)
            else:
                unverified_slot = InformationSlot(
                    slot_id=slot.slot_id,
                    name=slot.name,
                    required=slot.required,
                    covered_by_evidence_id=ref_id,
                    description=slot.description,
                    support_status="UNVERIFIED",
                    verified_support=False,
                )
                referenced_unverified.append(unverified_slot)

        self.covered_slots = covered
        self.referenced_unverified_slots = referenced_unverified
        self.missing_slots = missing
        self.invalid_reference_slots = invalid_references

        # Completeness calculation is strictly governed by required slots (Problem C)
        req_slots = [s for s in self.required_slots if s.required]
        req_covered = [s for s in covered if s.required]
        req_unverified = [s for s in referenced_unverified if s.required]
        req_missing = [s for s in missing if s.required]

        if not req_slots:
            self.completeness_status = "UNKNOWN"
        elif req_missing:
            if req_covered or req_unverified:
                self.completeness_status = "PARTIAL"
            else:
                self.completeness_status = "INSUFFICIENT"
        elif req_unverified:
            # All required slots reference existing items, but support is unverified!
            # Conservative status: NEVER mark complete purely from unverified references!
            self.completeness_status = "REFERENCED_UNVERIFIED"
        elif len(req_covered) == len(req_slots):
            self.completeness_status = "COMPLETE"
        else:
            self.completeness_status = "INSUFFICIENT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "evidence_items": [item.to_dict() for item in self.evidence_items],
            "evidence_relations": [rel.to_dict() for rel in self.evidence_relations],
            "required_slots": [slot.to_dict() for slot in self.required_slots],
            "covered_slots": [slot.to_dict() for slot in self.covered_slots],
            "referenced_unverified_slots": [slot.to_dict() for slot in self.referenced_unverified_slots],
            "missing_slots": [slot.to_dict() for slot in self.missing_slots],
            "invalid_reference_slots": [slot.to_dict() for slot in self.invalid_reference_slots],
            "completeness_status": self.completeness_status,
            "assembly_metadata": self.assembly_metadata,
        }

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceSet:
        """Construct EvidenceSet enforcing identity, reference, and relation invariants.

        Never trusts serialized completeness_status blindly (Problem A & D).
        Recomputes completeness from validated items and required slots.
        Rejects conflicting items and orphaned relations.
        """
        instance = cls(
            query_id=data.get("query_id", ""),
            assembly_metadata=data.get("assembly_metadata", {}),
        )

        # 1. Enforce duplicate identity rules via add_item()
        for item_data in data.get("evidence_items", []):
            item = EvidenceItem.from_dict(item_data)
            instance.add_item(item)

        # 2. Enforce relation integrity (reject orphaned relations) via add_relation()
        for rel_data in data.get("evidence_relations", []):
            relation = EvidenceRelation.from_dict(rel_data)
            instance.add_relation(relation)

        # 3. Load required slots
        for slot_data in data.get("required_slots", []):
            instance.required_slots.append(InformationSlot.from_dict(slot_data))

        # 4. Recompute slot coverage and derived completeness status
        instance.update_slot_coverage()

        return instance

    @classmethod
    def from_json(cls, json_str: str) -> EvidenceSet:
        return cls.from_dict(json.loads(json_str))
