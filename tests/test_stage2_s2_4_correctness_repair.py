"""Adversarial integration coverage for the S2.4 correctness repair."""

from __future__ import annotations

import pytest
import json
import re

from viirr_ontology.domain.classes import SourceValidationRecord, VerificationConstraint
from viirr_ontology.domain.constraint_registry import ConstraintRegistry
from viirr_ontology.evaluation.offline_runner import OfflineEvaluationRunner
from viirr_ontology.schema.claim import ClaimCondition, ClaimPolarity, EvidenceCitation, TechnicalClaim
from viirr_ontology.schema.evidence import EvidenceItem, EvidenceRelation, EvidenceSet
from viirr_ontology.verifier.models import ClaimVerificationStatus, ReasonCode
from viirr_ontology.verifier.ontology_verifier import OntologyConstraintVerifier


def _item(evidence_id: str, text: str, doc_id: str = "DOC", page: int = 1) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        doc_id=doc_id,
        page_id=f"P{page}",
        page_number=page,
        text=text,
    )


def _claim(*evidence_ids: str, value: str = "117") -> TechnicalClaim:
    return TechnicalClaim(
        claim_id="C_HB_MNDBT",
        claim_text=f"Mực nước dâng bình thường hồ Hòa Bình là {value} m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value=value,
        unit="m",
        evidence_ids=list(evidence_ids),
    )


@pytest.fixture
def verifier() -> OntologyConstraintVerifier:
    return OntologyConstraintVerifier()


def test_real_evidence_set_schema_is_used_without_compatibility_aliases(verifier):
    evidence = EvidenceSet(
        query_id="Q_SCHEMA",
        evidence_items=[_item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m.")],
    )
    assert not hasattr(evidence, "items")
    assert not hasattr(evidence, "relations")
    assert verifier.verify_single_claim(_claim("E1"), evidence).status == ClaimVerificationStatus.SUPPORTED


def test_support_does_not_hide_conflicting_relevant_evidence(verifier):
    evidence = EvidenceSet(
        query_id="Q_CONFLICT",
        evidence_items=[
            _item("E_SUPPORT", "Hồ Hòa Bình có mực nước dâng bình thường 117 m."),
            _item("E_CONFLICT", "Hồ Hòa Bình có mực nước dâng bình thường 118 m."),
        ],
    )
    result = verifier.verify_single_claim(_claim("E_SUPPORT", "E_CONFLICT"), evidence)
    assert result.status == ClaimVerificationStatus.CONTRADICTED
    assert result.supporting_evidence_ids == ["E_SUPPORT"]
    assert result.conflicting_evidence_ids == ["E_CONFLICT"]


def test_number_is_bound_to_exact_parameter(verifier):
    evidence = EvidenceSet(
        query_id="Q_BINDING",
        evidence_items=[
            _item(
                "E1",
                "Hồ Hòa Bình có mực nước dâng bình thường 80 m và mực nước chết 117 m.",
            )
        ],
    )
    result = verifier.verify_single_claim(_claim("E1"), evidence)
    assert result.status == ClaimVerificationStatus.CONTRADICTED
    assert ReasonCode.VALUE_CONTRADICTED.value in result.reason_codes


def test_unrelated_documents_cannot_be_synthesized(verifier):
    evidence = EvidenceSet(
        query_id="Q_MULTI_DOC",
        evidence_items=[
            _item("E_SUBJECT", "Hồ Hòa Bình.", doc_id="DOC_A"),
            _item("E_VALUE", "Mực nước dâng bình thường là 117 m.", doc_id="DOC_B"),
        ],
    )
    result = verifier.verify_single_claim(_claim("E_SUBJECT", "E_VALUE"), evidence)
    assert result.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.EVIDENCE_RELATION_MISSING.value in result.reason_codes


def test_unlinked_regions_in_one_document_cannot_be_synthesized(verifier):
    evidence = EvidenceSet(
        query_id="Q_UNLINKED",
        evidence_items=[
            _item("E_SUBJECT", "Hồ Hòa Bình."),
            _item("E_VALUE", "Mực nước dâng bình thường là 117 m."),
        ],
    )
    result = verifier.verify_single_claim(_claim("E_SUBJECT", "E_VALUE"), evidence)
    assert result.status == ClaimVerificationStatus.INSUFFICIENT
    assert "verified_evidence_relation" in result.missing_evidence_slots


def test_verified_table_relation_allows_multi_region_support(verifier):
    evidence = EvidenceSet(
        query_id="Q_LINKED",
        evidence_items=[
            _item("E_ROW", "Hồ Hòa Bình: 117"),
            _item("E_HEADER", "Mực nước dâng bình thường (m)"),
        ],
        evidence_relations=[
            EvidenceRelation(
                source_id="E_ROW",
                target_id="E_HEADER",
                relation_type="table_row_to_header",
                verified=True,
                provenance_source="manual_layout_audit",
            )
        ],
    )
    result = verifier.verify_single_claim(_claim("E_ROW", "E_HEADER"), evidence)
    assert result.status == ClaimVerificationStatus.SUPPORTED
    assert set(result.supporting_evidence_ids) == {"E_ROW", "E_HEADER"}


def test_one_missing_explicit_id_invalidates_mixed_citation_list(verifier):
    evidence = EvidenceSet(
        query_id="Q_MIXED_CITATION",
        evidence_items=[_item("E_VALID", "Hồ Hòa Bình có mực nước dâng bình thường 117 m.")],
    )
    result = verifier.verify_single_claim(_claim("E_VALID", "E_MISSING"), evidence)
    assert result.status == ClaimVerificationStatus.INSUFFICIENT
    assert result.supporting_evidence_ids == ["E_VALID"]
    assert ReasonCode.CITATION_IDENTITY_MISMATCH.value in result.reason_codes


@pytest.mark.parametrize(
    "citation",
    [
        EvidenceCitation(doc_id="WRONG_DOC", page_number=4, evidence_id="E1"),
        EvidenceCitation(doc_id="DOC", page_number=99, evidence_id="E1"),
        EvidenceCitation(doc_id="DOC", page_number=4, evidence_id="WRONG_EVIDENCE"),
    ],
)
def test_full_citation_identity_rejects_wrong_doc_page_or_id(verifier, citation):
    evidence = EvidenceSet(
        query_id="Q_CITATION_KEY",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m.", page=4)
        ],
    )
    claim = _claim()
    claim.evidence_citations = [citation]
    result = verifier.verify_single_claim(claim, evidence)
    assert result.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.CITATION_IDENTITY_MISMATCH.value in result.reason_codes


