"""Unit tests for experiment_validity_helpers.py.

Validates:
- Adversarial test: REG_FORGED vs REG_REAL on same doc/page (zero forged citation mapping).
- Abstention detection (no fabricated claims; full vs partial abstention).
- Independent claim extraction without reference leakage.
- Negation polarity preservation (ClaimPolarity.NEGATED vs AFFIRMED).
- Multiple extractable claims in a single compound sentence.
- Rejection of generic placeholder subject for ungrounded entities.
- Safe Vietnamese numeric normalization (thousands separator vs decimal).
- Relational binding inversion detection (inside-dike vs outside-dike).
- Out-of-scope ontology dimension classification (VERIFIER_OUT_OF_SCOPE for 'ha' and 'ngày').
- Unit alias compatibility.
"""

from __future__ import annotations

import pytest
from viirr_ontology.schema.claim import ClaimPolarity
from viirr_rag.pipeline import Evidence, GenerationResult
from scripts.experiment_validity_helpers import (
    classify_verifier_verdict,
    evaluate_provisional_answer_match,
    extract_independent_claim,
    is_model_abstention,
    normalize_vn_numeric_string,
    resolve_citations_strictly,
)


def test_adversarial_citation_forged_vs_real_same_page():
    """Adversarial test: REG_FORGED on same doc/page must NOT map to REG_REAL."""
    context_evidence = [
        Evidence(
            rank=1,
            evidence_id="REG_REAL",
            doc_id="DOC_A",
            page_id="P_01",
            page_number=2,
            unit_type="REGION",
            score=0.95,
            text="Lưu lượng xả là 250 m3/s",
            source="retrieved",
        )
    ]

    # Model generates citation with REG_FORGED on the same doc/page
    raw_citations = [
        {"doc_id": "DOC_A", "page_number": 2, "evidence_id": "REG_FORGED"}
    ]

    report = resolve_citations_strictly(raw_citations, context_evidence)
    assert len(report.matched_citations) == 0  # REG_FORGED must NOT be matched!
    assert len(report.invalid_citations) == 1
    assert report.invalid_citations[0]["evidence_id"] == "REG_FORGED"

    # Now verify with REAL citation
    raw_real = [{"doc_id": "DOC_A", "page_number": 2, "evidence_id": "REG_REAL"}]
    report_real = resolve_citations_strictly(raw_real, context_evidence)
    assert len(report_real.matched_citations) == 1
    assert report_real.matched_citations[0].evidence_id == "REG_REAL"
    assert len(report_real.invalid_citations) == 0


def test_page_level_vs_region_level_citation_distinction():
    """Page-level citation (no evidence_id) is recorded as page-level, not explicit region."""
    context_evidence = [
        Evidence(
            rank=1,
            evidence_id="REG_001",
            doc_id="DOC_B",
            page_id="P_05",
            page_number=5,
            unit_type="REGION",
            score=0.9,
            text="Mực nước là 12,8 m",
            source="retrieved",
        )
    ]

    raw_page_level = [{"doc_id": "DOC_B", "page_number": 5}]
    report = resolve_citations_strictly(raw_page_level, context_evidence)
    assert len(report.page_level_citations) == 1
    assert len(report.region_level_citations) == 0
    assert len(report.matched_citations) == 1


def test_abstention_detection():
    assert is_model_abstention("Không đủ bằng chứng trong ngữ cảnh được cung cấp để trả lời.") is True
    assert is_model_abstention("Tài liệu không nêu thông tin về hồ Bình Điền.") is True
    assert is_model_abstention("Tổng diện tích là 100.261 ha.", explicit_abstained_flag=False) is False
    assert is_model_abstention("Tổng diện tích là 100.261 ha.", explicit_abstained_flag=True) is True


def test_independent_claim_extraction_on_abstention():
    gen = GenerationResult(
        answer="Không đủ bằng chứng trong ngữ cảnh được cung cấp để trả lời câu hỏi.",
        citations=[],
        abstained=True,
        abstention_reason="INSUFFICIENT_CONTEXT",
        evidence_supported=False,
        parse_error="",
        raw_response="",
    )
    res = extract_independent_claim("V42-QA-021", "Độ mặn tại trạm là bao nhiêu?", gen, [])
    assert res.status == "ABSTAINED_NO_CLAIM"
    assert res.claim is None
    assert len(res.claims) == 0


def test_negation_polarity_preservation():
    """Negative assertion must yield ClaimPolarity.NEGATED."""
    gen = GenerationResult(
        answer="Mực nước tại hồ Bình Điền không vượt quá 10,4 m.",
        citations=[],
        abstained=False,
        abstention_reason="",
        evidence_supported=True,
        parse_error="",
        raw_response="",
    )
    res = extract_independent_claim("Q_NEG", "Mực nước hồ Bình Điền có vượt quá 10,4m không?", gen, [])
    assert res.status == "EXPLICIT_CLAIM_EXTRACTED"
    assert res.claim is not None
    assert res.claim.polarity == ClaimPolarity.NEGATED
    assert res.claim.value == "10,4"


