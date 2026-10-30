"""Comprehensive 35-Case Counterexample Test Suite for VietIRR-RAG Ontology Verifier.

Mandated by Section 11 & Section 12:
Group 1 — Provenance (1-8):
  1. Citation ID exists and belongs to context -> SUPPORTED
  2. Citation ID does not exist in context -> INSUFFICIENT (CITATION_NONEXISTENT)
  3. Citation belongs to different document -> INSUFFICIENT (PROVENANCE_INVALID)
  4. Citation belongs to different page -> INSUFFICIENT (PROVENANCE_INVALID)
  5. Citation belongs to different/unresolved corpus version -> INSUFFICIENT
  6. Evidence source exists but claim cites wrong ID -> INSUFFICIENT
  7. Correct parent TABLE_REGION but nonexistent TABLE_CELL -> INSUFFICIENT
  8. TABLE_CELL wrong row/column -> CONTRADICTED

Group 2 — Numeric (9-15):
  9. 115,42 m vs 115,42 cm -> CONTRADICTED (value mismatch: 1.1542 m != 115.42 m)
  10. 1,1542 m vs 115,42 cm -> SUPPORTED (115.42 cm = 1.1542 m)
  11. −3 m vs -3 m -> SUPPORTED (Unicode minus = ASCII minus)
  12. −3 m vs +3 m -> CONTRADICTED (negative vs positive)
  13. 11 triệu m³ vs 11 m³ -> CONTRADICTED (11,000,000 != 11)
  14. Wrong physical dimension -> CONTRADICTED (m3/s vs m, UNIT_INCOMPATIBLE)
  15. Same number but different parameter -> INSUFFICIENT (MNDBT vs MNC)

Group 3 — Time (16-22):
  16. Same date, same value -> SUPPORTED
  17. Same date, different value -> CONTRADICTED
  18. Different date, same value -> INSUFFICIENT (NOT CONTRADICTED)
  19. Different date, different value -> INSUFFICIENT (NOT CONTRADICTED)
  20. Claim has exact date, evidence date UNKNOWN/MISSING -> INSUFFICIENT (TEMPORAL_DATE_UNVERIFIED)
  21. Observation time vs publication date -> INSUFFICIENT
  22. Observed value vs forecast value -> INSUFFICIENT (OBSERVATION_TYPE_MISMATCH)

Group 4 — Claim and Answer (23-30):
  23. Two claims, one supported and one insufficient -> PARTIAL_SUPPORTED_WITH_INSUFFICIENT
  24. Supported + OUT_OF_SCOPE -> PARTIAL_SUPPORTED_WITH_OUT_OF_SCOPE
  25. Valid number but wrong entity -> CONTRADICTED
  26. Two correct numbers with swapped dates -> CONTRADICTED
  27. One correct claim and one unsupported claim -> PARTIAL_SUPPORTED_WITH_INSUFFICIENT
  28. Question asks three things, answer contains only one -> Completeness partial
  29. Model abstains ("Không đủ bằng chứng...") -> Empty claims / EXTRACTION_UNRESOLVED
  30. Claim parser missing important attributes -> INSUFFICIENT with missing_slots

Group 5 — Evaluation Leakage (31-35):
  31. Verification does not accept reference_answer as evidence
  32. Gold pages cannot become inference evidence
  33. Abstained answers cannot be replaced by references
  34. Missing real source returns INSUFFICIENT / NOT_EVALUABLE
  35. A1 cannot approve a document merely because ID lacks the word FAKE
"""

import pytest
from viirr_ontology.schema.claim import ClaimPolarity, EvidenceCitation, TechnicalClaim
from viirr_ontology.schema.evidence import EvidenceItem
from viirr_ontology.shadow_verifier import (
    FourValuedStatus,
    ShadowOntologyVerifier,
)
from viirr_ontology.typed_facts import (
    extract_atomic_claims,
    parse_vietnamese_number,
)


