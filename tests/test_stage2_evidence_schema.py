"""Comprehensive unit tests for Stage 2 Evidence and Claim Schemas, Adapters, and Provenance.

Includes regression tests for:
1. P5 Evidence adaptation (lossless preservation of P5 fields, zero fabrication).
2. Clean separation of document_number, publication_date, legal_status, and document_version.
3. Strict metadata join validation (region_id, doc_id, page_number) and conflicting duplicate detection.
4. Prevention of false completeness in EvidenceSet (empty set, nonexistent references, unverified references).
5. Identity policy enforcing conflict rejection for shared evidence_ids.
6. Orphaned relation rejection and verified link provenance enforcement.
7. Bounding box structural validity (non-negative, finite, non-inverted).
8. Safe polarity handling (UNKNOWN default, explicit validation, rejection of invalid values).
9. Adversarial fixtures for P5-KNOWN-01 (multi-word jurisdiction) and P5-KNOWN-02 (legal negation).
"""

from __future__ import annotations

import math
import pytest

from viirr_rag.pipeline import Evidence
from viirr_ontology.schema import (
    EvidenceItem,
    EvidenceRelation,
    EvidenceSet,
    InformationSlot,
    TechnicalClaim,
    ClaimCondition,
    ClaimPolarity,
)
from viirr_ontology.adapters import P5EvidenceAdapter, MetadataLookup


@pytest.fixture
def sample_p5_evidence() -> Evidence:
    """Fixture providing a standard P5 Evidence dataclass."""
    return Evidence(
        rank=1,
        evidence_id="REG_IRR_CP_2019_ee0bca33_P0012_B004",
        doc_id="IRR_CP_2019_ee0bca33",
        page_id="PAGE_IRR_CP_2019_ee0bca33_0012",
        page_number=12,
        unit_type="TEXT_REGION",
        score=0.8875,
        text="Mực nước hồ Hòa Bình mùa lũ không được vượt quá cao trình +117.0 m.",
        source="retrieved_b3_window_top10",
        truncated=False,
        context_group="LEGAL:IRR_CP_2019_ee0bca33:P0012",
        context_role="legal_condition",
    )


# =========================================================================
# 1. EVIDENCE ADAPTATION AND METADATA SEPARATION TESTS
# =========================================================================

def test_p5_adapter_preserves_all_p5_fields(sample_p5_evidence):
    """Every single field of the P5 Evidence dataclass must be preserved in EvidenceItem."""
    item = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)

    assert item.rank == sample_p5_evidence.rank
    assert item.evidence_id == sample_p5_evidence.evidence_id
    assert item.doc_id == sample_p5_evidence.doc_id
    assert item.page_id == sample_p5_evidence.page_id
    assert item.page_number == sample_p5_evidence.page_number
    assert item.score == sample_p5_evidence.score
    assert item.text == sample_p5_evidence.text
    assert item.source == sample_p5_evidence.source
    assert item.truncated == sample_p5_evidence.truncated
    assert item.context_group == sample_p5_evidence.context_group
    assert item.context_role == sample_p5_evidence.context_role


def test_p5_adapter_preserves_citation_identity(sample_p5_evidence):
    """Citation key (doc_id, page_number, evidence_id) must strictly match P5."""
    item = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)

    assert item.citation_key() == sample_p5_evidence.citation_key()
    assert item.citation_key() == ("IRR_CP_2019_ee0bca33", 12, "REG_IRR_CP_2019_ee0bca33_P0012_B004")


def test_p5_adapter_does_not_mutate_input(sample_p5_evidence):
    """Input P5 Evidence object must remain strictly unmodified."""
    original_dict = sample_p5_evidence.to_dict()
    _ = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)

    assert sample_p5_evidence.to_dict() == original_dict


def test_missing_metadata_is_not_fabricated(sample_p5_evidence):
    """When no verified metadata join is supplied, bbox and document_version MUST be None."""
    item = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence, lookup=None)

    assert item.bbox is None
    assert item.document_version is None
    assert item.document_number is None
    assert item.publication_date is None
    assert item.provenance_metadata["enriched_fields"] == []