def test_different_application_condition_is_not_a_contradiction(verifier):
    claim = _claim("E_MATCH", "E_OTHER")
    claim.conditions = [ClaimCondition("EQ", "0.01", "%", "p=0.01%")]
    evidence = EvidenceSet(
        query_id="Q_CONDITION_SCOPE",
        evidence_items=[
            _item("E_MATCH", "Hồ Hòa Bình: mực nước dâng bình thường p=0.01% là 117 m."),
            _item("E_OTHER", "Hồ Hòa Bình: mực nước dâng bình thường p=0.1% là 118 m."),
        ],
    )
    result = verifier.verify_single_claim(claim, evidence)
    assert result.status == ClaimVerificationStatus.SUPPORTED
    assert result.conflicting_evidence_ids == []


def test_unqualified_claim_over_different_conditions_is_insufficient(verifier):
    evidence = EvidenceSet(
        query_id="Q_UNQUALIFIED_CONDITIONS",
        evidence_items=[
            _item("E_P001", "Hồ Hòa Bình: mực nước dâng bình thường p=0.01% là 117 m."),
            _item("E_P01", "Hồ Hòa Bình: mực nước dâng bình thường p=0.1% là 118 m."),
        ],
    )
    result = verifier.verify_single_claim(_claim("E_P001", "E_P01"), evidence)
    assert result.status == ClaimVerificationStatus.INSUFFICIENT
    assert result.conflicting_evidence_ids == []
    assert "claim_conditions" in result.missing_evidence_slots


def test_multiple_document_versions_require_explicit_scope(verifier):
    old = _item("E_OLD", "Hồ Hòa Bình có mực nước dâng bình thường 117 m.", doc_id="DOC_740")
    new = _item("E_NEW", "Hồ Hòa Bình có mực nước dâng bình thường 118 m.", doc_id="DOC_922")
    old = EvidenceItem(**{**old.to_dict(), "document_number": "740/QĐ-TTg"})
    new = EvidenceItem(**{**new.to_dict(), "document_number": "922/QĐ-TTg"})
    evidence = EvidenceSet(query_id="Q_VERSION", evidence_items=[old, new])
    result = verifier.verify_single_claim(_claim("E_OLD", "E_NEW"), evidence)
    assert result.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.DOCUMENT_VERSION_CONFLICT.value in result.reason_codes
    assert "document_scope" in result.missing_evidence_slots


def test_unverified_metadata_only_source_constraint_is_inactive():
    constraint = VerificationConstraint(
        constraint_id="CONST-FAKE-VERIFIED-LABEL",
        name="Metadata-only fact",
        description="Must not activate without a trusted corpus source record",
        constraint_type="SOURCE_VERIFIED_FACT",
        applicable_class="Mực nước",
        document_id="DOC_NOT_IN_CORPUS",
        source_reference="Điều 1",
        validation_status="VERIFIED_SOURCE",
        applicable_article="Điều 1",
        validation_record=SourceValidationRecord(
            source_document_id="DOC_NOT_IN_CORPUS",
            citation_key="DOC_NOT_IN_CORPUS:P0001:E1",
            source_content_hash="0" * 64,
            verification_method="EXPERT_CONFIRMED",
            verification_outcome="VALID",
        ),
    )
    registry = ConstraintRegistry(constraints=[constraint])
    assert registry.get_active_constraints() == []
    log = registry.get_activation_log()
    assert log[0]["status"] == "INACTIVE_UNVERIFIED"


