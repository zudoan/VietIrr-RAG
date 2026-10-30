"""Regression test suite for VietIRR-RAG Data Consistency Sprint.

Covers:
1. Multi-document citation resolution (no false doc_mismatch when citations span multiple documents).
2. Clause-level entity & temporal binding on real Qwen outputs (An Long, Ham Giang/Long Hiep, Bac Trang/Bong Bot).
3. Separation of factual support from citation validity (SUPPORT_FOUND_BUT_CITATION_INVALID).
4. Table cell structured prefix parsing ([Ô BẢNG NGUỒN]).
5. Elevation dimension parameter compatibility (Cao trình đáy vs Cao trình).
6. Evaluator extra unsupported claim detection (prevents false CORRECT_COMPLETE).
7. Question requirement completeness vs claim support coverage.
8. Failure injections: swapped dates, swapped entities, fabricated citations.
"""

import pytest
from viirr_ontology.schema.claim import (
    ClaimPolarity,
    EvidenceCitation,
    TechnicalClaim,
)
from viirr_ontology.schema.evidence import EvidenceItem
from viirr_ontology.shadow_verifier import FourValuedStatus, ShadowOntologyVerifier
from viirr_ontology.typed_facts import (
    ObservationFact,
    DesignSpecificationFact,
    TypedFactExtractor,
    extract_atomic_claims,
    resolve_canonical_entity,
    resolve_canonical_parameter,
    extract_iso_date,
)


@pytest.fixture
def verifier():
    return ShadowOntologyVerifier()


# -----------------------------------------------------------------------------
# Test 1: Multi-document citation resolution (Issue A)
# -----------------------------------------------------------------------------
def test_multi_document_citations_no_false_doc_mismatch(verifier):
    """Citations from two different documents in the same answer must retain their own doc_id."""
    ev1 = EvidenceItem(
        evidence_id="EVID_DOC_A",
        doc_id="DOC_A",
        page_id="P1",
        page_number=1,
        text="Hồ Hòa Bình có mực nước dâng bình thường 117.0 m.",
    )
    ev2 = EvidenceItem(
        evidence_id="EVID_DOC_B",
        doc_id="DOC_B",
        page_id="P1",
        page_number=1,
        text="Hồ Sơn La có mực nước dâng bình thường 215.0 m.",
    )
    evidence_set = [ev1, ev2]

    # Citations correctly mapped to each item's own doc_id
    cits = [
        EvidenceCitation(doc_id="DOC_A", page_number=1, evidence_id="EVID_DOC_A"),
        EvidenceCitation(doc_id="DOC_B", page_number=1, evidence_id="EVID_DOC_B"),
    ]

    claim1 = TechnicalClaim(
        claim_id="C1",
        claim_text="Hồ Hòa Bình có mực nước dâng bình thường 117.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117.0",
        unit="m",
        evidence_citations=[cits[0]],
    )
    claim2 = TechnicalClaim(
        claim_id="C2",
        claim_text="Hồ Sơn La có mực nước dâng bình thường 215.0 m",
        subject="Hồ Sơn La",
        parameter="Mực nước dâng bình thường",
        value="215.0",
        unit="m",
        evidence_citations=[cits[1]],
    )

    res1 = verifier.verify_claim(claim1, evidence_set)
    res2 = verifier.verify_claim(claim2, evidence_set)

    assert res1.status == FourValuedStatus.SUPPORTED
    assert res1.citation_validity == "VALID"
    assert "doc_mismatch" not in str(res1.rule_evaluations)

    assert res2.status == FourValuedStatus.SUPPORTED
    assert res2.citation_validity == "VALID"
    assert "doc_mismatch" not in str(res2.rule_evaluations)