def test_document_metadata_separation_date_and_number_not_version(sample_p5_evidence):
    """Document number and publication date must NOT be coerced into document_version."""
    lookup = MetadataLookup.from_dicts(
        documents=[
            {
                "doc_id": "IRR_CP_2019_ee0bca33",
                "document_number": "740/QĐ-TTg",
                "version_status": "CURRENT",
                "publication_date": "2019-06-17",
            }
        ]
    )

    item = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence, lookup=lookup)

    assert item.document_number == "740/QĐ-TTg"
    assert item.publication_date == "2019-06-17"
    assert item.legal_status == "CURRENT"
    # Crucial scientific check: document_version must remain None when not explicitly defined!
    assert item.document_version is None


def test_document_metadata_with_explicit_version(sample_p5_evidence):
    """When an explicit version is provided, document_version is populated correctly."""
    lookup = MetadataLookup.from_dicts(
        documents=[
            {
                "doc_id": "IRR_CP_2019_ee0bca33",
                "document_number": "740/QĐ-TTg",
                "document_version": "2019_v1",
                "publication_date": "2019-06-17",
            }
        ]
    )

    item = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence, lookup=lookup)

    assert item.document_version == "2019_v1"
    assert item.document_number == "740/QĐ-TTg"


def test_verified_metadata_enrichment_succeeds(sample_p5_evidence):
    """Verified metadata lookup accurately enriches bbox and document fields with provenance."""
    lookup = MetadataLookup.from_dicts(
        regions=[
            {
                "doc_id": "IRR_CP_2019_ee0bca33",
                "page_number": 12,
                "region_id": "REG_IRR_CP_2019_ee0bca33_P0012_B004",
                "bbox": [54.0, 120.5, 480.0, 160.2],
            }
        ],
        documents=[
            {
                "doc_id": "IRR_CP_2019_ee0bca33",
                "document_number": "740/QĐ-TTg",
                "document_version": "2019_v1",
                "publication_date": "2019-06-17",
            }
        ],
    )

    item = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence, lookup=lookup)

    assert item.bbox == (54.0, 120.5, 480.0, 160.2)
    assert item.document_version == "2019_v1"
    assert "bbox" in item.provenance_metadata["enriched_fields"]
    assert "document_version" in item.provenance_metadata["enriched_fields"]
    assert item.provenance_metadata["bbox_source"] == "verified_region_record"
    assert item.provenance_metadata["document_version_source"] == "verified_document_record"


def test_mismatched_region_id_rejected(sample_p5_evidence):
    """Mismatched region_id in lookup record must raise ValueError."""
    bad_lookup = MetadataLookup(
        region_records={
            (sample_p5_evidence.doc_id, sample_p5_evidence.page_number, sample_p5_evidence.evidence_id): {
                "doc_id": sample_p5_evidence.doc_id,
                "page_number": sample_p5_evidence.page_number,
                "region_id": "WRONG_REGION_ID",
                "bbox": [10.0, 20.0, 30.0, 40.0],
            }
        }
    )

    with pytest.raises(ValueError, match="Mismatched region metadata join"):
        P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence, lookup=bad_lookup)


def test_mismatched_document_id_rejected(sample_p5_evidence):
    """Mismatched doc_id in document record must raise ValueError."""
    bad_lookup = MetadataLookup(
        document_records={
            sample_p5_evidence.doc_id: {
                "doc_id": "DIFFERENT_DOC_ID",
                "document_number": "922/QĐ-TTg",
            }
        }
    )

    with pytest.raises(ValueError, match="Mismatched document metadata join"):
        P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence, lookup=bad_lookup)


def test_duplicate_conflicting_lookup_records_rejected():
    """MetadataLookup must detect and reject conflicting duplicate records."""
    conflicting_regions = [
        {"doc_id": "D1", "page_number": 1, "region_id": "R1", "bbox": [1.0, 2.0, 3.0, 4.0]},
        {"doc_id": "D1", "page_number": 1, "region_id": "R1", "bbox": [5.0, 6.0, 7.0, 8.0]},
    ]
    with pytest.raises(ValueError, match="Conflicting duplicate region lookup record"):
        MetadataLookup.from_dicts(regions=conflicting_regions)

    # Identical duplicates are accepted
    identical_regions = [
        {"doc_id": "D1", "page_number": 1, "region_id": "R1", "bbox": [1.0, 2.0, 3.0, 4.0]},
        {"doc_id": "D1", "page_number": 1, "region_id": "R1", "bbox": [1.0, 2.0, 3.0, 4.0]},
    ]
    lookup = MetadataLookup.from_dicts(regions=identical_regions)
    assert lookup.lookup_region("D1", 1, "R1")["bbox"] == [1.0, 2.0, 3.0, 4.0]