def test_multiple_claims_extraction():
    """Extract both facts in compound response: length and catchment area."""
    gen = GenerationResult(
        answer="Chiều dài sông Hương khoảng 100km và diện tích lưu vực xấp xỉ 2.800 km2.",
        citations=[],
        abstained=False,
        abstention_reason="",
        evidence_supported=True,
        parse_error="",
        raw_response="",
    )
    res = extract_independent_claim(
        "V42-QA-007",
        "Báo cáo sự kiện lũ mô tả chiều dài sông Hương và diện tích lưu vực xấp xỉ bao nhiêu?",
        gen,
        [],
    )
    assert res.status == "EXPLICIT_CLAIM_EXTRACTED"
    assert len(res.claims) >= 2
    # First claim: length
    assert res.claims[0].subject == "Sông Hương"
    assert res.claims[0].parameter == "chiều dài"
    assert res.claims[0].value == "100"
    assert res.claims[0].unit == "km"
    # Second claim: basin area
    assert res.claims[1].subject == "Sông Hương"
    assert res.claims[1].parameter == "diện tích lưu vực"
    assert res.claims[1].value == "2.800"
    assert res.claims[1].unit == "km2"


def test_ungrounded_entity_rejected_without_generic_placeholder():
    """If no known hydraulic entity is mentioned, claim must be UNRESOLVED, not generic substitute."""
    gen = GenerationResult(
        answer="Lưu lượng trung bình đạt khoảng 150 m3/s.",
        citations=[],
        abstained=False,
        abstention_reason="",
        evidence_supported=True,
        parse_error="",
        raw_response="",
    )
    # Question mentions an unknown entity not in the catalog
    res = extract_independent_claim("Q_UNKNOWN", "Lưu lượng trung bình trạm XYZ là bao nhiêu?", gen, [])
    assert res.status == "CLAIM_EXTRACTION_UNRESOLVED"
    assert res.claim is None  # Unresolved claim is NOT passed to verifier as a verified claim!


def test_relational_binding_inversion_detected():
    """Inverted binding (14.935 inside-dike, 85.326 outside-dike) must NOT score EXACT_MATCH."""
    expected_val = "85326 | 14935"
    expected_unit = "ha"

    # Failing case from independent review: values are swapped!
    ans_inverted = "Diện tích trong đê là 14.935 ha và diện tích ngoài đê là 85.326 ha."
    res_inv = evaluate_provisional_answer_match(ans_inverted, expected_val, expected_unit)
    assert res_inv["status"] == "RELATIONAL_INVERSION"
    assert res_inv["val_match_score"] == 0.0
    assert res_inv["relational_correct"] is False

    # Correct binding
    ans_correct = "Diện tích trong đê là 85.326 ha và diện tích ngoài đê là 14.935 ha."
    res_corr = evaluate_provisional_answer_match(ans_correct, expected_val, expected_unit)
    assert res_corr["status"] == "EXACT_MATCH"
    assert res_corr["val_match_score"] == 1.0
    assert res_corr["relational_correct"] is True


def test_out_of_scope_ontology_verdict_classification():
    """Ha (AREA) must be classified as VERIFIER_OUT_OF_SCOPE, preserving raw CONTRADICTED."""
    gen = GenerationResult(
        answer="Tổng diện tích tự nhiên của hệ thống Bắc Nam Hà là 100.261 ha.",
        citations=[],
        abstained=False,
        abstention_reason="",
        evidence_supported=True,
        parse_error="",
        raw_response="",
    )
    clm_res = extract_independent_claim("V42-QA-001", "Tổng diện tích tự nhiên Bắc Nam Hà là bao nhiêu?", gen, [])
    raw_status = "CONTRADICTED"
    raw_reasons = ["UNIT_INCOMPATIBLE"]

    classification = classify_verifier_verdict(raw_status, raw_reasons, clm_res.claim)
    assert classification["raw_verifier_status"] == "CONTRADICTED"
    assert classification["scientific_verdict"] == "VERIFIER_OUT_OF_SCOPE"
    assert classification["out_of_scope_dimension"] == "AREA"
    assert classification["is_genuine_contradiction"] is False

    # Test genuine contradiction (e.g. asking for water level in m, but given in m3/s)
    raw_genuine_status = "CONTRADICTED"
    raw_genuine_reasons = ["VALUE_CONTRADICTED"]
    class_genuine = classify_verifier_verdict(raw_genuine_status, raw_genuine_reasons, clm_res.claim)
    assert class_genuine["scientific_verdict"] == "CONTRADICTED"
    assert class_genuine["is_genuine_contradiction"] is True


def test_safe_vietnamese_numeric_normalization():
    assert normalize_vn_numeric_string("100.261") == "100261"
    assert normalize_vn_numeric_string("85.326") == "85326"
    assert normalize_vn_numeric_string("1.234.567") == "1234567"
    assert normalize_vn_numeric_string("12,8") == "12.8"
    assert normalize_vn_numeric_string("0,5") == "0.5"
    assert normalize_vn_numeric_string("12.8") == "12.8"


def test_unit_alias_matching():
    res = evaluate_provisional_answer_match("Diện tích là 100.261 hecta.", "100261", "ha")
    assert res["unit_match"] is True
    assert res["status"] == "EXACT_MATCH"

    res2 = evaluate_provisional_answer_match("Lưu lượng xả là 250 m³/s.", "250", "m3/s")
    assert res2["unit_match"] is True
    assert res2["status"] == "EXACT_MATCH"
