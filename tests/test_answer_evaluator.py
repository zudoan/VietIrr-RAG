"""Unit tests for Phase 4 & 5 Evaluator (Factual Support, Citation Validity, and Question Requirement Completeness).

Mandatory tests from Specification Section 10:
1. Một câu hỏi yêu cầu hai số, đáp án chỉ có một.
2. Một câu hỏi yêu cầu hai ngày, đáp án đảo hai giá trị.
3. Một câu hỏi yêu cầu số liệu và giải thích, đáp án chỉ có số liệu.
4. Một câu hỏi yêu cầu so sánh, đáp án chỉ nêu giá trị.
5. Một answer trả lời đầy đủ nhưng có extra unsupported claim (MUST NOT BE CORRECT_COMPLETE).
6. Một answer có tất cả claims đúng và đủ requirements (CORRECT_COMPLETE).
7. Qwen abstain (ABSTAINED).
8. Question requirement extraction uncertain (fallback general requirement).
"""

import pytest
from viirr_ontology.answer_evaluator import (
    AnswerEvaluator,
    OverallEvaluationStatus,
    QuestionRequirementExtractor,
    RequirementStatus,
)
from viirr_ontology.schema.claim import TechnicalClaim
from viirr_ontology.shadow_verifier import FourValuedStatus, ShadowClaimVerificationResult


def make_dummy_claim(
    claim_id: str,
    raw_statement: str,
    entity: str = "TRAM_AN_LONG",
    param: str = "MUC_NUOC",
    val: float = 2.94,
    date_iso: str = "2026-10-02",
) -> TechnicalClaim:
    return TechnicalClaim(
        claim_id=claim_id,
        claim_text=raw_statement,
        subject=entity,
        parameter=param,
        value=str(val),
        unit="m",
        temporal_scope=date_iso,
    )


def make_dummy_res(
    claim_id: str,
    status: FourValuedStatus,
    cit_validity: str = "VALID",
) -> ShadowClaimVerificationResult:
    return ShadowClaimVerificationResult(
        claim_id=claim_id,
        status=status,
        reason_codes=[],
        factual_support="SUPPORTED" if status == FourValuedStatus.SUPPORTED else "CONTRADICTED" if status == FourValuedStatus.CONTRADICTED else "INSUFFICIENT",
        citation_validity=cit_validity,
    )


def test_01_two_numbers_required_only_one_provided():
    """1. Một câu hỏi yêu cầu hai số, đáp án chỉ có một -> CORRECT_PARTIAL, not COMPLETE."""
    q = "Mực nước trạm An Long vào ngày 02/10/2026 và ngày 04/10/2026 là bao nhiêu?"
    ans = "Mực nước An Long vào ngày 02/10/2026 là 2,94 m."
    c1 = make_dummy_claim("c1", "Mực nước An Long ngày 02/10/2026 là 2,94 m", "TRAM_AN_LONG", "MUC_NUOC", 2.94, "2026-10-02")
    r1 = make_dummy_res("c1", FourValuedStatus.SUPPORTED)

    report = AnswerEvaluator.evaluate(q, ans, [c1], [r1], abstained=False)
    assert report.total_requirements == 2
    assert report.satisfied_requirements == 1
    assert report.question_requirement_coverage == 0.5
    assert report.claim_support_coverage == 1.0  # 1/1 claims supported
    assert report.overall_status == OverallEvaluationStatus.CORRECT_PARTIAL
    assert report.overall_status != OverallEvaluationStatus.CORRECT_COMPLETE


def test_02_two_dates_required_values_swapped():
    """2. Một câu hỏi yêu cầu hai ngày, đáp án đảo hai giá trị -> CONTRADICTED or NOT_SATISFIED."""
    q = "Mực nước trạm An Long vào ngày 02/10/2026 và ngày 04/10/2026 là bao nhiêu?"
    ans = "Mực nước An Long ngày 02/10/2026 là 2,73 m và ngày 04/10/2026 là 2,94 m."
    # Both claims contradict source evidence
    c1 = make_dummy_claim("c1", "Mực nước An Long ngày 02/10/2026 là 2,73 m", "TRAM_AN_LONG", "MUC_NUOC", 2.73, "2026-10-02")
    c2 = make_dummy_claim("c2", "Mực nước An Long ngày 04/10/2026 là 2,94 m", "TRAM_AN_LONG", "MUC_NUOC", 2.94, "2026-10-04")
    r1 = make_dummy_res("c1", FourValuedStatus.CONTRADICTED)
    r2 = make_dummy_res("c2", FourValuedStatus.CONTRADICTED)

    report = AnswerEvaluator.evaluate(q, ans, [c1, c2], [r1, r2], abstained=False)
    assert report.total_requirements == 2
    assert report.satisfied_requirements == 0
    assert report.contradicted_claims == 2
    assert report.overall_status == OverallEvaluationStatus.CONTRADICTED