def test_reverse_projection_to_p5(sample_p5_evidence):
    """EvidenceItem projected back to P5 Evidence retains core P5 fields without pretending Stage 2 fields existed."""
    item = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)
    reconstructed_p5 = P5EvidenceAdapter.to_p5_evidence(item)

    assert isinstance(reconstructed_p5, Evidence)
    assert reconstructed_p5.evidence_id == sample_p5_evidence.evidence_id
    assert reconstructed_p5.citation_key() == sample_p5_evidence.citation_key()
    assert reconstructed_p5.text == sample_p5_evidence.text
    assert reconstructed_p5.score == sample_p5_evidence.score


# =========================================================================
# 2. BBOX VALIDATION TESTS
# =========================================================================

def test_evidence_item_bbox_validation():
    """Bbox coordinates must be finite, non-negative numbers with x0 <= x1 and y0 <= y1."""
    # Negative coordinate
    with pytest.raises(ValueError, match="non-negative"):
        EvidenceItem(
            evidence_id="E1", doc_id="D1", page_id="P1", page_number=1,
            bbox=(-10.0, 20.0, 30.0, 40.0)
        )

    # Inverted coordinates: x1 < x0
    with pytest.raises(ValueError, match="inverted coordinates"):
        EvidenceItem(
            evidence_id="E1", doc_id="D1", page_id="P1", page_number=1,
            bbox=(100.0, 20.0, 50.0, 40.0)
        )

    # Inverted coordinates: y1 < y0
    with pytest.raises(ValueError, match="inverted coordinates"):
        EvidenceItem(
            evidence_id="E1", doc_id="D1", page_id="P1", page_number=1,
            bbox=(10.0, 80.0, 30.0, 40.0)
        )

    # Non-finite coordinates (inf or nan)
    with pytest.raises(ValueError, match="finite"):
        EvidenceItem(
            evidence_id="E1", doc_id="D1", page_id="P1", page_number=1,
            bbox=(10.0, float("nan"), 30.0, 40.0)
        )

    # Valid bbox succeeds
    valid_item = EvidenceItem(
        evidence_id="E1", doc_id="D1", page_id="P1", page_number=1,
        bbox=(10.0, 20.0, 30.0, 40.0)
    )
    assert valid_item.bbox == (10.0, 20.0, 30.0, 40.0)


# =========================================================================
# 3. EVIDENCE SET & RELATION INTEGRITY TESTS
# =========================================================================

def test_evidence_set_false_completeness_prevented_when_empty():
    """EvidenceSet with no items must NEVER become COMPLETE even if a slot has a reference ID."""
    evidence_set = EvidenceSet(query_id="Q-EMPTY")
    evidence_set.required_slots = [
        InformationSlot(slot_id="s1", name="water_level", covered_by_evidence_id="NONEXISTENT_ID")
    ]
    evidence_set.update_slot_coverage()

    # Must be INSUFFICIENT, NEVER COMPLETE
    assert evidence_set.completeness_status == "INSUFFICIENT"
    assert len(evidence_set.missing_slots) == 1
    assert len(evidence_set.invalid_reference_slots) == 1
    assert len(evidence_set.covered_slots) == 0


def test_evidence_set_referenced_unverified_slot_is_not_complete(sample_p5_evidence):
    """Slot referencing an existing item whose support is unverified cannot make set COMPLETE."""
    item = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)
    evidence_set = EvidenceSet(query_id="Q-UNVERIFIED")
    evidence_set.add_item(item)

    # Slot references item.evidence_id, but verified_support is False
    slot = InformationSlot(
        slot_id="s1",
        name="water_level",
        covered_by_evidence_id=item.evidence_id,
        verified_support=False,
    )
    evidence_set.required_slots = [slot]
    evidence_set.update_slot_coverage()

    # Conservative status: REFERENCED_UNVERIFIED, NOT COMPLETE!
    assert evidence_set.completeness_status == "REFERENCED_UNVERIFIED"
    assert len(evidence_set.covered_slots) == 0
    assert len(evidence_set.referenced_unverified_slots) == 1


