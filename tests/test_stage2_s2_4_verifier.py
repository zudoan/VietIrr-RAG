"""Comprehensive Test Suite for Stage 2.4 Ontology-Constrained Claim Verification.

Includes:
- P5-KNOWN-01 (Multi-word jurisdiction mismatch: Đồng Nai vs Đồng Tháp).
- P5-KNOWN-02 (Negated legal action: affirmed in evidence, negated in claim).
- 20 Required Adversarial Scenarios from S2.4 Specification.
- Independent shadow mode verification (all 6 P5 vs S2.4 matrix combinations).
"""

from __future__ import annotations

import pytest
from viirr_ontology.domain.classes import SourceValidationRecord, VerificationConstraint
from viirr_ontology.domain.constraint_registry import ConstraintRegistry
from viirr_ontology.domain.ontology_loader import HydraulicOntology
from viirr_ontology.schema.claim import ClaimCondition, ClaimPolarity, TechnicalClaim
from viirr_ontology.schema.evidence import EvidenceItem, EvidenceRelation, EvidenceSet
from viirr_ontology.verifier.models import (
    AnswerVerificationResult,
    ClaimVerificationStatus,
    ReasonCode,
    VerificationResult,
)
from viirr_ontology.verifier.ontology_verifier import OntologyConstraintVerifier


@pytest.fixture
def verifier() -> OntologyConstraintVerifier:
    """Fixture providing initialized OntologyConstraintVerifier."""
    return OntologyConstraintVerifier()


# =============================================================================
# MANDATORY P5 KNOWN FAILURE MODES
# =============================================================================