def test_03_numeric_and_explanation_required_only_numeric_provided():
    """3. Một câu hỏi yêu cầu số liệu và giải thích, đáp án chỉ có số liệu -> CORRECT_PARTIAL."""
    q = "Mực nước trạm An Long ngày 02/10/2026 là bao nhiêu và giải thích nguyên nhân biến đổi?"
    ans = "Mực nước An Long ngày 02/10/2026 là 2,94 m."
    c1 = make_dummy_claim("c1", "Mực nước An Long ngày 02/10/2026 là 2,94 m", "TRAM_AN_LONG", "MUC_NUOC", 2.94, "2026-10-02")
    r1 = make_dummy_res("c1", FourValuedStatus.SUPPORTED)

    report = AnswerEvaluator.evaluate(q, ans, [c1], [r1], abstained=False)
    assert any(r.req_type == "EXPLANATION" for r in report.requirements)
    assert report.overall_status == OverallEvaluationStatus.CORRECT_PARTIAL


def test_04_comparison_required_only_values_provided():
    """4. Một câu hỏi yêu cầu so sánh, đáp án chỉ nêu giá trị -> has comparison requirement."""
    q = "So sánh mực nước trạm An Long giữa ngày 02/10/2026 và ngày 04/10/2026?"
    ans = "Mực nước ngày 02/10 là 2,94 m và ngày 04/10 là 2,73 m."
    c1 = make_dummy_claim("c1", "Mực nước 02/10 là 2,94 m", "TRAM_AN_LONG", "MUC_NUOC", 2.94, "2026-10-02")
    c2 = make_dummy_claim("c2", "Mực nước 04/10 là 2,73 m", "TRAM_AN_LONG", "MUC_NUOC", 2.73, "2026-10-04")
    r1 = make_dummy_res("c1", FourValuedStatus.SUPPORTED)
    r2 = make_dummy_res("c2", FourValuedStatus.SUPPORTED)

    report = AnswerEvaluator.evaluate(q, ans, [c1, c2], [r1, r2], abstained=False)
    assert any(r.req_type == "COMPARISON" for r in report.requirements)
    comp_req = [r for r in report.requirements if r.req_type == "COMPARISON"][0]
    assert comp_req.status != RequirementStatus.SATISFIED
    assert report.overall_status == OverallEvaluationStatus.CORRECT_PARTIAL


def test_05_complete_requirements_with_extra_unsupported_claim():
    """5. Một answer trả lời đầy đủ nhưng có extra unsupported claim -> MUST BE HAS_UNSUPPORTED_EXTRA, NOT COMPLETE."""
    q = "Mực nước trạm An Long vào ngày 02/10/2026 là bao nhiêu?"
    ans = "Mực nước trạm An Long ngày 02/10/2026 là 2,94 m. Lưu lượng xả Hồ Hòa Bình là 999 m3/s."
    c1 = make_dummy_claim("c1", "Mực nước An Long ngày 02/10/2026 là 2,94 m", "TRAM_AN_LONG", "MUC_NUOC", 2.94, "2026-10-02")
    c2 = make_dummy_claim("c2", "Lưu lượng xả Hồ Hòa Bình là 999 m3/s", "HO_HOA_BINH", "LUU_LUONG_XA", 999.0, "2026-10-02")
    r1 = make_dummy_res("c1", FourValuedStatus.SUPPORTED)
    r2 = make_dummy_res("c2", FourValuedStatus.INSUFFICIENT)  # Unsupported extra hallucination!

    report = AnswerEvaluator.evaluate(q, ans, [c1, c2], [r1, r2], abstained=False)
    assert report.satisfied_requirements == 1
    assert len(report.extra_unsupported_claims) == 1
    assert report.extra_unsupported_claims[0]["claim_id"] == "c2"
    assert report.overall_status == OverallEvaluationStatus.HAS_UNSUPPORTED_EXTRA
    assert report.overall_status != OverallEvaluationStatus.CORRECT_COMPLETE