def test_evidence_set_completeness_requires_all_slots_verified(sample_p5_evidence):
    """EvidenceSet becomes COMPLETE only when all slots reference existing items AND have verified support."""
    item1 = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)
    item2 = EvidenceItem(
        evidence_id="REG_IRR_CP_2019_ee0bca33_P0012_B001",
        doc_id="IRR_CP_2019_ee0bca33",
        page_id="PAGE_IRR_CP_2019_ee0bca33_0012",
        page_number=12,
        content_type="heading",
        text="Điều 12. Vận hành giảm lũ cho hạ du",
    )
    evidence_set = EvidenceSet(query_id="Q-VERIFIED")
    evidence_set.add_item(item1)
    evidence_set.add_item(item2)

    slot1 = InformationSlot(
        slot_id="s1", name="water_level", covered_by_evidence_id=item1.evidence_id, verified_support=True
    )
    slot2 = InformationSlot(
        slot_id="s2", name="rule", covered_by_evidence_id=item2.evidence_id, verified_support=True
    )
    evidence_set.required_slots = [slot1, slot2]
    evidence_set.update_slot_coverage()

    assert evidence_set.completeness_status == "COMPLETE"
    assert len(evidence_set.covered_slots) == 2
    assert len(evidence_set.missing_slots) == 0


def test_evidence_set_rejects_conflicting_items_sharing_id(sample_p5_evidence):
    """EvidenceSet must reject different records sharing the same evidence_id."""
    evidence_set = EvidenceSet(query_id="Q-CONF")
    item1 = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)
    evidence_set.add_item(item1)

    # Identical item is safely ignored (idempotent)
    evidence_set.add_item(item1)
    assert len(evidence_set.evidence_items) == 1

    # Conflicting item with same ID but different text must raise ValueError
    conflicting_item = EvidenceItem(
        evidence_id=item1.evidence_id,
        doc_id=item1.doc_id,
        page_id=item1.page_id,
        page_number=item1.page_number,
        text="Different conflicting text",
    )
    with pytest.raises(ValueError, match="Conflicting evidence items"):
        evidence_set.add_item(conflicting_item)


def test_evidence_set_rejects_orphaned_relations(sample_p5_evidence):
    """EvidenceRelation with source or target not in EvidenceSet must be rejected."""
    item = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)
    evidence_set = EvidenceSet(query_id="Q-REL")
    evidence_set.add_item(item)

    orphaned_rel = EvidenceRelation(
        source_id=item.evidence_id,
        target_id="NON_EXISTENT_TARGET",
        relation_type="parent_to_child",
    )
    with pytest.raises(ValueError, match="Orphaned evidence relation rejected"):
        evidence_set.add_relation(orphaned_rel)


def test_evidence_relation_verified_requires_provenance():
    """Verified EvidenceRelation must have non-empty provenance_source."""
    with pytest.raises(ValueError, match="non-empty provenance_source"):
        EvidenceRelation(
            source_id="S1", target_id="T1", relation_type="table_to_note",
            verified=True, provenance_source=""
        )


def test_evidence_set_json_roundtrip(sample_p5_evidence):
    """EvidenceSet must cleanly serialize and deserialize to/from JSON."""
    item = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)
    evidence_set = EvidenceSet(
        query_id="Q-JSON-001",
        evidence_items=[item],
        evidence_relations=[
            EvidenceRelation(
                source_id=item.evidence_id,
                target_id=item.evidence_id,
                relation_type="parent_to_child",
            )
        ],
        required_slots=[
            InformationSlot(
                slot_id="s1", name="parameter", covered_by_evidence_id=item.evidence_id, verified_support=True
            )
        ],
        assembly_metadata={"builder": "test_builder", "version": "1.0"},
    )
    evidence_set.update_slot_coverage()

    json_str = evidence_set.to_json()
    reconstructed = EvidenceSet.from_json(json_str)

    assert reconstructed.query_id == evidence_set.query_id
    assert len(reconstructed.evidence_items) == 1
    assert reconstructed.evidence_items[0].evidence_id == item.evidence_id
    assert reconstructed.evidence_items[0].citation_key() == item.citation_key()
    assert reconstructed.completeness_status == "COMPLETE"
    assert reconstructed.assembly_metadata["builder"] == "test_builder"