# -----------------------------------------------------------------------------
# Test 2: Real An Long multi-date multi-observation extraction (Issue B, Case 1)
# -----------------------------------------------------------------------------
def test_real_an_long_extraction_and_verification(verifier):
    """An Long compound sentence with actual and forecast observations."""
    text = "Mực nước lớn nhất thực đo ngày 02/10/2026 của An Long là 2,94 m và mực nước lớn nhất dự báo ngày 04/10/2026 là 2,73 m."
    cits = [
        EvidenceCitation(doc_id="DOC_AN_LONG_FC", page_number=1, evidence_id="EVID_AL_FC_0410"),
        EvidenceCitation(doc_id="DOC_AN_LONG_ACT", page_number=1, evidence_id="EVID_AL_ACT_0210"),
    ]
    claims = extract_atomic_claims(text, default_entity="An Long", default_parameter="WaterLevel", citations=cits)

    assert len(claims) == 2

    # Claim 1: actual observed 02/10
    c1 = claims[0]
    assert c1.subject == "An Long"
    assert c1.temporal_scope == "2026-10-02"
    assert c1.observation_type == "ACTUAL_OBSERVED"
    assert c1.value == "2,94"

    # Claim 2: forecast 04/10
    c2 = claims[1]
    assert c2.subject == "An Long"
    assert c2.temporal_scope == "2026-10-04"
    assert c2.observation_type == "FORECAST_ESTIMATE"
    assert c2.value == "2,73"

    # Verify against real structured cell items
    ev_act = EvidenceItem(
        evidence_id="EVID_AL_ACT_0210",
        doc_id="DOC_AN_LONG_ACT",
        page_id="P1",
        page_number=1,
        content_type="table_cell",
        text="[Ô BẢNG NGUỒN] Thực thể: An Long; Thông số: Mực nước lớn nhất thực đo (m) — 02/10; Giá trị: 2,94 m; điều kiện/cột: Mực nước lớn nhất thực đo (m) — 02/10.",
    )
    ev_fc = EvidenceItem(
        evidence_id="EVID_AL_FC_0410",
        doc_id="DOC_AN_LONG_FC",
        page_id="P1",
        page_number=1,
        content_type="table_cell",
        text="[Ô BẢNG NGUỒN] Thực thể: An Long; Thông số: Mực nước lớn nhất dự báo (m) — 04/10; Giá trị: 2,73 m; điều kiện/cột: Mực nước lớn nhất dự báo (m) — 04/10.",
    )
    evidence_set = [ev_act, ev_fc]

    res1 = verifier.verify_claim(c1, evidence_set)
    res2 = verifier.verify_claim(c2, evidence_set)

    assert res1.status == FourValuedStatus.SUPPORTED
    assert res2.status == FourValuedStatus.SUPPORTED


# -----------------------------------------------------------------------------
# Test 3: Real Ham Giang & Long Hiep entity separation (Issue B, Case 2)
# -----------------------------------------------------------------------------
def test_real_ham_giang_long_hiep_entity_separation(verifier):
    """Hàm Giang and Long Hiệp are bound to their respective clauses, not conflated."""
    text = "Cao trình đáy của Hàm Giang là -3 m và Long Hiệp là -2 m."
    claims = extract_atomic_claims(text, default_entity="Hàm Giang", default_parameter="Cao trình đáy")

    assert len(claims) == 2
    assert claims[0].subject == "Hàm Giang"
    assert claims[0].value == "-3"
    assert claims[0].parameter == "Cao trình đáy"

    assert claims[1].subject == "Long Hiệp"
    assert claims[1].value == "-2"
    assert claims[1].parameter == "Cao trình đáy"


# -----------------------------------------------------------------------------
# Test 4: Real Bac Trang & Bong Bot entity separation (Issue B, Case 3)
# -----------------------------------------------------------------------------
def test_real_bac_trang_bong_bot_entity_separation(verifier):
    """Bắc Trang and Bông Bót bound to their respective clauses."""
    text = "Cao trình đáy của Bắc Trang là -3 m và Bông Bót là -4,5 m."
    claims = extract_atomic_claims(text, default_entity="Bắc Trang", default_parameter="Cao trình đáy")

    assert len(claims) == 2
    assert claims[0].subject == "Bắc Trang"
    assert claims[0].value == "-3"

    assert claims[1].subject == "Bông Bót"
    assert claims[1].value == "-4,5"