def test_06_complete_requirements_and_all_claims_supported():
    """6. Một answer có tất cả claims đúng và đủ requirements -> CORRECT_COMPLETE."""
    q = "Mực nước trạm An Long vào ngày 02/10/2026 và ngày 04/10/2026 là bao nhiêu?"
    ans = "Mực nước An Long ngày 02/10/2026 là 2,94 m và ngày 04/10/2026 là 2,73 m."
    c1 = make_dummy_claim("c1", "Mực nước An Long ngày 02/10/2026 là 2,94 m", "TRAM_AN_LONG", "MUC_NUOC", 2.94, "2026-10-02")
    c2 = make_dummy_claim("c2", "Mực nước An Long ngày 04/10/2026 là 2,73 m", "TRAM_AN_LONG", "MUC_NUOC", 2.73, "2026-10-04")
    r1 = make_dummy_res("c1", FourValuedStatus.SUPPORTED)
    r2 = make_dummy_res("c2", FourValuedStatus.SUPPORTED)

    report = AnswerEvaluator.evaluate(q, ans, [c1, c2], [r1, r2], abstained=False)
    assert report.satisfied_requirements == 2
    assert report.question_requirement_coverage == 1.0
    assert report.claim_support_coverage == 1.0
    assert len(report.extra_unsupported_claims) == 0
    assert report.overall_status == OverallEvaluationStatus.CORRECT_COMPLETE


def test_07_qwen_abstain():
    """7. Qwen abstain -> ABSTAINED."""
    q = "Mực nước hồ A là bao nhiêu?"
    ans = "Không đủ bằng chứng trong ngữ cảnh được cung cấp để trả lời đáng tin cậy."
    report = AnswerEvaluator.evaluate(q, ans, [], [], abstained=True)
    assert report.overall_status == OverallEvaluationStatus.ABSTAINED
    assert report.claim_support_coverage == 1.0


def test_08_question_requirement_extraction_uncertain():
    """8. Question requirement extraction uncertain -> Fallback general requirement."""
    q = "Xin chào bạn có khỏe không?"
    reqs = QuestionRequirementExtractor.extract_requirements(q)
    assert len(reqs) == 1
    assert reqs[0].req_type == "GENERAL"


def test_09_missing_entity_in_claim_cannot_be_correct_complete():
    """Missing entity in claim: claim has value/unit/date/param but NO entity -> NOT_SATISFIED, cannot be CORRECT_COMPLETE."""
    q = "Mực nước thực đo tại trạm An Long ngày 02/10/2026 là bao nhiêu?"
    ans = "Mực nước ngày 02/10/2026 là 2,94 m."
    # Claim lacks subject entity
    c1 = make_dummy_claim("c1", "Mực nước ngày 02/10/2026 là 2,94 m", entity="", param="MUC_NUOC", val=2.94, date_iso="2026-10-02")
    r1 = make_dummy_res("c1", FourValuedStatus.SUPPORTED)

    report = AnswerEvaluator.evaluate(q, ans, [c1], [r1], abstained=False)
    assert report.total_requirements == 1
    assert report.requirements[0].status == RequirementStatus.NOT_SATISFIED
    assert report.satisfied_requirements == 0
    assert report.overall_status != OverallEvaluationStatus.CORRECT_COMPLETE
    assert report.overall_status == OverallEvaluationStatus.INSUFFICIENT_SUPPORT


def test_10_missing_date_in_claim_cannot_be_correct_complete():
    """Missing date in claim: question specifies date, claim lacks date -> NOT_SATISFIED."""
    q = "Mực nước trạm An Long vào ngày 02/10/2026 là bao nhiêu?"
    ans = "Mực nước trạm An Long là 2,94 m."
    # Claim lacks date
    c1 = TechnicalClaim(
        claim_id="c1",
        claim_text="Mực nước trạm An Long là 2,94 m",
        subject="TRAM_AN_LONG",
        parameter="MUC_NUOC",
        value="2.94",
        unit="m",
        temporal_scope=None,
    )
    r1 = make_dummy_res("c1", FourValuedStatus.SUPPORTED)

    report = AnswerEvaluator.evaluate(q, ans, [c1], [r1], abstained=False)
    assert report.total_requirements == 1
    assert report.requirements[0].status == RequirementStatus.NOT_SATISFIED
    assert report.satisfied_requirements == 0
    assert report.overall_status != OverallEvaluationStatus.CORRECT_COMPLETE