# =========================================================================
# 4. TECHNICAL CLAIM & SAFE POLARITY TESTS
# =========================================================================

def test_claim_polarity_unknown_default():
    """Default polarity of TechnicalClaim must be UNKNOWN, NEVER assumed AFFIRMED."""
    claim = TechnicalClaim(claim_id="C1", claim_text="Mực nước hồ Hòa Bình")
    assert claim.polarity == ClaimPolarity.UNKNOWN


def test_claim_polarity_explicit_affirmed_negated_uncertain():
    """AFFIRMED, NEGATED, UNCERTAIN, and UNKNOWN are cleanly distinguished."""
    c_aff = TechnicalClaim(claim_id="C1", claim_text="T", polarity=ClaimPolarity.AFFIRMED)
    c_neg = TechnicalClaim(claim_id="C2", claim_text="T", polarity=ClaimPolarity.NEGATED)
    c_unc = TechnicalClaim(claim_id="C3", claim_text="T", polarity=ClaimPolarity.UNCERTAIN)
    c_unk = TechnicalClaim(claim_id="C4", claim_text="T", polarity=ClaimPolarity.UNKNOWN)

    assert c_aff.polarity == ClaimPolarity.AFFIRMED
    assert c_neg.polarity == ClaimPolarity.NEGATED
    assert c_unc.polarity == ClaimPolarity.UNCERTAIN
    assert c_unk.polarity == ClaimPolarity.UNKNOWN


def test_claim_polarity_invalid_value_raises():
    """Invalid polarity string in from_dict must raise ValueError rather than falling back to AFFIRMED."""
    invalid_data = {
        "claim_id": "C-BAD",
        "claim_text": "Test claim",
        "polarity": "INVALID_POLARITY_VALUE",
    }
    with pytest.raises(ValueError, match="Invalid claim polarity"):
        TechnicalClaim.from_dict(invalid_data)


def test_claim_polarity_missing_value_becomes_unknown():
    """Missing or None polarity in from_dict must safely become UNKNOWN."""
    data_missing = {"claim_id": "C1", "claim_text": "Test claim"}
    claim = TechnicalClaim.from_dict(data_missing)
    assert claim.polarity == ClaimPolarity.UNKNOWN

    data_none = {"claim_id": "C1", "claim_text": "Test claim", "polarity": None}
    claim_none = TechnicalClaim.from_dict(data_none)
    assert claim_none.polarity == ClaimPolarity.UNKNOWN


def test_technical_claim_structure_and_json():
    """TechnicalClaim represents structured technical facts and conditions."""
    claim = TechnicalClaim(
        claim_id="CLAIM-001",
        claim_text="Mực nước hồ Hòa Bình mùa lũ không vượt quá cao trình 117.0 m theo QĐ 740/QĐ-TTg.",
        subject="Hồ Hòa Bình",
        parameter="Mực nước mùa lũ",
        value="117.0",
        unit="m",
        temporal_scope="mùa lũ",
        conditions=[ClaimCondition(operator="LE", value="117.0", unit="m", raw_text="không vượt quá cao trình 117.0 m")],
        document_scope="740/QĐ-TTg",
        evidence_ids=["REG_IRR_CP_2019_ee0bca33_P0012_B004"],
        polarity=ClaimPolarity.AFFIRMED,
        jurisdiction="Trung ương",
        action=None,
    )

    data = claim.to_dict()
    assert data["subject"] == "Hồ Hòa Bình"
    assert data["polarity"] == "AFFIRMED"
    assert len(data["conditions"]) == 1

    reconstructed = TechnicalClaim.from_json(claim.to_json())
    assert reconstructed.claim_id == claim.claim_id
    assert reconstructed.conditions[0].operator == "LE"
    assert reconstructed.polarity == ClaimPolarity.AFFIRMED