def test_p5_known_01_multi_word_jurisdiction_mismatch(verifier: OntologyConstraintVerifier):
    """P5-KNOWN-01: Multi-word jurisdiction conflict between Đồng Nai and Đồng Tháp.

    Evidence establishes jurisdiction for 'tỉnh Đồng Nai'.
    Claim asserts authority for 'tỉnh Đồng Tháp'.
    Verifier must detect the incompatibility and return CONTRADICTED.
    """
    evidence = EvidenceSet(
        query_id="Q_JUR_01",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_JUR_DONG_NAI",
                doc_id="DOC_GOV_DONG_NAI",
                page_id="P1",
                page_number=1,
                text="Ủy ban nhân dân tỉnh Đồng Nai có trách nhiệm phê duyệt phương án ứng phó thiên tai trên địa bàn tỉnh.",
                document_number="UBND-DN-2023",
            )
        ],
    )

    claim = TechnicalClaim(
        claim_id="C_JUR_DONG_THAP",
        claim_text="Ủy ban nhân dân tỉnh Đồng Tháp có trách nhiệm phê duyệt phương án ứng phó thiên tai",
        subject="Ủy ban nhân dân tỉnh Đồng Tháp",
        action="phê duyệt phương án ứng phó thiên tai",
        jurisdiction="tỉnh Đồng Tháp",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E_JUR_DONG_NAI"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.CONTRADICTED
    assert ReasonCode.JURISDICTION_MISMATCH.value in res.reason_codes
    assert "E_JUR_DONG_NAI" in res.conflicting_evidence_ids


def test_p5_known_02_negated_legal_action(verifier: OntologyConstraintVerifier):
    """P5-KNOWN-02: Negated legal action.

    Evidence affirms authority: 'Bộ Tài nguyên và Môi trường quyết định vận hành giảm lũ...'.
    Claim states authority is not permitted: 'Bộ Tài nguyên và Môi trường không có thẩm quyền quyết định...'.
    Verifier must detect polarity contradiction and return CONTRADICTED.
    """
    evidence = EvidenceSet(
        query_id="Q_LEG_02",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_LEG_AFFIRMED",
                doc_id="IRR_CP_2019_ee0bca33",
                page_id="P10",
                page_number=10,
                text="Bộ Tài nguyên và Môi trường quyết định phương án vận hành các hồ chứa để giảm lũ cho hạ du.",
                document_number="740/QĐ-TTg",
            )
        ],
    )

    claim = TechnicalClaim(
        claim_id="C_LEG_NEGATED",
        claim_text="Bộ Tài nguyên và Môi trường không có thẩm quyền quyết định phương án vận hành các hồ chứa để giảm lũ",
        subject="Bộ Tài nguyên và Môi trường",
        action="quyết định phương án vận hành",
        polarity=ClaimPolarity.NEGATED,
        evidence_ids=["E_LEG_AFFIRMED"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.CONTRADICTED
    assert ReasonCode.POLARITY_CONTRADICTED.value in res.reason_codes
    assert "E_LEG_AFFIRMED" in res.conflicting_evidence_ids


# =============================================================================
# 20 REQUIRED ADVERSARIAL TESTS (Section 12)
# =============================================================================

def test_adv_01_correct_reservoir_and_water_level(verifier: OntologyConstraintVerifier):
    """Scenario 1: Correct reservoir and water-level parameter (Hòa Bình, MNDBT 117.0 m -> SUPPORTED)."""
    evidence = EvidenceSet(
        query_id="Q_ADV_01",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_HB_117",
                doc_id="IRR_CP_2019_ee0bca33",
                page_id="P4",
                page_number=4,
                text="Hồ Hòa Bình có mực nước dâng bình thường là 117,0 m theo Quy trình 740.",
                document_number="740/QĐ-TTg",
            )
        ],
    )

    claim = TechnicalClaim(
        claim_id="C_HB_MNDBT",
        claim_text="Mực nước dâng bình thường của hồ Hòa Bình là 117.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117.0",
        unit="m",
        evidence_ids=["E_HB_117"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.SUPPORTED
    assert "E_HB_117" in res.supporting_evidence_ids


def test_adv_02_wrong_reservoir_same_numeric_value(verifier: OntologyConstraintVerifier):
    """Scenario 2: Wrong reservoir, same numeric value (Claim says Sơn La, evidence mentions Hòa Bình)."""
    evidence = EvidenceSet(
        query_id="Q_ADV_02",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_HB_117",
                doc_id="IRR_CP_2019_ee0bca33",
                page_id="P4",
                page_number=4,
                text="Hồ Hòa Bình: mực nước dâng bình thường là 117.0 m.",
            )
        ],
    )

    claim = TechnicalClaim(
        claim_id="C_SL_117",
        claim_text="Mực nước dâng bình thường của hồ Sơn La là 117.0 m",
        subject="Hồ Sơn La",
        parameter="Mực nước dâng bình thường",
        value="117.0",
        unit="m",
        evidence_ids=["E_HB_117"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.CONTRADICTED
    assert ReasonCode.ENTITY_MISMATCH.value in res.reason_codes


def test_adv_03_normal_pool_level_confused_with_dead_water_level(verifier: OntologyConstraintVerifier):
    """Scenario 3: Normal pool level (MNDBT) confused with dead water level (MNC)."""
    evidence = EvidenceSet(
        query_id="Q_ADV_03",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_HB_MNC_80",
                doc_id="IRR_CP_2019_ee0bca33",
                page_id="P4",
                page_number=4,
                text="Hồ Hòa Bình có mực nước chết là 80,0 m.",
            )
        ],
    )

    # Claim says 80.0 m is the Normal Water Level (MNDBT)
    claim = TechnicalClaim(
        claim_id="C_HB_MNDBT_CONFUSED",
        claim_text="Mực nước dâng bình thường của hồ Hòa Bình là 80.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="80.0",
        unit="m",
        evidence_ids=["E_HB_MNC_80"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.CONTRADICTED
    assert ReasonCode.PARAMETER_MISMATCH.value in res.reason_codes


def test_adv_04_correct_number_wrong_unit(verifier: OntologyConstraintVerifier):
    """Scenario 4: Correct number but wrong unit (117 m3/s instead of 117 m)."""
    evidence = EvidenceSet(
        query_id="Q_ADV_04",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_HB_117_M",
                doc_id="IRR_CP_2019_ee0bca33",
                page_id="P4",
                page_number=4,
                text="Hồ Hòa Bình có mực nước dâng bình thường là 117.0 m.",
            )
        ],
    )

    claim = TechnicalClaim(
        claim_id="C_HB_WRONG_UNIT",
        claim_text="Mực nước dâng bình thường của hồ Hòa Bình là 117.0 m3/s",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117.0",
        unit="m3/s",
        evidence_ids=["E_HB_117_M"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status in (ClaimVerificationStatus.CONTRADICTED, ClaimVerificationStatus.INSUFFICIENT)
    assert ReasonCode.UNIT_INCOMPATIBLE.value in res.reason_codes


def test_adv_05_correct_unit_wrong_physical_parameter(verifier: OntologyConstraintVerifier):
    """Scenario 5: Correct unit (m3/s) but applied to water level concept."""
    evidence = EvidenceSet(
        query_id="Q_ADV_05",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_HB_Q",
                doc_id="IRR_CP_2019_ee0bca33",
                page_id="P4",
                page_number=4,
                text="Lưu lượng xả lớn nhất của hồ Hòa Bình là 3500 m3/s.",
            )
        ],
    )

    # Claim claims that water level is 3500 m3/s
    claim = TechnicalClaim(
        claim_id="C_PARAM_DIM_WRONG",
        claim_text="Mực nước dâng bình thường của hồ Hòa Bình là 3500 m3/s",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="3500",
        unit="m3/s",
        evidence_ids=["E_HB_Q"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status in (ClaimVerificationStatus.CONTRADICTED, ClaimVerificationStatus.INSUFFICIENT)
    assert ReasonCode.UNIT_INCOMPATIBLE.value in res.reason_codes


def test_adv_06_missing_design_condition(verifier: OntologyConstraintVerifier):
    """Scenario 6: Missing design condition (Claim asserts specific p=0.01% but evidence omits it)."""
    evidence = EvidenceSet(
        query_id="Q_ADV_06",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_GENERAL_WATER_LEVEL",
                doc_id="IRR_CP_2019_ee0bca33",
                page_id="P5",
                page_number=5,
                text="Hồ Hòa Bình có mực nước cao nhất là 120.0 m.",
            )
        ],
    )

    claim = TechnicalClaim(
        claim_id="C_COND_MISSING",
        claim_text="Mực nước cao nhất với tần suất lũ thiết kế p=0.01% là 120.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước cao nhất",
        value="120.0",
        unit="m",
        conditions=[ClaimCondition(operator="EQ", value="0.01", unit="%", raw_text="p=0.01%")],
        evidence_ids=["E_GENERAL_WATER_LEVEL"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.CONDITION_MISSING.value in res.reason_codes
    assert "conditions" in res.missing_evidence_slots


def test_adv_07_different_design_flood_frequency(verifier: OntologyConstraintVerifier):
    """Different design frequency is out of scope, not contradictory evidence."""
    evidence = EvidenceSet(
        query_id="Q_ADV_07",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_FREQ_01",
                doc_id="IRR_CP_2019_ee0bca33",
                page_id="P5",
                page_number=5,
                text="Mực nước lũ thiết kế của hồ Hòa Bình ứng với tần suất p = 0.1 % là 120.0 m.",
            )
        ],
    )

    claim = TechnicalClaim(
        claim_id="C_FREQ_CONFLICT",
        claim_text="Mực nước lũ kiểm tra ứng với p=0.01% là 120.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước lũ",
        value="120.0",
        unit="m",
        conditions=[ClaimCondition(operator="EQ", value="0.01", unit="%", raw_text="p=0.01%")],
        evidence_ids=["E_FREQ_01"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.CONDITION_CONTRADICTED.value in res.reason_codes


def test_adv_08_table_row_separated_from_header(verifier: OntologyConstraintVerifier):
    """Scenario 8: Table row separated from header without relation -> INSUFFICIENT."""
    # Row only contains '117.0', header is missing
    evidence = EvidenceSet(
        query_id="Q_ADV_08",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_ROW_ONLY",
                doc_id="DOC_TABLE",
                page_id="P1",
                page_number=1,
                content_type="table",
                text="Hồ Hòa Bình | 117.0 | 80.0",
            )
        ],
    )

    claim = TechnicalClaim(
        claim_id="C_TABLE_UNLINKED",
        claim_text="Mực nước dâng bình thường của hồ Hòa Bình là 117.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117.0",
        unit="m",
        evidence_ids=["E_ROW_ONLY"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    # Parameter 'Mực nước dâng bình thường' is not present in row text
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert "parameter" in res.missing_evidence_slots


def test_adv_09_missing_table_note(verifier: OntologyConstraintVerifier):
    """Scenario 9: Missing table note specifying seasonal limitation -> INSUFFICIENT."""
    evidence = EvidenceSet(
        query_id="Q_ADV_09",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_TABLE_ROW_NO_NOTE",
                doc_id="DOC_TABLE",
                page_id="P1",
                page_number=1,
                text="Hồ Sơn La: Mực nước dâng bình thường 215.0 m.",
            )
        ],
    )

    # Claim states it applies exclusively in early flood season ("thời kỳ lũ sớm")
    claim = TechnicalClaim(
        claim_id="C_NOTE_MISSING",
        claim_text="Mực nước đón lũ hồ Sơn La thời kỳ lũ sớm là 215.0 m",
        subject="Hồ Sơn La",
        parameter="Mực nước",
        value="215.0",
        unit="m",
        conditions=[ClaimCondition(operator="EQ", value="lũ sớm", raw_text="thời kỳ lũ sớm")],
        evidence_ids=["E_TABLE_ROW_NO_NOTE"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.CONDITION_MISSING.value in res.reason_codes


def test_adv_10_multi_region_complementary_synthesis(verifier: OntologyConstraintVerifier):
    """Scenario 10: Multi-region evidence that collectively supports one claim -> SUPPORTED."""
    # Header item provides parameter name and unit, row item provides structure and value
    evidence = EvidenceSet(
        query_id="Q_ADV_10",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_HEADER",
                doc_id="DOC_HYDRAULIC_SPECS",
                page_id="P2",
                page_number=2,
                content_type="table",
                text="Bảng thông số: Mực nước dâng bình thường (m)",
            ),
            EvidenceItem(
                evidence_id="E_ROW",
                doc_id="DOC_HYDRAULIC_SPECS",
                page_id="P2",
                page_number=2,
                content_type="table",
                text="Hồ Hòa Bình: 117.0",
            ),
        ],
        evidence_relations=[
            EvidenceRelation(
                source_id="E_ROW",
                target_id="E_HEADER",
                relation_type="table_row_to_header",
                verified=True,
                provenance_source="document_layout_inspection",
            )
        ],
    )

    claim = TechnicalClaim(
        claim_id="C_MULTI_REGION_HB",
        claim_text="Mực nước dâng bình thường của hồ Hòa Bình là 117.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117.0",
        unit="m",
        evidence_ids=["E_ROW", "E_HEADER"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.SUPPORTED
    assert ReasonCode.EVIDENCE_MULTI_REGION_MATCH.value in res.reason_codes
    assert "E_ROW" in res.supporting_evidence_ids
    assert "E_HEADER" in res.supporting_evidence_ids


def test_adv_11_evidence_id_belonging_to_another_document(verifier: OntologyConstraintVerifier):
    """Scenario 11: Claimed evidence ID belongs to another document -> INSUFFICIENT / INVALID_PROVENANCE."""
    evidence = EvidenceSet(
        query_id="Q_ADV_11",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_DOC_B_ITEM",
                doc_id="DOC_B",
                page_id="P1",
                page_number=1,
                text="Hồ Hòa Bình có mực nước dâng bình thường 117.0 m.",
            )
        ],
    )

    # Claim claims to be grounded in DOC_A
    claim = TechnicalClaim(
        claim_id="C_CROSS_DOC_MISMATCH",
        claim_text="Mực nước dâng bình thường của hồ Hòa Bình là 117.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117.0",
        unit="m",
        document_scope="DOC_A_SPECIAL_SPECS",
        evidence_ids=["E_DOC_B_ITEM"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.DOCUMENT_MISMATCH.value in res.reason_codes


def test_adv_12_conflicting_document_versions(verifier: OntologyConstraintVerifier):
    """Scenario 12: Conflicting document versions (QĐ 740 vs QĐ 922 amendments)."""
    # QĐ 740 had 117.0, an amending document specifies a modified threshold
    evidence = EvidenceSet(
        query_id="Q_ADV_12",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_QD_922_AMEND",
                doc_id="IRR_CP_2025_2d3e4a1e",
                page_id="P2",
                page_number=2,
                text="Quyết định 922 sửa đổi Điều 5: Hồ Hòa Bình mực nước đón lũ là 105.0 m.",
                document_number="922/QĐ-TTg",
            )
        ],
    )

    claim = TechnicalClaim(
        claim_id="C_DOC_CONFLICT",
        claim_text="Mực nước đón lũ của hồ Hòa Bình là 101.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước đón lũ",
        value="101.0",
        unit="m",
        document_scope="922/QĐ-TTg",
        evidence_ids=["E_QD_922_AMEND"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.CONTRADICTED
    assert ReasonCode.VALUE_CONTRADICTED.value in res.reason_codes


def test_adv_13_amended_versus_superseded_documents(verifier: OntologyConstraintVerifier):
    """Scenario 13: Amended vs superseded documents.

    QĐ 922 amends specific provisions of QĐ 740, but does not supersede or invalidate QĐ 740 entirely.
    """
    evidence = EvidenceSet(
        query_id="Q_ADV_13",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_QD_740_UNTOUCHED",
                doc_id="IRR_CP_2019_ee0bca33",
                page_id="P4",
                page_number=4,
                text="Hồ Hòa Bình mực nước dâng bình thường là 117.0 m.",
                document_number="740/QĐ-TTg",
            )
        ],
    )

    # Claim asserts QĐ 740's MNDBT remains valid under current regulation
    claim = TechnicalClaim(
        claim_id="C_AMENDED_NOT_SUPERSEDED",
        claim_text="Mực nước dâng bình thường hồ Hòa Bình theo QĐ 740 là 117.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117.0",
        unit="m",
        document_scope="740/QĐ-TTg",
        evidence_ids=["E_QD_740_UNTOUCHED"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.SUPPORTED


def test_adv_14_unverified_factual_constraint_does_not_decide_support(verifier: OntologyConstraintVerifier):
    """Scenario 14: Unverified factual constraint must be ignored and not decide support."""
    custom_registry = ConstraintRegistry()
    # Register an unverified draft constraint
    unverified_rule = VerificationConstraint(
        constraint_id="CONST_DRAFT_FABRICATED_01",
        name="Draft Fabricated Rule",
        description="A fabricated draft constraint without validated source record",
        constraint_type="SOURCE_VERIFIED_FACT",
        applicable_class="WaterLevel",
        validation_status="DRAFT_UNVERIFIED",
    )
    custom_registry.register(unverified_rule)

    custom_verifier = OntologyConstraintVerifier(constraint_registry=custom_registry)

    # Claim matching draft rule but with no real evidence
    claim = TechnicalClaim(
        claim_id="C_UNVERIFIED_RULE_TEST",
        claim_text="Mực nước hồ X là 100 m",
        subject="Hồ X",
        parameter="WaterLevel",
        value="100.0",
        unit="m",
    )

    res = custom_verifier.verify_single_claim(claim, EvidenceSet(query_id="Q_EMPTY", evidence_items=[]))
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert "CONST_DRAFT_FABRICATED_01" in res.missing_constraints
    assert ReasonCode.CONSTRAINT_UNVERIFIED_IGNORED.value in res.reason_codes


def test_adv_15_unknown_jurisdiction(verifier: OntologyConstraintVerifier):
    """Scenario 15: Unknown / unresolved jurisdiction -> INSUFFICIENT."""
    evidence = EvidenceSet(
        query_id="Q_ADV_15",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_NO_JUR",
                doc_id="DOC_GENERIC",
                page_id="P1",
                page_number=1,
                text="Ủy ban nhân dân có trách nhiệm chỉ đạo công tác cứu hộ cứu nạn.",
            )
        ],
    )

    claim = TechnicalClaim(
        claim_id="C_UNKNOWN_JUR",
        claim_text="Ủy ban nhân dân tỉnh X có trách nhiệm chỉ đạo công tác cứu hộ",
        subject="Ủy ban nhân dân",
        jurisdiction="tỉnh X",
        action="chỉ đạo công tác cứu hộ",
        evidence_ids=["E_NO_JUR"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.JURISDICTION_UNKNOWN.value in res.reason_codes


def test_adv_16_multi_word_jurisdiction_mismatch(verifier: OntologyConstraintVerifier):
    """Scenario 16: Multi-word jurisdiction mismatch (Đồng Nai vs Đồng Tháp)."""
    evidence = EvidenceSet(
        query_id="Q_ADV_16",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_DN",
                doc_id="DOC_DN",
                page_id="P1",
                page_number=1,
                text="Chủ tịch UBND tỉnh Đồng Nai ban hành lệnh vận hành hồ Trị An.",
            )
        ],
    )

    claim = TechnicalClaim(
        claim_id="C_DT_MISMATCH",
        claim_text="Chủ tịch UBND tỉnh Đồng Tháp ban hành lệnh vận hành hồ Trị An",
        subject="Chủ tịch UBND",
        jurisdiction="tỉnh Đồng Tháp",
        action="ban hành lệnh vận hành",
        evidence_ids=["E_DN"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.CONTRADICTED
    assert ReasonCode.JURISDICTION_MISMATCH.value in res.reason_codes


def test_adv_17_legal_negation(verifier: OntologyConstraintVerifier):
    """Scenario 17: Legal negation mismatch."""
    evidence = EvidenceSet(
        query_id="Q_ADV_17",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_AFFIRMED",
                doc_id="DOC_DEC",
                page_id="P1",
                page_number=1,
                text="Trưởng Ban Chỉ huy Phòng chống thiên tai tỉnh được phép quyết định lệnh đóng mở cống.",
            )
        ],
    )

    claim = TechnicalClaim(
        claim_id="C_NEGATED",
        claim_text="Trưởng Ban Chỉ huy Phòng chống thiên tai tỉnh không được phép quyết định lệnh đóng mở cống",
        subject="Trưởng Ban Chỉ huy",
        action="quyết định lệnh đóng mở cống",
        polarity=ClaimPolarity.NEGATED,
        evidence_ids=["E_AFFIRMED"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.CONTRADICTED
    assert ReasonCode.POLARITY_CONTRADICTED.value in res.reason_codes


def test_adv_18_ambiguous_parameter_phrase(verifier: OntologyConstraintVerifier):
    """Scenario 18: Ambiguous multi-parameter phrase -> INSUFFICIENT."""
    evidence = EvidenceSet(
        query_id="Q_ADV_18",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_HB_117",
                doc_id="DOC_HB",
                page_id="P1",
                page_number=1,
                text="Hồ Hòa Bình: mực nước dâng bình thường 117.0 m.",
            )
        ],
    )

    # Claim uses an ambiguous compound parameter: "mực nước dâng bình thường và mực nước chết"
    claim = TechnicalClaim(
        claim_id="C_AMBIGUOUS_PARAM",
        claim_text="Mực nước dâng bình thường và mực nước chết là 117.0 m",
        subject="Hồ Hòa Bình",
        parameter="mực nước dâng bình thường và mực nước chết",
        value="117.0",
        unit="m",
        evidence_ids=["E_HB_117"],
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.PARAMETER_AMBIGUOUS.value in res.reason_codes


def test_adv_19_answer_aggregation_two_claims_different_status(verifier: OntologyConstraintVerifier):
    """Scenario 19: Multi-claim answer aggregation: 1 supported + 1 contradicted -> CONTRADICTED."""
    evidence = EvidenceSet(
        query_id="Q_ADV_19",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_HB",
                doc_id="DOC_HB",
                page_id="P1",
                page_number=1,
                text="Hồ Hòa Bình: mực nước dâng bình thường là 117.0 m.",
            ),
            EvidenceItem(
                evidence_id="E_SL",
                doc_id="DOC_SL",
                page_id="P2",
                page_number=2,
                text="Hồ Sơn La: mực nước dâng bình thường là 215.0 m.",
            ),
        ],
    )

    claim1_valid = TechnicalClaim(
        claim_id="C1_VALID",
        claim_text="MNDBT Hòa Bình là 117.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117.0",
        unit="m",
        evidence_ids=["E_HB"],
    )

    claim2_invalid = TechnicalClaim(
        claim_id="C2_CONTRADICTED",
        claim_text="MNDBT Sơn La là 100.0 m",  # Contradicts 215.0 m
        subject="Hồ Sơn La",
        parameter="Mực nước dâng bình thường",
        value="100.0",
        unit="m",
        evidence_ids=["E_SL"],
    )

    answer_res = verifier.verify_answer([claim1_valid, claim2_invalid], evidence)
    # Aggregate status must NEVER hide the contradicted claim!
    assert answer_res.aggregate_status == ClaimVerificationStatus.CONTRADICTED
    assert answer_res.supported_count == 1
    assert answer_res.contradicted_count == 1