def test_11_missing_parameter_in_claim_cannot_be_correct_complete():
    """Missing parameter in claim: claim has entity and date but parameter is empty -> NOT_SATISFIED."""
    q = "Mực nước trạm An Long vào ngày 02/10/2026 là bao nhiêu?"
    ans = "Tại An Long ngày 02/10/2026 là 2,94 m."
    c1 = TechnicalClaim(
        claim_id="c1",
        claim_text="Tại An Long ngày 02/10/2026 là 2,94 m",
        subject="TRAM_AN_LONG",
        parameter="",
        value="2.94",
        unit="m",
        temporal_scope="2026-10-02",
    )
    r1 = make_dummy_res("c1", FourValuedStatus.SUPPORTED)

    report = AnswerEvaluator.evaluate(q, ans, [c1], [r1], abstained=False)
    assert report.total_requirements == 1
    assert report.requirements[0].status == RequirementStatus.NOT_SATISFIED
    assert report.satisfied_requirements == 0
    assert report.overall_status != OverallEvaluationStatus.CORRECT_COMPLETE


def test_12_wrong_observation_type_forecast_vs_observed():
    """Wrong observation type: question asks for actual observed, claim provides forecast -> NOT_SATISFIED."""
    q = "Mực nước thực đo tại trạm An Long ngày 02/10/2026 là bao nhiêu?"
    ans = "Mực nước dự báo trạm An Long ngày 02/10/2026 là 2,94 m."
    c1 = TechnicalClaim(
        claim_id="c1",
        claim_text="Mực nước dự báo trạm An Long ngày 02/10/2026 là 2,94 m",
        subject="TRAM_AN_LONG",
        parameter="MUC_NUOC",
        value="2.94",
        unit="m",
        temporal_scope="2026-10-02",
        observation_type="FORECAST_ESTIMATE",
    )
    r1 = make_dummy_res("c1", FourValuedStatus.SUPPORTED)

    report = AnswerEvaluator.evaluate(q, ans, [c1], [r1], abstained=False)
    assert report.total_requirements == 1
    assert report.requirements[0].target_obs_type == "ACTUAL_OBSERVED"
    assert report.requirements[0].status == RequirementStatus.NOT_SATISFIED
    assert report.overall_status != OverallEvaluationStatus.CORRECT_COMPLETE


def test_13_wrong_parameter_with_same_unit_canal_bed_vs_water_level():
    """Wrong parameter with same unit (m): canal bottom elevation (CAO_TRINH_DAY) must NOT match water level (MUC_NUOC)."""
    q = "Mực nước trạm An Long vào ngày 02/10/2026 là bao nhiêu?"
    ans = "Cao trình đáy trạm An Long ngày 02/10/2026 là -2,5 m."
    c1 = make_dummy_claim("c1", "Cao trình đáy trạm An Long ngày 02/10/2026 là -2,5 m", "TRAM_AN_LONG", "CAO_TRINH_DAY", -2.5, "2026-10-02")
    r1 = make_dummy_res("c1", FourValuedStatus.SUPPORTED)

    report = AnswerEvaluator.evaluate(q, ans, [c1], [r1], abstained=False)
    assert report.total_requirements == 1
    assert report.requirements[0].target_parameter == "MUC_NUOC"
    assert report.requirements[0].status == RequirementStatus.NOT_SATISFIED
    assert report.overall_status == OverallEvaluationStatus.INSUFFICIENT_SUPPORT
    assert report.overall_status != OverallEvaluationStatus.CORRECT_COMPLETE