def test_p5_known_01_fixture_multiword_jurisdiction():
    """P5-KNOWN-01 Fixture: TechnicalClaim preserves multi-word jurisdiction names.

    In P5, regex matched only the first word 'dong' for both 'Đồng Nai' and 'Đồng Tháp'.
    Stage 2 TechnicalClaim cleanly preserves and distinguishes full jurisdiction strings.
    """
    claim_dong_nai = TechnicalClaim(
        claim_id="CLAIM-P5-01-DN",
        claim_text="Công trình xả lũ thuộc địa bàn tỉnh Đồng Nai.",
        subject="Hồ Trị An",
        jurisdiction="tỉnh Đồng Nai",
        polarity=ClaimPolarity.AFFIRMED,
    )
    claim_dong_thap = TechnicalClaim(
        claim_id="CLAIM-P5-01-DT",
        claim_text="Công trình xả lũ thuộc địa bàn tỉnh Đồng Tháp.",
        subject="Hồ Trị An",
        jurisdiction="tỉnh Đồng Tháp",
        polarity=ClaimPolarity.AFFIRMED,
    )

    assert claim_dong_nai.jurisdiction != claim_dong_thap.jurisdiction
    assert "Đồng Nai" in claim_dong_nai.jurisdiction
    assert "Đồng Tháp" in claim_dong_thap.jurisdiction


def test_p5_known_02_fixture_legal_negation():
    """P5-KNOWN-02 Fixture: TechnicalClaim isolates action and negation polarity.

    In P5, 'không được quyết định' was mistakenly parsed as AFFIRMED 'quyết định'
    because of the intervening word 'được'.
    Stage 2 TechnicalClaim decouples action ('quyết định') and polarity (NEGATED).
    """
    evidence_claim = TechnicalClaim(
        claim_id="CLAIM-P5-02-EVID",
        claim_text="Chủ tịch UBND tỉnh quyết định xả lũ.",
        subject="Chủ tịch UBND cấp tỉnh",
        action="quyết định",
        polarity=ClaimPolarity.AFFIRMED,
    )
    answer_claim = TechnicalClaim(
        claim_id="CLAIM-P5-02-ANS",
        claim_text="Chủ tịch UBND tỉnh không được quyết định xả lũ.",
        subject="Chủ tịch UBND cấp tỉnh",
        action="quyết định",
        polarity=ClaimPolarity.NEGATED,
    )

    assert evidence_claim.action == answer_claim.action == "quyết định"
    assert evidence_claim.polarity == ClaimPolarity.AFFIRMED
    assert answer_claim.polarity == ClaimPolarity.NEGATED
    assert evidence_claim.polarity != answer_claim.polarity


# =========================================================================
# 5. PHASE 0 ADVERSARIAL INTEGRITY TESTS (PROBLEMS A, B, C, D)
# =========================================================================

def test_phase0_problem_a_unsafe_deserialization_completeness_recomputed():
    """Problem A: from_dict must NEVER trust serialized completeness_status without validation.

    Adversarial test: JSON claims completeness_status="COMPLETE" with no evidence items
    and a fabricated verified slot reference. Recomputed status must be INSUFFICIENT.
    """
    tampered_data = {
        "query_id": "Q-TAMPERED",
        "evidence_items": [],
        "evidence_relations": [],
        "required_slots": [
            {
                "slot_id": "s_fabricated",
                "name": "design_discharge",
                "required": True,
                "covered_by_evidence_id": "FABRICATED_EVID_ID",
                "description": "Fabricated reference link",
                "support_status": "SUPPORTED",
                "verified_support": True,
            }
        ],
        "completeness_status": "COMPLETE",  # Tampered status!
        "assembly_metadata": {},
    }

    reconstructed = EvidenceSet.from_dict(tampered_data)

    # Invariants enforced: status recomputed, NOT trusted blindly
    assert reconstructed.completeness_status == "INSUFFICIENT"
    assert len(reconstructed.covered_slots) == 0
    assert len(reconstructed.missing_slots) == 1
    assert len(reconstructed.invalid_reference_slots) == 1
    assert reconstructed.invalid_reference_slots[0].support_status == "INVALID_REFERENCE"