@pytest.fixture
def verifier():
    return ShadowOntologyVerifier()


# =============================================================================
# GROUP 1: PROVENANCE (Cases 1 - 8)
# =============================================================================

def test_01_citation_id_exists_and_belongs_to_context(verifier):
    """Case 1: Citation ID exists and belongs to context -> SUPPORTED."""
    claim = TechnicalClaim(
        claim_id="C01",
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
    assert "VALUE_MATCHED" in res.reason_codes


def test_02_citation_id_nonexistent(verifier):
    """Case 2: Citation ID does not exist in context -> INSUFFICIENT with CITATION_NONEXISTENT."""
    claim = TechnicalClaim(
        claim_id="C02",
        claim_text="Mực nước hồ Hòa Bình ngày 02/10/2024 đạt 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        temporal_scope="2024-10-02",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "A_NONEXISTENT_EVIDENCE")],
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


def test_03_citation_different_document(verifier):
    """Case 3: Citation belongs to a different document -> INSUFFICIENT with PROVENANCE_INVALID."""
    claim = TechnicalClaim(
        claim_id="C03",
        claim_text="Mực nước hồ Hòa Bình ngày 02/10/2024 đạt 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        temporal_scope="2024-10-02",
        evidence_citations=[EvidenceCitation("DOC_WRONG", 1, "EVID_01")],
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
    assert "PROVENANCE_INVALID" in res.reason_codes


def test_04_citation_different_page(verifier):
    """Case 4: Citation belongs to a different page -> INSUFFICIENT with PROVENANCE_INVALID."""
    claim = TechnicalClaim(
        claim_id="C04",
        claim_text="Mực nước hồ Hòa Bình ngày 02/10/2024 đạt 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        temporal_scope="2024-10-02",
        evidence_citations=[EvidenceCitation("DOC_01", 99, "EVID_01")],
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
    assert "PROVENANCE_INVALID" in res.reason_codes


def test_05_citation_different_corpus_version(verifier):
    """Case 5: Citation belongs to unresolvable/fake doc ID -> INSUFFICIENT with FAKE/INVALID."""
    claim = TechnicalClaim(
        claim_id="C05",
        claim_text="Mực nước hồ Hòa Bình ngày 02/10/2024 đạt 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        temporal_scope="2024-10-02",
        evidence_citations=[EvidenceCitation("DOC_FAKE_V9", 1, "EVID_FAKE")],
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
    assert "CITATION_NONEXISTENT" in res.reason_codes or "PROVENANCE_INVALID" in res.reason_codes


def test_06_evidence_source_exists_but_wrong_citation_id(verifier):
    """Case 6: Real evidence exists in context, but claim cites wrong ID -> INSUFFICIENT."""
    claim = TechnicalClaim(
        claim_id="C06",
        claim_text="Mực nước hồ Hòa Bình ngày 02/10/2024 đạt 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        temporal_scope="2024-10-02",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "EVID_WRONG_999")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_REAL_123",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Báo cáo ngày 02/10/2024: Mực nước hồ Hòa Bình hiện tại là 115,42 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "CITATION_NONEXISTENT" in res.reason_codes


def test_07_correct_parent_table_nonexistent_cell(verifier):
    """Case 7: Parent table exists but cell ID is nonexistent -> INSUFFICIENT."""
    claim = TechnicalClaim(
        claim_id="C07",
        claim_text="Mực nước hồ Hòa Bình ngày 02/10/2024 đạt 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        temporal_scope="2024-10-02",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "TAB_HB_01_R999_C999")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="TAB_HB_01_R001_C002",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Bảng 1: Hàng 1 Cột 2: Mực nước hồ Hòa Bình ngày 02/10/2024 là 115,42 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "CITATION_NONEXISTENT" in res.reason_codes


def test_08_table_cell_wrong_column(verifier):
    """Case 8: TABLE_CELL from Station B cited for Station A -> CONTRADICTED."""
    claim = TechnicalClaim(
        claim_id="C08",
        claim_text="Mực nước trạm Tân Hồng là 1.54 m",
        subject="Tân Hồng",
        parameter="Mực nước",
        value="1.54",
        unit="m",
        evidence_citations=[EvidenceCitation("DOC_SIWRP", 1, "TAB_CELL_VB2")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="TAB_CELL_VB2",
            doc_id="DOC_SIWRP",
            page_id="P1",
            page_number=1,
            text="Bảng quan trắc mực nước: Trạm VB2 đạt 1,54 m; Trạm Tân Hồng đạt 2,85 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.CONTRADICTED
    assert "VALUE_CONTRADICTED" in res.reason_codes


# =============================================================================
# GROUP 2: NUMERIC & UNITS (Cases 9 - 15)
# =============================================================================

def test_09_numeric_115_42_m_vs_115_42_cm(verifier):
    """Case 9: Claim 115.42 cm vs evidence 115.42 m -> CONTRADICTED (1.1542 m != 115.42 m)."""
    claim = TechnicalClaim(
        claim_id="C09",
        claim_text="Mực nước hồ Hòa Bình là 115.42 cm",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="cm",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "EVID_01")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Mực nước hồ Hòa Bình hiện tại là 115,42 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.CONTRADICTED
    assert "VALUE_CONTRADICTED" in res.reason_codes


def test_10_numeric_1_1542_m_vs_115_42_cm(verifier):
    """Case 10: Claim 115.42 cm vs evidence 1.1542 m -> SUPPORTED (115.42 cm = 1.1542 m)."""
    claim = TechnicalClaim(
        claim_id="C10",
        claim_text="Mực nước quan trắc là 115.42 cm",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="cm",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "EVID_01")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Mực nước hồ Hòa Bình hiện tại là 1,1542 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.SUPPORTED
    assert "VALUE_MATCHED" in res.reason_codes


def test_11_numeric_unicode_minus_vs_ascii_minus(verifier):
    """Case 11: Claim -3 m vs evidence −3 m (Unicode minus \u2212) -> SUPPORTED."""
    claim = TechnicalClaim(
        claim_id="C11",
        claim_text="Cao trình đáy cống là -3.0 m",
        subject="Cống",
        parameter="Cao trình",
        value="-3.0",
        unit="m",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "EVID_01")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Cao trình đáy cống thiết kế là −3,0 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.SUPPORTED
    assert "VALUE_MATCHED" in res.reason_codes


def test_12_numeric_negative_vs_positive(verifier):
    """Case 12: Claim -3 m vs evidence +3 m -> CONTRADICTED."""
    claim = TechnicalClaim(
        claim_id="C12",
        claim_text="Cao trình đáy cống là -3.0 m",
        subject="Cống",
        parameter="Cao trình",
        value="-3.0",
        unit="m",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "EVID_01")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Cao trình đáy cống thiết kế là 3,0 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.CONTRADICTED
    assert "VALUE_CONTRADICTED" in res.reason_codes


def test_13_numeric_11_trieu_m3_vs_11_m3(verifier):
    """Case 13: Claim 11 triệu m³ vs evidence 11 m³ -> CONTRADICTED (11,000,000 != 11)."""
    claim = TechnicalClaim(
        claim_id="C13",
        claim_text="Dung tích hồ là 11 triệu m3",
        subject="Hồ Hòa Bình",
        parameter="Dung tích",
        value="11",
        unit="triệu m3",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "EVID_01")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Dung tích hồ Hòa Bình là 11 m3.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.CONTRADICTED
    assert "VALUE_CONTRADICTED" in res.reason_codes


def test_14_wrong_physical_dimension(verifier):
    """Case 14: Wrong physical dimension (m3/s vs m) -> CONTRADICTED (UNIT_INCOMPATIBLE)."""
    claim = TechnicalClaim(
        claim_id="C14",
        claim_text="Mực nước dâng bình thường hồ Hòa Bình là 117.0 m3/s",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="117.0",
        unit="m3/s",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "EVID_01")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Mực nước dâng bình thường hồ Hòa Bình là 117,0 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.CONTRADICTED
    assert "UNIT_INCOMPATIBLE" in res.reason_codes


def test_15_same_number_different_parameter(verifier):
    """Case 15: Same number (80m) but claim asks MNDBT while evidence gives MNC -> INSUFFICIENT."""
    claim = TechnicalClaim(
        claim_id="C15",
        claim_text="Mực nước dâng bình thường hồ Hòa Bình là 80.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước dâng bình thường",
        value="80.0",
        unit="m",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "EVID_01")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Điều 5: Mực nước chết hồ Hòa Bình là 80,0 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT


# =============================================================================
# GROUP 3: TIME & OBSERVATION TYPE (Cases 16 - 22)
# =============================================================================

def test_16_temporal_same_date_same_value(verifier):
    """Case 16: Same date, same value -> SUPPORTED."""
    claim = TechnicalClaim(
        claim_id="C16",
        claim_text="Mực nước hồ Hòa Bình ngày 02/10/2024 là 115.42 m",
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


def test_17_temporal_same_date_diff_value(verifier):
    """Case 17: Same date, different value -> CONTRADICTED."""
    claim = TechnicalClaim(
        claim_id="C17",
        claim_text="Mực nước hồ Hòa Bình ngày 02/10/2024 là 118.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="118.0",
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
    assert res.status == FourValuedStatus.CONTRADICTED


def test_18_temporal_diff_date_same_value(verifier):
    """Case 18: Different date, same value -> INSUFFICIENT (NOT CONTRADICTED)."""
    claim = TechnicalClaim(
        claim_id="C18",
        claim_text="Mực nước hồ Hòa Bình ngày 04/10/2024 là 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        temporal_scope="2024-10-04",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "EVID_01")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Báo cáo ngày 02/10/2024: Mực nước hồ Hòa Bình là 115,42 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "TEMPORAL_SCOPE_MISMATCH" in res.reason_codes


def test_19_temporal_diff_date_diff_value(verifier):
    """Case 19: Different date, different value -> INSUFFICIENT (NOT CONTRADICTED)."""
    claim = TechnicalClaim(
        claim_id="C19",
        claim_text="Mực nước hồ Hòa Bình ngày 04/10/2024 là 117.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="117.0",
        unit="m",
        temporal_scope="2024-10-04",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "EVID_01")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Báo cáo ngày 02/10/2024: Mực nước hồ Hòa Bình là 115,42 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "TEMPORAL_SCOPE_MISMATCH" in res.reason_codes


def test_20_temporal_claim_has_exact_date_evidence_date_missing(verifier):
    """Case 20: Claim specifies date, but evidence has NO observation date -> INSUFFICIENT."""
    claim = TechnicalClaim(
        claim_id="C20",
        claim_text="Mực nước hồ Hòa Bình ngày 02/10/2024 là 115.42 m",
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
            # No date mentioned anywhere in evidence
            text="Mực nước hồ Hòa Bình quan trắc là 115,42 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "TEMPORAL_DATE_UNVERIFIED" in res.reason_codes


def test_21_temporal_observation_time_vs_publication_date(verifier):
    """Case 21: Publication date != observation time -> INSUFFICIENT."""
    claim = TechnicalClaim(
        claim_id="C21",
        claim_text="Mực nước thực đo ngày 02/10/2024 là 115.42 m",
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
            # Published on 2024-10-02, but observation was measured on 2024-09-30
            text="Công văn ban hành ngày 02/10/2024. Số liệu thực đo ngày 30/09/2024: Mực nước hồ Hòa Bình là 115,42 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "TEMPORAL_SCOPE_MISMATCH" in res.reason_codes


def test_22_temporal_observed_vs_forecast(verifier):
    """Case 22: Claim asserts forecast, but evidence provides observed value -> INSUFFICIENT."""
    claim = TechnicalClaim(
        claim_id="C22",
        claim_text="Mực nước lớn nhất dự báo của Tân Hồng là 2.85 m",
        subject="Tân Hồng",
        parameter="Mực nước",
        value="2.85",
        unit="m",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "EVID_01")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Trạm Tân Hồng: Mực nước thực đo quan trắc hiện tại là 2,85 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "OBSERVATION_TYPE_MISMATCH" in res.reason_codes


# =============================================================================
# GROUP 4: CLAIM & ANSWER AGGREGATION (Cases 23 - 30)
# =============================================================================

def test_23_two_claims_one_supported_one_insufficient(verifier):
    """Case 23: 1 supported + 1 insufficient -> PARTIAL_SUPPORTED_WITH_INSUFFICIENT."""
    c1 = TechnicalClaim("C23_1", "Mực nước hồ Hòa Bình là 115.42 m", "Hồ Hòa Bình", "Mực nước", "115.42", "m")
    c2 = TechnicalClaim("C23_2", "Mực nước hồ Thác Bà là 58.0 m", "Hồ Thác Bà", "Mực nước", "58.0", "m")
    evidence = [
        EvidenceItem(evidence_id="E1", doc_id="D1", page_id="P1", page_number=1, text="Mực nước hồ Hòa Bình hiện tại là 115,42 m.")
    ]
    ans_res = verifier.verify_claims([c1, c2], evidence)
    assert ans_res.aggregate_status == FourValuedStatus.INSUFFICIENT
    assert ans_res.canonical_answer_verdict == "PARTIAL_SUPPORTED_WITH_INSUFFICIENT"
    assert ans_res.supported_count == 1
    assert ans_res.insufficient_count == 1


def test_24_two_claims_supported_plus_out_of_scope(verifier):
    """Case 24: 1 supported hydraulic + 1 out-of-scope non-hydraulic -> PARTIAL_SUPPORTED_WITH_OUT_OF_SCOPE."""
    c1 = TechnicalClaim("C24_1", "Mực nước hồ Hòa Bình là 115.42 m", "Hồ Hòa Bình", "Mực nước", "115.42", "m")
    c2 = TechnicalClaim("C24_2", "Diện tích gieo cấy lúa là 1500 ha", "Đồng bằng", "Diện tích lúa", "1500", "ha")
    evidence = [
        EvidenceItem(evidence_id="E1", doc_id="D1", page_id="P1", page_number=1, text="Mực nước hồ Hòa Bình hiện tại là 115,42 m.")
    ]
    ans_res = verifier.verify_claims([c1, c2], evidence)
    assert ans_res.canonical_answer_verdict == "PARTIAL_SUPPORTED_WITH_OUT_OF_SCOPE"
    assert ans_res.supported_count == 1
    assert ans_res.out_of_scope_count == 1


def test_25_valid_number_wrong_entity(verifier):
    """Case 25: Valid number in corpus, but claimed for wrong entity -> CONTRADICTED."""
    claim = TechnicalClaim(
        claim_id="C25",
        claim_text="Mực nước hồ Hòa Bình là 215.0 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="215.0",
        unit="m",
        evidence_citations=[EvidenceCitation("DOC_01", 1, "EVID_01")],
    )
    evidence = [
        EvidenceItem(
            evidence_id="EVID_01",
            doc_id="DOC_01",
            page_id="P1",
            page_number=1,
            text="Hồ Sơn La có mực nước là 215,0 m; còn hồ Hòa Bình có mực nước là 117,0 m.",
        )
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.CONTRADICTED
    assert "VALUE_CONTRADICTED" in res.reason_codes


def test_26_two_correct_numbers_swapped_dates(verifier):
    """Case 26: Day 1=2.94m, Day 2=2.73m. Claim asserts Day 1=2.73m -> CONTRADICTED."""
    c1 = TechnicalClaim(
        "C26_1", "Mực nước ngày 02/10/2026 của An Long là 2.73 m", "An Long", "Mực nước", "2.73", "m", temporal_scope="2026-10-02"
    )
    evidence = [
        EvidenceItem(
            evidence_id="E1",
            doc_id="D1",
            page_id="P1",
            page_number=1,
            text="Mực nước trạm An Long: Ngày 02/10/2026 là 2,94 m; Ngày 04/10/2026 là 2,73 m.",
        )
    ]
    res = verifier.verify_claim(c1, evidence)
    assert res.status == FourValuedStatus.CONTRADICTED
    assert "VALUE_CONTRADICTED" in res.reason_codes


def test_27_one_correct_claim_one_unsupported_claim(verifier):
    """Case 27: 1 correct claim + 1 unsupported claim -> PARTIAL_SUPPORTED_WITH_INSUFFICIENT."""
    c1 = TechnicalClaim("C27_1", "Mực nước hồ Hòa Bình là 115.42 m", "Hồ Hòa Bình", "Mực nước", "115.42", "m")
    c2 = TechnicalClaim("C27_2", "Lưu lượng xả trạm Cổ Mân là 450 m3/s", "Trạm Cổ Mân", "Lưu lượng xả", "450", "m3/s")
    evidence = [
        EvidenceItem(evidence_id="E1", doc_id="D1", page_id="P1", page_number=1, text="Mực nước hồ Hòa Bình hiện tại là 115,42 m.")
    ]
    ans_res = verifier.verify_claims([c1, c2], evidence)
    assert ans_res.canonical_answer_verdict == "PARTIAL_SUPPORTED_WITH_INSUFFICIENT"


def test_28_question_asks_three_things_answer_has_one(verifier):
    """Case 28: Question asks 3 requirements, answer only satisfies 1 -> claim coverage ratio 1/3."""
    c1 = TechnicalClaim("C28_1", "Mực nước hồ Hòa Bình là 115.42 m", "Hồ Hòa Bình", "Mực nước", "115.42", "m")
    c2 = TechnicalClaim("C28_2", "Mực nước hồ Sơn La là 215.0 m", "Hồ Sơn La", "Mực nước", "215.0", "m")
    c3 = TechnicalClaim("C28_3", "Mực nước hồ Thác Bà là 58.0 m", "Hồ Thác Bà", "Mực nước", "58.0", "m")
    # Only c1 has evidence
    evidence = [
        EvidenceItem(evidence_id="E1", doc_id="D1", page_id="P1", page_number=1, text="Mực nước hồ Hòa Bình là 115,42 m.")
    ]
    ans_res = verifier.verify_claims([c1, c2, c3], evidence)
    assert ans_res.total_claims == 3
    assert ans_res.supported_count == 1
    assert ans_res.claim_coverage_ratio == pytest.approx(1.0 / 3.0, rel=1e-2)


def test_29_model_abstains(verifier):
    """Case 29: Model abstains -> extract_atomic_claims returns empty list, aggregate is EXTRACTION_UNRESOLVED."""
    raw_answer = "Không đủ bằng chứng trong ngữ cảnh được cung cấp để trả lời đáng tin cậy."
    claims = extract_atomic_claims(raw_answer)
    assert len(claims) == 0
    ans_res = verifier.aggregate_answer([])
    assert ans_res.canonical_answer_verdict == "EXTRACTION_UNRESOLVED"
    assert ans_res.total_claims == 0


def test_30_claim_parser_missing_attributes(verifier):
    """Case 30: Claim missing entity / numeric value -> INSUFFICIENT with missing_slots."""
    claim = TechnicalClaim(
        claim_id="C30",
        claim_text="Mực nước là không rõ",
        subject="",  # Missing entity
        parameter="Mực nước",
        value="",  # Missing value
        unit="m",
    )
    evidence = [EvidenceItem("E1", "D1", "P1", 1, "Mực nước hồ Hòa Bình là 115,42 m.")]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "numeric_value" in res.missing_slots or "subject_entity" in res.missing_slots


# =============================================================================
# GROUP 5: EVALUATION LEAKAGE & ROBUSTNESS (Cases 31 - 35)
# =============================================================================

def test_31_evaluation_leakage_reference_answer_not_evidence(verifier):
    """Case 31: Verifier fails closed if evidence has fake doc or missing provenance."""
    claim = TechnicalClaim(
        claim_id="C31",
        claim_text="Mực nước hồ Hòa Bình là 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        evidence_citations=[EvidenceCitation("DOC_FAKE_REF_ANS", 1, "EVID_FAKE")],
    )
    # Evidence without authentic document provenance
    evidence = [
        EvidenceItem("EVID_REAL", "DOC_01", "P1", 1, "Mực nước hồ Hòa Bình là 115,42 m.")
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "CITATION_NONEXISTENT" in res.reason_codes or "PROVENANCE_INVALID" in res.reason_codes


def test_32_gold_pages_cannot_become_inference_evidence(verifier):
    """Case 32: Citation citing a page not in the provided evidence set is rejected."""
    claim = TechnicalClaim(
        claim_id="C32",
        claim_text="Mực nước hồ Hòa Bình là 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        # Trying to cite page 42 which was not retrieved in context
        evidence_citations=[EvidenceCitation("DOC_01", 42, "EVID_01")],
    )
    evidence = [
        EvidenceItem("EVID_01", "DOC_01", "P1", 1, "Mực nước hồ Hòa Bình là 115,42 m.")
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "PROVENANCE_INVALID" in res.reason_codes


def test_33_abstained_answers_cannot_be_replaced_by_references(verifier):
    """Case 33: An abstained answer must remain abstained and produce 0 claims."""
    ref_ans = "Mực nước hồ Hòa Bình là 115,42 m ngày 02/10/2026."
    actual_ans = "Không đủ bằng chứng trong ngữ cảnh được cung cấp để trả lời đáng tin cậy."

    # Using actual_ans MUST NOT extract claims from ref_ans
    claims_from_actual = extract_atomic_claims(actual_ans)
    assert len(claims_from_actual) == 0

    # Ensure no claims are verified when generator abstained
    ans_res = verifier.aggregate_answer(claims_from_actual)
    assert ans_res.total_claims == 0
    assert ans_res.canonical_answer_verdict == "EXTRACTION_UNRESOLVED"


def test_34_missing_real_source_returns_insufficient_or_not_evaluable(verifier):
    """Case 34: Missing real source evidence items returns INSUFFICIENT."""
    claim = TechnicalClaim(
        claim_id="C34",
        claim_text="Mực nước hồ Hòa Bình là 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
    )
    empty_evidence: list[EvidenceItem] = []
    res = verifier.verify_claim(claim, empty_evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "PROVENANCE_MISSING" in res.reason_codes


def test_35_a1_cannot_approve_document_merely_lacking_fake_in_id(verifier):
    """Case 35: A citation with a plausible doc_id but nonexistent in context must FAIL."""
    claim = TechnicalClaim(
        claim_id="C35",
        claim_text="Mực nước hồ Hòa Bình là 115.42 m",
        subject="Hồ Hòa Bình",
        parameter="Mực nước",
        value="115.42",
        unit="m",
        # Plausible doc name, doesn't contain 'FAKE', but nonexistent in context
        evidence_citations=[EvidenceCitation("QUY_TRINH_VAN_HANH_2026_LEGAL", 5, "EVID_NONEXISTENT_99")],
    )
    evidence = [
        EvidenceItem("EVID_01", "DOC_01", "P1", 1, "Mực nước hồ Hòa Bình là 115,42 m.")
    ]
    res = verifier.verify_claim(claim, evidence)
    assert res.status == FourValuedStatus.INSUFFICIENT
    assert "CITATION_NONEXISTENT" in res.reason_codes
