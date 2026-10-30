"""Mandatory Verification & Regression Test Suite for Final Correctness Sprint.

Validates the three confirmed technical fixes:
1. Strict citation identity and provenance (zero substring, prefix, or fake cell acceptance).
2. Relation-aware atomic claim extraction (clause splitting, local temporal/entity/param/obs binding).
3. Evaluator relational fact matching (swapped dates, entity mismatch, extra claims rejected).
"""

import pytest
from viirr_ontology.schema.claim import ClaimPolarity, EvidenceCitation, TechnicalClaim
from viirr_ontology.schema.evidence import EvidenceItem
from viirr_ontology.shadow_verifier import FourValuedStatus, ShadowOntologyVerifier
from viirr_ontology.typed_facts import (
    extract_atomic_claims,
    extract_iso_date,
    parse_vietnamese_number,
)


@pytest.fixture
def verifier():
    return ShadowOntologyVerifier()


# =============================================================================
# GATE 1: STRICT CITATION IDENTITY & PROVENANCE
# =============================================================================

def test_gate1_exact_citation_id_accepted(verifier):
    """Exact citation ID in context is accepted."""
    claim = TechnicalClaim(
        claim_id="C1",
        claim_text="Mực nước hồ Hòa Bình ngày 02/10/2024 đạt 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        temporal_scope="2024-10-02",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "EVID_01")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Báo cáo ngày 02/10/2024: Mực nước hồ Hòa Bình hiện tại là 115,42 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.SUPPORTED
    assert "CITATION_VALID" in res.reason_codes
    assert "VALUE_MATCHED" in res.reason_codes


def test_gate1_citation_substring_rejected(verifier):
    """Citation 'EVID' must NOT match 'EVID_01' through substring or prefix."""
    claim = TechnicalClaim(
        claim_id="C2",
        claim_text="Mực nước hồ Hòa Bình ngày 02/10/2024 đạt 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        temporal_scope="2024-10-02",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "EVID")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Báo cáo ngày 02/10/2024: Mực nước hồ Hòa Bình hiện tại là 115,42 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "CITATION_NONEXISTENT" in res.reason_codes
    # Content exists in context, so SUPPORT_FOUND_BUT_CITATION_INVALID must be logged
    assert "SUPPORT_FOUND_BUT_CITATION_INVALID" in res.reason_codes


def test_gate1_invented_table_cell_suffix_rejected(verifier):
    """Invented cell suffix 'TAB_01_R999_C999' with parent 'TAB_01' in context must be REJECTED."""
    claim = TechnicalClaim(
        claim_id="C3",
        claim_text="Mực nước hồ Hòa Bình ngày 02/10/2024 đạt 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        temporal_scope="2024-10-02",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "TAB_01_R999_C999")],
    )
    table_text = (
        "| Hồ chứa | Ngày | Mực nước (m) |\n"
        "| Hồ Hòa Bình | 02/10/2024 | 115,42 |\n"
        "| Hồ Thác Bà | 02/10/2024 | 58,00 |"
    )
    evidence = [
        EvidenceItem(
            evidence_id="TAB_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            content_type="table",
            text=table_text,
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "CITATION_NONEXISTENT" in res.reason_codes


def test_gate1_valid_dynamically_derived_table_cell_accepted(verifier):
    """Valid dynamically derived cell 'TAB_01_R000_C002' matching parent 'TAB_01' is accepted."""
    claim = TechnicalClaim(
        claim_id="C4",
        claim_text="Mực nước hồ Hòa Bình ngày 02/10/2024 đạt 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        temporal_scope="2024-10-02",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "TAB_01_R000_C003")],
    )
    table_text = (
        "| Hồ chứa | Ngày | Mực nước (m) |\n"
        "| Hồ Hòa Bình | 02/10/2024 | 115,42 |\n"
        "| Hồ Thác Bà | 02/10/2024 | 58,00 |"
    )
    evidence = [
        EvidenceItem(
            evidence_id="TAB_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            content_type="table",
            text=table_text,
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.SUPPORTED
    assert "CITATION_VALID" in res.reason_codes


def test_gate1_two_citations_one_valid_one_invalid(verifier):
    """If a claim cites 2 IDs and one is nonexistent, citation verification fails."""
    claim = TechnicalClaim(
        claim_id="C5",
        claim_text="Mực nước hồ Hòa Bình ngày 02/10/2024 đạt 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        temporal_scope="2024-10-02",
        evidence_citations=[
            EvidenceCitation("DOC_01", 1, "EVID_01"),
            EvidenceCitation("DOC_01", 1, "EVID_FAKE_99"),
        ],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Báo cáo ngày 02/10/2024: Mực nước hồ Hòa Bình hiện tại là 115,42 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "CITATION_NONEXISTENT" in res.reason_codes


def test_gate1_claim_missing_citations_flagged(verifier):
    """Claim without citations records CITATION_MISSING."""
    claim = TechnicalClaim(
        claim_id="C6",
        claim_text="Mực nước hồ Hòa Bình ngày 02/10/2024 đạt 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        temporal_scope="2024-10-02",
        evidence_citations=[],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Báo cáo ngày 02/10/2024: Mực nước hồ Hòa Bình hiện tại là 115,42 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert "CITATION_MISSING" in res.reason_codes
    assert "FACT_SUPPORTED_WITHOUT_CITATION" in res.reason_codes
    assert "CITATION_VALID" not in res.reason_codes


# =============================================================================
# GATE 2: RELATION-AWARE ATOMIC CLAIM EXTRACTION
# =============================================================================

def test_gate2_an_long_two_dates_and_two_observation_types():
    """An Long sentence with observed date A and forecast date B."""
    ans = "Ngày 02/10/2026, mực nước thực đo tại An Long là 2,94 m, còn dự báo ngày 04/10/2026 là 2,73 m."
    claims = extract_atomic_claims(ans, qa_id="QA_TEST_01")
    assert len(claims) == 2

    c1, c2 = claims[0], claims[1]
    assert c1.subject == "An Long"
    assert c1.value == "2,94"
    assert c1.unit == "m"
    assert c1.temporal_scope == "2026-10-02"
    assert c1.observation_type == "ACTUAL_OBSERVED"

    assert c2.subject == "An Long"
    assert c2.value == "2,73"
    assert c2.unit == "m"
    assert c2.temporal_scope == "2026-10-04"
    assert c2.observation_type == "FORECAST_ESTIMATE"


def test_gate2_respective_enumeration_lan_luot_la():
    """Respective enumeration (lần lượt là) 1-to-1 date/value pairing."""
    ans = (
        "Theo chuỗi tài liệu liên quan, mực nước lớn nhất dự báo của VB2 tại các kỳ "
        "ngày 01 tháng 10 năm 2026, ngày 03 tháng 10 năm 2026 và ngày 04 tháng 10 năm 2026 "
        "lần lượt là 1,45 m, 1,53 m và 1,30 m."
    )
    claims = extract_atomic_claims(ans, qa_id="QA_TEST_02")
    assert len(claims) == 3

    assert claims[0].subject == "VB2"
    assert claims[0].temporal_scope == "2026-10-01"
    assert claims[0].value == "1,45"
    assert claims[0].observation_type == "FORECAST_ESTIMATE"

    assert claims[1].subject == "VB2"
    assert claims[1].temporal_scope == "2026-10-03"
    assert claims[1].value == "1,53"
    assert claims[1].observation_type == "FORECAST_ESTIMATE"

    assert claims[2].subject == "VB2"
    assert claims[2].temporal_scope == "2026-10-04"
    assert claims[2].value == "1,30"
    assert claims[2].observation_type == "FORECAST_ESTIMATE"


def test_gate2_two_entities_in_same_sentence():
    """Two different entities mentioned across coordinate clauses."""
    ans = "Mực nước trạm Tân Hồng là 2,85 m, còn tại VB2 là 1,54 m."
    claims = extract_atomic_claims(ans, qa_id="QA_TEST_03")
    assert len(claims) == 2

    assert claims[0].subject == "Tân Hồng"
    assert claims[0].value == "2,85"

    assert claims[1].subject == "VB2"
    assert claims[1].value == "1,54"


def test_gate2_two_parameters_in_same_sentence():
    """Two different parameters mentioned in the same sentence."""
    ans = "Hồ Hòa Bình có mực nước là 115,42 m, lưu lượng xả là 450 m3/s."
    claims = extract_atomic_claims(ans, qa_id="QA_TEST_04")
    assert len(claims) == 2

    assert claims[0].subject == "Hồ Hòa Bình"
    assert claims[0].parameter == "Mực nước"
    assert claims[0].value == "115,42"

    assert claims[1].subject == "Hồ Hòa Bình"
    assert claims[1].parameter == "Lưu lượng xả"
    assert claims[1].value == "450"
    assert claims[1].unit == "m3/s"


def test_gate2_clause_bound_inline_citations():
    """Inline citations attached to specific clauses are bound locally."""
    ans = "Mực nước trạm Tân Hồng là 2,85 m [EVID_TH], còn tại VB2 là 1,54 m [EVID_VB2]."
    claims = extract_atomic_claims(ans, qa_id="QA_TEST_05")
    assert len(claims) == 2

    assert [c.evidence_id for c in claims[0].evidence_citations] == ["EVID_TH"]
    assert [c.evidence_id for c in claims[1].evidence_citations] == ["EVID_VB2"]


def test_gate2_negative_unicode_minus():
    """Preserves negative measurements with Unicode minus."""
    ans = "Độ hạ thấp mực nước hồ là −3,2 m."
    claims = extract_atomic_claims(ans, qa_id="QA_TEST_06")
    assert len(claims) == 1
    assert claims[0].value == "-3,2"
    assert parse_vietnamese_number(claims[0].value) == -3.2


def test_gate2_negated_claim_polarity():
    """Negated assertion receives ClaimPolarity.NEGATED."""
    ans = "Lưu lượng xả trạm Cổ Mân không đạt 450 m3/s."
    claims = extract_atomic_claims(ans, qa_id="QA_TEST_07")
    assert len(claims) == 1
    assert claims[0].polarity == ClaimPolarity.NEGATED