def test_phase0_problem_b_contradictory_slot_verification_state_rejected():
    """Problem B: support_status="CONTRADICTED" and verified_support=True must be strictly rejected."""
    with pytest.raises(ValueError, match="Contradictory slot verification state"):
        InformationSlot(
            slot_id="s_contra",
            name="sluice_gate_status",
            required=True,
            covered_by_evidence_id="EVID_01",
            support_status="CONTRADICTED",
            verified_support=True,
        )

    with pytest.raises(ValueError, match="Invalid slot verification state"):
        InformationSlot(
            slot_id="s_invalid",
            name="sluice_gate_status",
            required=True,
            covered_by_evidence_id="EVID_01",
            support_status="INVALID_REFERENCE",
            verified_support=True,
        )


def test_phase0_problem_b_contradicted_slot_is_never_covered(sample_p5_evidence):
    """Problem B: A slot with support_status="CONTRADICTED" must NEVER be considered covered."""
    item = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)
    slot = InformationSlot(
        slot_id="s_contra",
        name="water_level",
        covered_by_evidence_id=item.evidence_id,
        support_status="CONTRADICTED",
        verified_support=False,
    )

    evidence_set = EvidenceSet(query_id="Q-CONTRA")
    evidence_set.add_item(item)

    # is_covered must return False
    assert not slot.is_covered(evidence_set)

    # When evaluated in EvidenceSet, contradicted slot prevents COMPLETE status
    evidence_set.required_slots = [slot]
    evidence_set.update_slot_coverage()

    assert evidence_set.completeness_status == "INSUFFICIENT"
    assert len(evidence_set.covered_slots) == 0
    assert len(evidence_set.missing_slots) == 1


def test_phase0_problem_b_unverified_support_assertion_is_not_proof(sample_p5_evidence):
    """Problem B: A caller asserting support_status='SUPPORTED' without verified_support=True

    is treated conservatively as unverified reference, not independent proof of factual support.
    """
    item = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)
    slot = InformationSlot(
        slot_id="s_unverified_claim",
        name="water_level",
        covered_by_evidence_id=item.evidence_id,
        support_status="SUPPORTED",
        verified_support=False,  # Unverified!
    )

    evidence_set = EvidenceSet(query_id="Q-ASSERT")
    evidence_set.add_item(item)
    evidence_set.required_slots = [slot]
    evidence_set.update_slot_coverage()

    # Must be REFERENCED_UNVERIFIED, not COMPLETE
    assert evidence_set.completeness_status == "REFERENCED_UNVERIFIED"
    assert len(evidence_set.covered_slots) == 0
    assert len(evidence_set.referenced_unverified_slots) == 1


def test_phase0_problem_c_optional_slots_do_not_prevent_completeness(sample_p5_evidence):
    """Problem C: A slot with required=False must NOT prevent completeness if missing."""
    item = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)
    evidence_set = EvidenceSet(query_id="Q-OPTIONAL")
    evidence_set.add_item(item)

    # Required slot is covered and verified
    req_slot = InformationSlot(
        slot_id="s_req",
        name="mandatory_water_level",
        required=True,
        covered_by_evidence_id=item.evidence_id,
        verified_support=True,
    )
    # Optional slot is missing (covered_by_evidence_id=None)
    opt_slot = InformationSlot(
        slot_id="s_opt",
        name="optional_water_temperature",
        required=False,
        covered_by_evidence_id=None,
    )

    evidence_set.required_slots = [req_slot, opt_slot]
    evidence_set.update_slot_coverage()

    # Mandatory slot is covered, missing optional slot does NOT downgrade completeness
    assert evidence_set.completeness_status == "COMPLETE"
    assert len(evidence_set.covered_slots) == 1
    assert len(evidence_set.missing_slots) == 0  # Only required slots count toward missing

    # Conversely, if required slot is missing, completeness must be INSUFFICIENT even if optional is covered
    evidence_set2 = EvidenceSet(query_id="Q-OPTIONAL-2")
    evidence_set2.add_item(item)
    missing_req = InformationSlot(slot_id="s_req2", name="mandatory_rule", required=True)
    covered_opt = InformationSlot(
        slot_id="s_opt2",
        name="optional_obs",
        required=False,
        covered_by_evidence_id=item.evidence_id,
        verified_support=True,
    )
    evidence_set2.required_slots = [missing_req, covered_opt]
    evidence_set2.update_slot_coverage()

    assert evidence_set2.completeness_status == "INSUFFICIENT"