def test_adv_20_malformed_incomplete_claim(verifier: OntologyConstraintVerifier):
    """Scenario 20: Malformed or incomplete claim extraction -> INSUFFICIENT."""
    evidence = EvidenceSet(
        query_id="Q_ADV_20",
        evidence_items=[
            EvidenceItem(
                evidence_id="E_VALID",
                doc_id="DOC_1",
                page_id="P1",
                page_number=1,
                text="Hồ Hòa Bình mực nước 117.0 m.",
            )
        ],
    )

    # Malformed claim with empty text, subject, parameter
    claim = TechnicalClaim(
        claim_id="C_MALFORMED",
        claim_text="",
        subject="",
        parameter="",
    )

    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.INCOMPLETE_CLAIM_EXTRACTION.value in res.reason_codes


# =============================================================================
# INDEPENDENT SHADOW MODE & P5 MATRIX EVALUATION (Section 9)
# =============================================================================

@pytest.mark.parametrize(
    "p5_verdict, s2_4_expected_status",
    [
        ("PASS", ClaimVerificationStatus.SUPPORTED),
        ("PASS", ClaimVerificationStatus.CONTRADICTED),
        ("PASS", ClaimVerificationStatus.INSUFFICIENT),
        ("ABSTAIN", ClaimVerificationStatus.SUPPORTED),
        ("ABSTAIN", ClaimVerificationStatus.CONTRADICTED),
        ("ABSTAIN", ClaimVerificationStatus.INSUFFICIENT),
    ],
)
def test_p5_s2_4_all_six_matrix_combinations(
    verifier: OntologyConstraintVerifier, p5_verdict: str, s2_4_expected_status: ClaimVerificationStatus
):
    """Verify that S2.4 can run completely independently of P5 across all 6 status combinations."""
    p5_output = {
        "verdict": p5_verdict,
        "reason": f"Synthetic baseline output with verdict {p5_verdict}",
        "citations": ["DOC_TEST:1:E1"],
    }

    if s2_4_expected_status == ClaimVerificationStatus.SUPPORTED:
        evidence = EvidenceSet(
            query_id="Q_SHADOW",
            evidence_items=[EvidenceItem(evidence_id="E1", doc_id="DOC_TEST", page_id="P1", page_number=1, text="Hồ Hòa Bình có mực nước 117.0 m.")],
        )
        claim = TechnicalClaim(
            claim_id="C_SHADOW",
            claim_text="Mực nước hồ Hòa Bình 117.0 m",
            subject="Hồ Hòa Bình",
            parameter="Mực nước",
            value="117.0",
            unit="m",
            evidence_ids=["E1"],
        )
    elif s2_4_expected_status == ClaimVerificationStatus.CONTRADICTED:
        evidence = EvidenceSet(
            query_id="Q_SHADOW",
            evidence_items=[EvidenceItem(evidence_id="E1", doc_id="DOC_TEST", page_id="P1", page_number=1, text="Hồ Hòa Bình có mực nước là 117.0 m.")],
        )
        claim = TechnicalClaim(
            claim_id="C_SHADOW",
            claim_text="Mực nước hồ Hòa Bình 80.0 m",  # Contradicts 117.0 m
            subject="Hồ Hòa Bình",
            parameter="Mực nước",
            value="80.0",
            unit="m",
            evidence_ids=["E1"],
        )
    else:  # INSUFFICIENT
        evidence = EvidenceSet(query_id="Q_SHADOW", evidence_items=[])
        claim = TechnicalClaim(
            claim_id="C_SHADOW",
            claim_text="Mực nước hồ Hòa Bình 117.0 m",
            subject="Hồ Hòa Bình",
            parameter="Mực nước",
            value="117.0",
            unit="m",
        )

    ans_result = verifier.verify_answer([claim], evidence, p5_output=p5_output)
    assert ans_result.aggregate_status == s2_4_expected_status
    assert ans_result.p5_comparison is not None
    assert ans_result.p5_comparison["p5_verdict"] == p5_verdict