def test_ambiguous_missing_unit_is_insufficient(verifier):
    evidence = EvidenceSet(
        query_id="Q_UNIT_MISSING",
        evidence_items=[_item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117.")],
    )
    result = verifier.verify_single_claim(_claim("E1"), evidence)
    assert result.status == ClaimVerificationStatus.INSUFFICIENT
    assert "unit" in result.missing_evidence_slots


def test_dong_nai_vs_dong_thap_jurisdiction_mismatch(verifier):
    evidence = EvidenceSet(
        query_id="Q_DN_DT",
        evidence_items=[
            _item("E_DN", "Ủy ban nhân dân tỉnh Đồng Nai có trách nhiệm phê duyệt phương án phòng chống thiên tai.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_DT",
        claim_text="Ủy ban nhân dân tỉnh Đồng Tháp có trách nhiệm phê duyệt phương án phòng chống thiên tai",
        subject="Ủy ban nhân dân tỉnh Đồng Tháp",
        action="phê duyệt phương án phòng chống thiên tai",
        jurisdiction="tỉnh Đồng Tháp",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E_DN"],
    )
    result = verifier.verify_single_claim(claim, evidence)
    assert result.status == ClaimVerificationStatus.CONTRADICTED
    assert ReasonCode.JURISDICTION_MISMATCH.value in result.reason_codes


def test_legal_negation_contradicts_affirmed_evidence(verifier):
    evidence = EvidenceSet(
        query_id="Q_NEGATION",
        evidence_items=[
            _item("E_AFF", "Bộ Tài nguyên và Môi trường quyết định phương án vận hành các hồ chứa để giảm lũ cho hạ du.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_NEG",
        claim_text="Bộ Tài nguyên và Môi trường không có thẩm quyền quyết định phương án vận hành các hồ chứa",
        subject="Bộ Tài nguyên và Môi trường",
        action="quyết định phương án vận hành",
        polarity=ClaimPolarity.NEGATED,
        evidence_ids=["E_AFF"],
    )
    result = verifier.verify_single_claim(claim, evidence)
    assert result.status == ClaimVerificationStatus.CONTRADICTED
    assert ReasonCode.POLARITY_CONTRADICTED.value in result.reason_codes


def test_missing_technical_condition_in_evidence_is_insufficient(verifier):
    evidence = EvidenceSet(
        query_id="Q_COND_MISSING",
        evidence_items=[_item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m.")],
    )
    claim = _claim("E1")
    claim.conditions = [ClaimCondition("EQ", "0.01", "%", "p=0.01%")]
    result = verifier.verify_single_claim(claim, evidence)
    assert result.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.CONDITION_MISSING.value in result.reason_codes


def test_temporal_scope_mismatch_is_insufficient(verifier):
    evidence = EvidenceSet(
        query_id="Q_TEMPORAL",
        evidence_items=[_item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m.")],
    )
    claim = _claim("E1")
    claim.temporal_scope = "mùa lũ năm 2026"
    result = verifier.verify_single_claim(claim, evidence)
    assert result.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.TEMPORAL_SCOPE_MISMATCH.value in result.reason_codes


def test_multi_claim_mixed_verdicts_aggregates_safely(verifier):
    evidence = EvidenceSet(
        query_id="Q_MULTI_CLAIM",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m."),
            _item("E2", "Hồ Hòa Bình có mực nước chết 80 m."),
        ],
    )
    claim_supported = _claim("E1", value="117")
    claim_contradicted = TechnicalClaim(
        claim_id="C_MNC_WRONG",
        claim_text="Mực nước chết hồ Hòa Bình là 90 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước chết",
        value="90",
        unit="m",
        evidence_ids=["E2"],
    )
    claim_insufficient = TechnicalClaim(
        claim_id="C_INFLOW_MISSING",
        claim_text="Lưu lượng đến hồ Hòa Bình là 1500 m3/s",
        subject="Hồ Hòa Bình",
        parameter="Lưu lượng đến hồ",
        value="1500",
        unit="m3/s",
        evidence_ids=["E1"],
    )

    # 1. Supported + Contradicted -> Contradicted (Supported never hides Contradicted)
    ans_contra = verifier.verify_answer([claim_supported, claim_contradicted], evidence)
    assert ans_contra.aggregate_status == ClaimVerificationStatus.CONTRADICTED
    assert ans_contra.supported_count == 1
    assert ans_contra.contradicted_count == 1

    # 2. Supported + Insufficient -> Insufficient (Supported never hides Insufficient)
    ans_insuff = verifier.verify_answer([claim_supported, claim_insufficient], evidence)
    assert ans_insuff.aggregate_status == ClaimVerificationStatus.INSUFFICIENT
    assert ans_insuff.supported_count == 1
    assert ans_insuff.insufficient_count == 1

    # 3. All Supported -> Supported
    claim_mnc_correct = TechnicalClaim(
        claim_id="C_MNC_CORRECT",
        claim_text="Mực nước chết hồ Hòa Bình là 80 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước chết",
        value="80",
        unit="m",
        evidence_ids=["E2"],
    )
    ans_supp = verifier.verify_answer([claim_supported, claim_mnc_correct], evidence)
    assert ans_supp.aggregate_status == ClaimVerificationStatus.SUPPORTED
    assert ans_supp.supported_count == 2


# =============================================================================
# NEW INDEPENDENT ADVERSARIAL SEMANTIC SAFETY TESTS (SECTION 7)
# =============================================================================

def test_legal_action_absent_from_evidence_is_insufficient(verifier):
    """1. Legal action absent from evidence -> INSUFFICIENT."""
    evidence = EvidenceSet(
        query_id="Q_LEGAL_ACTION_ABSENT",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai tham dự cuộc họp về an toàn đập.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_ACTION_ABSENT",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai được quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.ACTION_MISMATCH.value in res.reason_codes
    assert "action" in res.missing_evidence_slots


def test_negative_legal_claim_with_action_absent_is_insufficient(verifier):
    """2. Negative legal claim with action absent -> INSUFFICIENT."""
    evidence = EvidenceSet(
        query_id="Q_LEGAL_NEG_ACTION_ABSENT",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai tham dự cuộc họp về an toàn đập.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_NEG_ACTION_ABSENT",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai không được quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.NEGATED,
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.ACTION_MISMATCH.value in res.reason_codes
    assert "action" in res.missing_evidence_slots


def test_legal_claim_with_unknown_polarity_is_insufficient(verifier):
    """3. Legal claim with UNKNOWN polarity -> INSUFFICIENT when polarity is required."""
    evidence = EvidenceSet(
        query_id="Q_LEGAL_POLARITY_UNKNOWN",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai quyết định xả lũ trong tình huống khẩn cấp.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_UNKNOWN_POLARITY",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.UNKNOWN,
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.POLARITY_UNKNOWN.value in res.reason_codes
    assert "polarity" in res.missing_evidence_slots


def test_affirmative_legal_claim_contradicted_by_matching_actor_prohibition(verifier):
    """4. Affirmative legal claim contradicted by matching-actor explicit prohibition."""
    evidence = EvidenceSet(
        query_id="Q_MATCHING_ACTOR_PROHIBITION",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai không được quyết định xả lũ khi chưa có lệnh của Ban Chỉ đạo.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_AFFIRMED_CONTRADICTED",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai được quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.CONTRADICTED
    assert ReasonCode.POLARITY_CONTRADICTED.value in res.reason_codes
    assert "E1" in res.conflicting_evidence_ids


def test_unrelated_actor_prohibition_does_not_contradict_claim_actor(verifier):
    """5. Unrelated actor's prohibition must not contradict the claim actor."""
    evidence = EvidenceSet(
        query_id="Q_UNRELATED_ACTOR_PROHIBITION",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai phát biểu tại cuộc họp; cơ quan khác không được quyết định xả lũ.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_UNRELATED_NEGATION",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai được quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    # Must NOT be CONTRADICTED because prohibition was for "cơ quan khác", not claim actor
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert res.conflicting_evidence_ids == []
    assert ReasonCode.ACTION_MISMATCH.value in res.reason_codes


def test_structured_threshold_condition_absent_is_insufficient(verifier):
    """6. Structured threshold condition absent -> INSUFFICIENT."""
    evidence = EvidenceSet(
        query_id="Q_THRESH_ABSENT",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_THRESH_ABSENT",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi ngưỡng >=85 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="GE", value="85", unit="m")],
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.CONDITION_MISSING.value in res.reason_codes
    assert "conditions" in res.missing_evidence_slots


def test_correct_structured_threshold_condition_supported_with_adequate_evidence(verifier):
    """7. Correct structured threshold condition -> support only with adequate evidence."""
    evidence = EvidenceSet(
        query_id="Q_THRESH_MATCHED",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước hồ từ 85 m trở lên.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_THRESH_MATCHED",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi ngưỡng >=85 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="GE", value="85", unit="m")],
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.SUPPORTED
    assert ReasonCode.CONDITION_MATCHED.value in res.reason_codes


def test_explicit_incompatible_threshold_is_contradicted(verifier):
    """8. Explicit incompatible threshold -> appropriate non-supported outcome (INSUFFICIENT with CONDITION_CONTRADICTED)."""
    evidence = EvidenceSet(
        query_id="Q_THRESH_CONTRADICTED",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước hồ dưới 85 m.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_THRESH_CONTRADICTED",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi ngưỡng >=85 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="GE", value="85", unit="m")],
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.CONDITION_CONTRADICTED.value in res.reason_codes
    assert "conditions" in res.missing_evidence_slots


def test_unsupported_condition_operator_is_insufficient(verifier):
    """9. Unsupported condition operator -> INSUFFICIENT."""
    evidence = EvidenceSet(
        query_id="Q_THRESH_UNSUPPORTED",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_THRESH_UNSUPPORTED",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="UNSUPPORTED_OP", value="85", unit="m")],
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.CONDITION_MISSING.value in res.reason_codes


def test_negative_water_level_elevation_with_matching_evidence_is_supported(verifier):
    """10. Negative water-level elevation with matching evidence -> not automatically contradicted."""
    evidence = EvidenceSet(
        query_id="Q_NEGATIVE_ELEVATION",
        evidence_items=[
            _item("E1", "Trạm đo hạ lưu hồ Trị An ghi nhận mực nước -2 m so với mốc cao độ chuẩn Hải Đồ.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_NEG_ELEVATION",
        claim_text="Mực nước trạm hạ lưu hồ Trị An là -2 m",
        subject="Hồ Trị An",
        parameter="Mực nước",
        value="-2",
        unit="m",
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.SUPPORTED
    assert "STRUCTURAL_NON_NEGATIVE_PHYSICAL_BOUND" not in res.violated_constraints


def test_negative_storage_volume_violates_physical_constraint(verifier):
    """Negative storage volume is genuinely physically impossible -> CONTRADICTED."""
    claim = TechnicalClaim(
        claim_id="C_NEG_STORAGE",
        claim_text="Dung tích toàn bộ hồ Hòa Bình là -50 triệu m3",
        subject="Hồ Hòa Bình",
        parameter="Dung tích toàn bộ",
        value="-50",
        unit="triệu m3",
    )
    res = verifier.verify_single_claim(claim, EvidenceSet(query_id="Q_EMPTY", evidence_items=[]))
    assert res.status == ClaimVerificationStatus.CONTRADICTED
    assert "STRUCTURAL_NON_NEGATIVE_PHYSICAL_BOUND" in res.violated_constraints
    assert ReasonCode.CONSTRAINT_VIOLATED.value in res.reason_codes


def test_dimensionally_incompatible_unit_rejected(verifier):
    """11. Valid dimensionally incompatible unit -> appropriate rejection."""
    evidence = EvidenceSet(
        query_id="Q_DIM_INCOMPATIBLE",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_DIM_INCOMPATIBLE",
        claim_text="Mực nước dâng bình thường hồ Hòa Bình là 117 m3/s",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m3/s",
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.CONTRADICTED
    assert ReasonCode.UNIT_INCOMPATIBLE.value in res.reason_codes


def test_valid_citation_plus_nonexistent_citation_plus_contradictory_text_preserves_citation_error(verifier):
    """12. Valid citation plus nonexistent citation plus contradictory text -> citation error preserved."""
    evidence = EvidenceSet(
        query_id="Q_MIXED_CITATIONS_CONTRADICTED",
        evidence_items=[
            _item("E_VALID", "Hồ Hòa Bình có mực nước dâng bình thường 118 m.")
        ],
    )
    # Claim cites both valid E_VALID (contradictory: 118 != 117) and nonexistent E_NONEXISTENT
    claim = TechnicalClaim(
        claim_id="C_MIXED_CONTRADICTED",
        claim_text="Mực nước dâng bình thường hồ Hòa Bình là 117 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        evidence_ids=["E_VALID", "E_NONEXISTENT"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    # Factual contradiction from valid evidence is caught
    assert res.status == ClaimVerificationStatus.CONTRADICTED
    assert "E_VALID" in res.conflicting_evidence_ids
    # Crucially, citation error reason codes and missing slot MUST be preserved!
    assert ReasonCode.CITATION_IDENTITY_MISMATCH.value in res.reason_codes
    assert ReasonCode.PROVENANCE_INVALID.value in res.reason_codes
    assert "explicit_citation" in res.missing_evidence_slots
    assert len(res.verifier_metadata["invalid_references"]) == 1
    assert res.verifier_metadata["invalid_references"][0]["evidence_id"] == "E_NONEXISTENT"



def test_source_backed_development_fixtures_match_corpus_records():
    runner = OfflineEvaluationRunner()
    cases = runner.load_source_backed_development_suite()
    assert cases
    assert all(case.p5_result == "NOT_EVALUATED" for case in cases)
    assert all("NOT_INDEPENDENT_GOLD" in case.label_origin for case in cases)

    pages = {}
    with open("data/pages.jsonl", "r", encoding="utf-8") as page_file:
        for line in page_file:
            record = json.loads(line)
            pages[(record["doc_id"], record["page_number"])] = record

    normalize_ws = lambda text: re.sub(r"\s+", " ", text).strip()
    for case in cases:
        provenance = case.source_provenance[0]
        page = pages[(provenance["doc_id"], provenance["page_number"])]
        assert provenance["source_record_sha256"] == page["sha256"]
        assert normalize_ws(provenance["source_text"]) in normalize_ws(page["raw_text"])


def test_evaluation_reports_agreement_not_scientific_accuracy(tmp_path):
    result = OfflineEvaluationRunner().run_all(output_dir=tmp_path)
    summary = result["summary"]
    assert "overall_accuracy" not in summary
    assert summary["scientific_accuracy"] is None
    assert summary["scientific_evaluation_status"] == "NOT_EVALUATED_NO_INDEPENDENT_GOLD_LABELS"
    assert summary["p5_paired_comparison_status"] == "NOT_EVALUATED_NO_ACTUAL_P5_EXECUTION"
    assert all(row["p5_result"] == "NOT_EVALUATED" for row in result["case_outputs"])


# =============================================================================
# S2.4 FINAL FALSE-SUPPORT GATE ACCEPTANCE TESTS (SECTION 4)
# =============================================================================

def test_incidental_threshold_value_does_not_establish_applicability(verifier):
    """1. An incidental threshold value must not establish applicability."""
    evidence = EvidenceSet(
        query_id="Q_INCIDENTAL_THRESH",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m; số liệu mực nước lịch sử 85 m.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_INCIDENTAL_THRESH",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi ngưỡng >= 85 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="GE", value="85", unit="m")],
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.CONDITION_MISSING.value in res.reason_codes
    assert "conditions" in res.missing_evidence_slots


def test_explicit_valid_ge_le_thresholds_work(verifier):
    """2. Explicit valid GE/LE thresholds must still work."""
    # Case GE
    ev_ge = EvidenceSet(
        query_id="Q_VALID_GE",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước hồ từ 85 m trở lên.")
        ],
    )
    claim_ge = TechnicalClaim(
        claim_id="C_VALID_GE",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi ngưỡng >= 85 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="GE", value="85", unit="m")],
        evidence_ids=["E1"],
    )
    res_ge = verifier.verify_single_claim(claim_ge, ev_ge)
    assert res_ge.status == ClaimVerificationStatus.SUPPORTED
    assert ReasonCode.CONDITION_MATCHED.value in res_ge.reason_codes

    # Case LE
    ev_le = EvidenceSet(
        query_id="Q_VALID_LE",
        evidence_items=[
            _item("E2", "Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước hồ từ 85 m trở xuống.")
        ],
    )
    claim_le = TechnicalClaim(
        claim_id="C_VALID_LE",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi ngưỡng <= 85 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="LE", value="85", unit="m")],
        evidence_ids=["E2"],
    )
    res_le = verifier.verify_single_claim(claim_le, ev_le)
    assert res_le.status == ClaimVerificationStatus.SUPPORTED
    assert ReasonCode.CONDITION_MATCHED.value in res_le.reason_codes


def test_between_requires_both_endpoints(verifier):
    """3. BETWEEN requires both endpoints."""
    # Case A: Only one endpoint present in evidence -> INSUFFICIENT
    ev_one = EvidenceSet(
        query_id="Q_BETWEEN_ONE",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước từ 85 m trở lên.")
        ],
    )
    claim_between = TechnicalClaim(
        claim_id="C_BETWEEN",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước trong khoảng 85-115 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="BETWEEN", value="85-115", unit="m")],
        evidence_ids=["E1"],
    )
    res_one = verifier.verify_single_claim(claim_between, ev_one)
    assert res_one.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.CONDITION_MISSING.value in res_one.reason_codes

    # Case B: Both endpoints present in range context -> SUPPORTED
    ev_both = EvidenceSet(
        query_id="Q_BETWEEN_BOTH",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước hồ trong khoảng từ 85 m đến 115 m.")
        ],
    )
    res_both = verifier.verify_single_claim(claim_between, ev_both)
    assert res_both.status == ClaimVerificationStatus.SUPPORTED
    assert ReasonCode.CONDITION_MATCHED.value in res_both.reason_codes


def test_threshold_belonging_to_another_structure_does_not_support_claim(verifier):
    """4. Threshold belonging to another structure must not support the claim."""
    evidence = EvidenceSet(
        query_id="Q_OTHER_STRUCT_THRESH",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m. Hồ Sơn La khi ngưỡng >= 85 m phải xả lũ.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_OTHER_STRUCT_THRESH",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi ngưỡng >= 85 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="GE", value="85", unit="m")],
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.CONDITION_MISSING.value in res.reason_codes


def test_different_actors_in_contrastive_sentence(verifier):
    """5. Different actors in one contrastive sentence."""
    evidence = EvidenceSet(
        query_id="Q_CONTRASTIVE_ACTORS",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai phát biểu tại cuộc họp, còn Ban chỉ huy được quyết định xả lũ.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_CONTRASTIVE_ACTOR",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai được quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert res.conflicting_evidence_ids == []
    assert ReasonCode.ACTION_MISMATCH.value in res.reason_codes


def test_mention_of_illegal_action_does_not_establish_legal_permission(verifier):
    """6. Mention of an illegal action must not establish legal permission."""
    evidence = EvidenceSet(
        query_id="Q_ILLEGAL_ACTION",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai bị cơ quan điều tra xem xét về việc quyết định xả lũ trái phép.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_ILLEGAL_ACTION",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai được quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.ACTION_MISMATCH.value in res.reason_codes


def test_legal_claim_with_missing_structured_action(verifier):
    """7. Legal claim with missing structured action."""
    evidence = EvidenceSet(
        query_id="Q_MISSING_ACTION",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai tham dự cuộc họp an toàn đập.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_MISSING_ACTION",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai được quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        polarity=ClaimPolarity.AFFIRMED,
        action=None,  # Missing structured action field
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.INCOMPLETE_CLAIM_EXTRACTION.value in res.reason_codes
    assert "action" in res.missing_evidence_slots


def test_explicit_same_actor_legal_authorization(verifier):
    """8. Explicit same-actor legal authorization."""
    evidence = EvidenceSet(
        query_id="Q_SAME_ACTOR_AUTH",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai được quyền quyết định xả lũ trong tình huống khẩn cấp.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_SAME_ACTOR_AUTH",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai được quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.SUPPORTED
    assert ReasonCode.POLARITY_MATCHED.value in res.reason_codes


def test_explicit_same_actor_prohibition(verifier):
    """9. Explicit same-actor prohibition."""
    evidence = EvidenceSet(
        query_id="Q_SAME_ACTOR_PROHIB",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai không được quyết định xả lũ khi chưa có lệnh của Ban Chỉ đạo.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_SAME_ACTOR_PROHIB",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai được quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.CONTRADICTED
    assert ReasonCode.POLARITY_CONTRADICTED.value in res.reason_codes
    assert "E1" in res.conflicting_evidence_ids


def test_ambiguous_authorization_remains_insufficient(verifier):
    """10. Ambiguous authorization must remain INSUFFICIENT."""
    evidence = EvidenceSet(
        query_id="Q_AMBIGUOUS_AUTH",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai trao đổi về việc quyết định xả lũ tại cuộc họp.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_AMBIGUOUS_AUTH",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai được quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.ACTION_MISMATCH.value in res.reason_codes


# =============================================================================
# STAGE 3 SPRINT A — PHASE 0 ACCEPTANCE TESTS
# =============================================================================

def test_phase0_legal_modality_past_action_is_insufficient(verifier):
    """Phase 0.A.1: Actual performance / past action must NOT establish legal authority."""
    evidence = EvidenceSet(
        query_id="Q_P0_PAST_ACTION",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai đã quyết định xả lũ.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_P0_AUTH_1",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai được quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.ACTION_MISMATCH.value in res.reason_codes


def test_phase0_legal_modality_pending_authorization_is_insufficient(verifier):
    """Phase 0.A.2: Pending authorization must NOT establish legal authority."""
    evidence = EvidenceSet(
        query_id="Q_P0_PENDING",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai chưa được quyết định xả lũ.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_P0_AUTH_2",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai được quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.ACTION_MISMATCH.value in res.reason_codes


def test_phase0_legal_modality_inability_is_insufficient(verifier):
    """Phase 0.A.3: Inability must NOT establish legal authority or formal prohibition."""
    evidence = EvidenceSet(
        query_id="Q_P0_INABILITY",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai không thể quyết định xả lũ.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_P0_AUTH_3",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai được quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.ACTION_MISMATCH.value in res.reason_codes


def test_phase0_legal_modality_study_assignment_is_insufficient(verifier):
    """Phase 0.A.4: Assigned to study/research must NOT establish authority to decide."""
    evidence = EvidenceSet(
        query_id="Q_P0_STUDY",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai được giao nghiên cứu việc quyết định xả lũ.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_P0_AUTH_4",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai được quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.ACTION_MISMATCH.value in res.reason_codes


def test_phase0_legal_modality_advice_is_insufficient(verifier):
    """Phase 0.A.5: Advice or recommendation must NOT establish legal authority."""
    evidence = EvidenceSet(
        query_id="Q_P0_ADVICE",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai không nên quyết định xả lũ.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_P0_AUTH_5",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai được quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.ACTION_MISMATCH.value in res.reason_codes


def test_phase0_claim_ge_vs_evidence_gt_is_insufficient(verifier):
    """Phase 0.B.1: Claim GE 85 vs evidence GT 85 must return INSUFFICIENT."""
    evidence = EvidenceSet(
        query_id="Q_P0_GE_GT",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước hồ lớn hơn 85 m.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_P0_GE",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi ngưỡng >= 85 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="GE", value="85", unit="m")],
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.CONDITION_MISSING.value in res.reason_codes


def test_phase0_claim_le_vs_evidence_lt_is_insufficient(verifier):
    """Phase 0.B.2: Claim LE 85 vs evidence LT 85 must return INSUFFICIENT."""
    evidence = EvidenceSet(
        query_id="Q_P0_LE_LT",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước hồ dưới 85 m.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_P0_LE",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi ngưỡng <= 85 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="LE", value="85", unit="m")],
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.CONDITION_MISSING.value in res.reason_codes


def test_phase0_claim_unit_m_vs_evidence_discharge_m3s_is_insufficient(verifier):
    """Phase 0.B.3: Claim threshold 85 m vs evidence discharge threshold 85 m3/s -> INSUFFICIENT."""
    evidence = EvidenceSet(
        query_id="Q_P0_UNIT_DIM",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m khi lưu lượng xả từ 85 m3/s trở lên.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_P0_UNIT_M",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi ngưỡng >= 85 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="GE", value="85", unit="m")],
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.CONDITION_MISSING.value in res.reason_codes


def test_phase0_claim_mndbt_threshold_vs_evidence_mnc_threshold_is_insufficient(verifier):
    """Phase 0.B.4: Threshold for normal pool level vs evidence threshold for dead water level -> INSUFFICIENT."""
    evidence = EvidenceSet(
        query_id="Q_P0_PARAM_ID",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m; mực nước chết khi ngưỡng >= 85 m phải xả lũ.")
        ],
    )
    claim = TechnicalClaim(
        claim_id="C_P0_PARAM_THRESH",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước dâng bình thường >= 85 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="GE", value="85", unit="m", raw_text="mực nước dâng bình thường >= 85 m")],
        evidence_ids=["E1"],
    )
    res = verifier.verify_single_claim(claim, evidence)
    assert res.status == ClaimVerificationStatus.INSUFFICIENT
    assert ReasonCode.CONDITION_MISSING.value in res.reason_codes


def test_phase0_positive_explicit_ge_and_le_thresholds_supported(verifier):
    """Phase 0.Acceptance: Valid explicit GE/LE thresholds with matching evidence return SUPPORTED."""
    ev_ge = EvidenceSet(
        query_id="Q_P0_POS_GE",
        evidence_items=[
            _item("E1", "Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước hồ từ 85 m trở lên.")
        ],
    )
    claim_ge = TechnicalClaim(
        claim_id="C_P0_POS_GE",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi ngưỡng >= 85 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="GE", value="85", unit="m")],
        evidence_ids=["E1"],
    )
    res_ge = verifier.verify_single_claim(claim_ge, ev_ge)
    assert res_ge.status == ClaimVerificationStatus.SUPPORTED

    ev_le = EvidenceSet(
        query_id="Q_P0_POS_LE",
        evidence_items=[
            _item("E2", "Hồ Hòa Bình có mực nước dâng bình thường 117 m khi mực nước hồ không vượt quá 115 m.")
        ],
    )
    claim_le = TechnicalClaim(
        claim_id="C_P0_POS_LE",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117 m khi ngưỡng <= 115 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117",
        unit="m",
        conditions=[ClaimCondition(operator="LE", value="115", unit="m")],
        evidence_ids=["E2"],
    )
    res_le = verifier.verify_single_claim(claim_le, ev_le)
    assert res_le.status == ClaimVerificationStatus.SUPPORTED


def test_phase0_positive_explicit_legal_authority_and_prohibition_supported(verifier):
    """Phase 0.Acceptance: Explicit genuine legal authority and prohibition return SUPPORTED."""
    ev_auth = EvidenceSet(
        query_id="Q_P0_POS_AUTH",
        evidence_items=[
            _item("E1", "Chủ tịch UBND tỉnh Đồng Nai có thẩm quyền quyết định xả lũ trong tình huống khẩn cấp.")
        ],
    )
    claim_auth = TechnicalClaim(
        claim_id="C_P0_POS_AUTH",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai có thẩm quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.AFFIRMED,
        evidence_ids=["E1"],
    )
    res_auth = verifier.verify_single_claim(claim_auth, ev_auth)
    assert res_auth.status == ClaimVerificationStatus.SUPPORTED
    assert ReasonCode.POLARITY_MATCHED.value in res_auth.reason_codes

    ev_prohib = EvidenceSet(
        query_id="Q_P0_POS_PROHIB",
        evidence_items=[
            _item("E2", "Chủ tịch UBND tỉnh Đồng Nai không có thẩm quyền quyết định xả lũ tại công trình này.")
        ],
    )
    claim_prohib = TechnicalClaim(
        claim_id="C_P0_POS_PROHIB",
        claim_text="Chủ tịch UBND tỉnh Đồng Nai không có thẩm quyền quyết định xả lũ",
        subject="Chủ tịch UBND tỉnh Đồng Nai",
        jurisdiction="tỉnh Đồng Nai",
        action="quyết định xả lũ",
        polarity=ClaimPolarity.NEGATED,
        evidence_ids=["E2"],
    )
    res_prohib = verifier.verify_single_claim(claim_prohib, ev_prohib)
    assert res_prohib.status == ClaimVerificationStatus.SUPPORTED
    assert ReasonCode.POLARITY_MATCHED.value in res_prohib.reason_codes