def test_phase0_problem_d_deserialization_rejects_orphaned_relations(sample_p5_evidence):
    """Problem D: from_dict must reject orphaned relations just like add_relation()."""
    item = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)
    serialized = {
        "query_id": "Q-ORPHAN-DESER",
        "evidence_items": [item.to_dict()],
        "evidence_relations": [
            {
                "source_id": item.evidence_id,
                "target_id": "MISSING_TARGET_ITEM",
                "relation_type": "parent_to_child",
            }
        ],
        "required_slots": [],
    }

    with pytest.raises(ValueError, match="Orphaned evidence relation rejected"):
        EvidenceSet.from_dict(serialized)


def test_phase0_problem_d_deserialization_rejects_conflicting_duplicate_items(sample_p5_evidence):
    """Problem D: from_dict must reject conflicting items sharing the same evidence_id."""
    item1 = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)
    item2_conflicting = EvidenceItem(
        evidence_id=item1.evidence_id,
        doc_id=item1.doc_id,
        page_id=item1.page_id,
        page_number=item1.page_number,
        text="Conflicting modified text for the same evidence_id",
    )

    serialized = {
        "query_id": "Q-DUP-CONFLICT",
        "evidence_items": [item1.to_dict(), item2_conflicting.to_dict()],
        "evidence_relations": [],
        "required_slots": [],
    }

    with pytest.raises(ValueError, match="Conflicting evidence items"):
        EvidenceSet.from_dict(serialized)


def test_phase0_direct_construction_rejects_conflicting_duplicate_items(sample_p5_evidence):
    """Direct construction with conflicting evidence items sharing the same ID must raise ValueError."""
    item1 = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)
    item2_conflicting = EvidenceItem(
        evidence_id=item1.evidence_id,
        doc_id=item1.doc_id,
        page_id=item1.page_id,
        page_number=item1.page_number,
        text="Direct construction conflicting text",
    )

    with pytest.raises(ValueError, match="Conflicting evidence items"):
        EvidenceSet(
            query_id="Q-DIRECT-CONFLICT",
            evidence_items=[item1, item2_conflicting],
        )


def test_phase0_direct_construction_rejects_orphaned_relations(sample_p5_evidence):
    """Direct construction with orphaned relations must raise ValueError."""
    item = P5EvidenceAdapter.from_p5_evidence(sample_p5_evidence)
    orphaned_rel = EvidenceRelation(
        source_id=item.evidence_id,
        target_id="NONEXISTENT_ITEM_ID",
        relation_type="parent_to_child",
    )

    with pytest.raises(ValueError, match="Orphaned evidence relation rejected"):
        EvidenceSet(
            query_id="Q-DIRECT-ORPHAN",
            evidence_items=[item],
            evidence_relations=[orphaned_rel],
        )


def test_phase0_direct_construction_recomputes_completeness_status():
    """Direct construction passing completeness_status='COMPLETE' blindly must recompute to UNKNOWN."""
    evidence_set = EvidenceSet(
        query_id="Q-DIRECT-BLIND-COMPLETE",
        evidence_items=[],
        required_slots=[],
        completeness_status="COMPLETE",  # Blind claim of completeness
    )

    # Must be recomputed by __post_init__ to UNKNOWN
    assert evidence_set.completeness_status == "UNKNOWN"


def test_phase0_missing_evidence_does_not_imply_contradiction():
    """Missing evidence indicates incomplete coverage, NOT contradiction."""
    slot = InformationSlot(
        slot_id="slot_missing",
        name="design_frequency",
        required=True,
        covered_by_evidence_id=None,
    )
    evidence_set = EvidenceSet(query_id="Q-MISSING-SEMANTICS")
    evidence_set.required_slots = [slot]
    evidence_set.update_slot_coverage()

    assert evidence_set.completeness_status == "INSUFFICIENT"
    assert len(evidence_set.missing_slots) == 1
    # Missing slot must NEVER be treated as CONTRADICTED
    assert evidence_set.missing_slots[0].support_status != "CONTRADICTED"
    assert evidence_set.missing_slots[0].support_status == "UNVERIFIED"