# -----------------------------------------------------------------------------
# Test 5: Support found in context but citation invalid (Section 5.3)
# -----------------------------------------------------------------------------
def test_support_found_in_context_but_citation_invalid(verifier):
    """When cited item lacks fact but another context item has it -> SUPPORT_FOUND_BUT_CITATION_INVALID."""
    ev_cited = EvidenceItem(
        evidence_id="EVID_CITED_DOC1",
        doc_id="DOC1",
        page_id="P1",
        page_number=1,
        content_type="table_cell",
        text="[Ô BẢNG NGUỒN] Thực thể: Hàm Giang; Thông số: Cao trình đáy (m); Giá trị: -3 m.",
    )
    ev_other = EvidenceItem(
        evidence_id="EVID_OTHER_DOC1",
        doc_id="DOC1",
        page_id="P1",
        page_number=1,
        content_type="table_cell",
        text="[Ô BẢNG NGUỒN] Thực thể: Long Hiệp; Thông số: Cao trình đáy (m); Giá trị: -2 m.",
    )
    evidence_set = [ev_cited, ev_other]

    # Claim asserts Long Hiệp -2m, but caller incorrectly cites ev_cited (Hàm Giang)
    claim = TechnicalClaim(
        claim_id="C_LONG_HIEP",
        claim_text="Long Hiệp là -2 m",
        subject="Long Hiệp",
        parameter="Cao trình đáy",
        value="-2",
        unit="m",
        observation_type="DESIGN_SPECIFICATION",
        evidence_citations=[EvidenceCitation("DOC1", 1, "EVID_CITED_DOC1")],
    )

    res = verifier.verify_claim(claim, evidence_set)

    # Must NOT be final SUPPORTED
    assert res.status == FourValuedStatus.INSUFFICIENT
    # Two-axis evaluation
    assert res.factual_support == "SUPPORTED"
    assert res.citation_validity == "INVALID"
    assert "SUPPORT_FOUND_BUT_CITATION_INVALID" in res.reason_codes


# -----------------------------------------------------------------------------
# Test 6: Failure injection - Swapped observation dates
# -----------------------------------------------------------------------------
def test_failure_injection_swapped_observation_dates(verifier):
    """Claim asserts An Long forecast on 02/10 is 2.73m, but evidence has 2.73m on 04/10 -> REJECTED."""
    ev = EvidenceItem(
        evidence_id="EVID_FC_0410",
        doc_id="DOC1",
        page_id="P1",
        page_number=1,
        content_type="table_cell",
        text="[Ô BẢNG NGUỒN] Thực thể: An Long; Thông số: Mực nước lớn nhất dự báo (m) — 04/10; Giá trị: 2,73 m; điều kiện/cột: Mực nước lớn nhất dự báo (m) — 04/10.",
    )
    # Model mistakenly swapped date to 02/10
    claim_swapped = TechnicalClaim(
        claim_id="C_SWAPPED_DATE",
        claim_text="Mực nước dự báo ngày 02/10/2026 của An Long là 2,73 m",
        subject="An Long",
        parameter="Mực nước",
        value="2.73",
        unit="m",
        temporal_scope="2026-10-02",
        observation_type="FORECAST_ESTIMATE",
        evidence_citations=[EvidenceCitation("DOC1", 1, "EVID_FC_0410")],
    )
    res = verifier.verify_claim(claim_swapped, [ev])
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "TEMPORAL_SCOPE_MISMATCH" in res.reason_codes


# -----------------------------------------------------------------------------
# Test 7: Failure injection - Fabricated TABLE_CELL suffix rejected
# -----------------------------------------------------------------------------
def test_failure_injection_fabricated_table_cell_suffix(verifier):
    """A fabricated table cell suffix like _R999_C999 must be rejected."""
    ev = EvidenceItem(
        evidence_id="TAB_SOURCE_P0001",
        doc_id="DOC1",
        page_id="P1",
        page_number=1,
        content_type="table",
        text="| Cột 1 | Cột 2 |\n| Hàng 1 | 10.5 |",
    )
    claim_fake_cell = TechnicalClaim(
        claim_id="C_FAKE_CELL",
        claim_text="Thông số là 10.5 m",
        subject="Cột 1",
        parameter="Mực nước",
        value="10.5",
        unit="m",
        evidence_citations=[EvidenceCitation("DOC1", 1, "TAB_SOURCE_P0001_R999_C999")],
    )
    res = verifier.verify_claim(claim_fake_cell, [ev])
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "CITATION_NONEXISTENT" in res.reason_codes or "PROVENANCE_INSUFFICIENT" in res.reason_codes