def test_14_swapped_entity_values_contradicted():
    """Swapped entities and values: question asks for two structures, answer swaps their values -> CONTRADICTED."""
    q = "Cao trình đáy của cống Hàm Giang và cống Long Hiệp là bao nhiêu?"
    ans = "Cao trình đáy cống Hàm Giang là -2,0 m và cống Long Hiệp là -3,0 m."
    # Ground truth: Ham Giang is -3.0m, Long Hiep is -2.0m. Thus both statements contradict source evidence!
    c1 = make_dummy_claim("c1", "Cao trình đáy cống Hàm Giang là -2,0 m", "TRAM_HAM_GIANG", "CAO_TRINH_DAY", -2.0, "2026-10-01")
    c2 = make_dummy_claim("c2", "Cao trình đáy cống Long Hiệp là -3,0 m", "CONG_LONG_HIEP", "CAO_TRINH_DAY", -3.0, "2026-10-01")
    r1 = make_dummy_res("c1", FourValuedStatus.CONTRADICTED)
    r2 = make_dummy_res("c2", FourValuedStatus.CONTRADICTED)

    report = AnswerEvaluator.evaluate(q, ans, [c1, c2], [r1, r2], abstained=False)
    assert report.total_requirements == 2
    assert report.satisfied_requirements == 0
    assert report.contradicted_claims == 2
    assert report.overall_status == OverallEvaluationStatus.CONTRADICTED


def test_15_one_claim_reused_for_two_distinct_requirements_blocked():
    """A single claim cannot be reused to satisfy multiple distinct requirements."""
    q = "Mực nước trạm An Long vào ngày 02/10/2026 và ngày 04/10/2026 là bao nhiêu?"
    ans = "Mực nước An Long ngày 02/10/2026 là 2,94 m."
    # Only 1 claim provided
    c1 = make_dummy_claim("c1", "Mực nước An Long ngày 02/10/2026 là 2,94 m", "TRAM_AN_LONG", "MUC_NUOC", 2.94, "2026-10-02")
    r1 = make_dummy_res("c1", FourValuedStatus.SUPPORTED)

    report = AnswerEvaluator.evaluate(q, ans, [c1], [r1], abstained=False)
    assert report.total_requirements == 2
    # First requirement satisfied by c1, second requirement NOT_SATISFIED (c1 cannot be reused)
    assert report.requirements[0].status == RequirementStatus.SATISFIED
    assert report.requirements[1].status == RequirementStatus.NOT_SATISFIED
    assert report.satisfied_requirements == 1
    assert report.overall_status == OverallEvaluationStatus.CORRECT_PARTIAL


def test_16_same_day_month_different_year_must_not_match():
    """Different year: Question asks for 02/10/2026, claim gives 02/10/2025 -> MUST NOT MATCH!"""
    q = "Mực nước trạm An Long vào ngày 02/10/2026 là bao nhiêu?"
    ans = "Mực nước An Long ngày 02/10/2025 là 2,94 m."
    # Year is 2025, not 2026!
    c1 = make_dummy_claim("c1", "Mực nước An Long ngày 02/10/2025 là 2,94 m", "TRAM_AN_LONG", "MUC_NUOC", 2.94, "2025-10-02")
    r1 = make_dummy_res("c1", FourValuedStatus.SUPPORTED)

    report = AnswerEvaluator.evaluate(q, ans, [c1], [r1], abstained=False)
    assert report.total_requirements == 1
    assert report.requirements[0].target_date_iso == "2026-10-02"
    assert report.requirements[0].status == RequirementStatus.NOT_SATISFIED
    assert report.satisfied_requirements == 0
    assert report.overall_status != OverallEvaluationStatus.CORRECT_COMPLETE


def test_17_unknown_or_missing_observation_type_cannot_match_required_actual_obs():
    """Unknown observation type: question requires ACTUAL_OBSERVED, claim has observation_type='UNKNOWN' -> NOT_SATISFIED."""
    q = "Mực nước thực đo tại trạm An Long ngày 02/10/2026 là bao nhiêu?"
    ans = "Mực nước trạm An Long ngày 02/10/2026 là 2,94 m."
    # Observation type explicitly UNKNOWN and text gives no hint
    c1 = TechnicalClaim(
        claim_id="c1",
        claim_text="Mực nước trạm An Long ngày 02/10/2026 là 2,94 m",
        subject="TRAM_AN_LONG",
        parameter="MUC_NUOC",
        value="2.94",
        unit="m",
        temporal_scope="2026-10-02",
        observation_type="UNKNOWN",
    )
    r1 = make_dummy_res("c1", FourValuedStatus.SUPPORTED)

    report = AnswerEvaluator.evaluate(q, ans, [c1], [r1], abstained=False)
    assert report.total_requirements == 1
    assert report.requirements[0].target_obs_type == "ACTUAL_OBSERVED"
    assert report.requirements[0].status == RequirementStatus.NOT_SATISFIED
    assert report.satisfied_requirements == 0
    assert report.overall_status != OverallEvaluationStatus.CORRECT_COMPLETE


