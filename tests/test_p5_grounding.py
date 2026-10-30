from __future__ import annotations

import json

import pytest

from viirr_rag.pipeline import (
    Evidence,
    build_context,
    build_grounded_prompt,
    enforce_citation_grounding,
    expand_grounded_evidence,
    parse_generation,
    select_context_evidence,
)


def evidence(
    block: int,
    text: str,
    *,
    page: int = 1,
    doc_id: str = "DOC",
    rank: int | None = None,
) -> Evidence:
    return Evidence(
        rank=rank or block,
        evidence_id=f"REG_{doc_id}_P{page:04d}_B{block:03d}",
        doc_id=doc_id,
        page_id=f"PAGE_{doc_id}_{page:04d}",
        page_number=page,
        unit_type="TEXT_REGION",
        score=1.0 / (rank or block),
        text=text,
        source="synthetic_p5_test",
    )


def generation(answer: str, citations: list[dict[str, object]], abstained: bool = False):
    return parse_generation(
        json.dumps(
            {
                "answer": answer,
                "citations": citations,
                "abstained": abstained,
                "abstention_reason": "",
                "evidence_supported": bool(citations),
            },
            ensure_ascii=False,
        )
    )


def citation(item: Evidence) -> dict[str, object]:
    return {
        "doc_id": item.doc_id,
        "page_number": item.page_number,
        "evidence_id": item.evidence_id,
    }


def test_selection_has_no_per_page_quota_for_complementary_evidence():
    rows = [evidence(index, f"MT5 WQI hàng bổ sung {index}", rank=index) for index in range(1, 9)]
    selected = select_context_evidence("MT5 WQI", rows, max_anchors=8)
    assert len(selected) == 8
    assert {item.page_id for item in selected} == {"PAGE_DOC_0001"}


def test_table_bundle_keeps_caption_header_station_and_values():
    page_rows = [
        evidence(2, "Bảng 2. Kết quả đo đạc chất lượng nước ngày 14/03/2025"),
        evidence(13, "Đơn vị: mg/L; TT Trạm pH DO WQI"),
        evidence(14, "1 MT1 (Đầu sông Trà Ngoa)"),
        evidence(15, "6,90 29,0 6,67 100"),
    ]
    expanded = expand_grounded_evidence(
        [page_rows[-1]],
        page_rows,
        "WQI của MT1 ngày 14/03/2025 là bao nhiêu?",
    )
    assert [item.evidence_id for item in expanded] == [item.evidence_id for item in page_rows]
    assert {item.context_group for item in expanded} == {"TABLE:PAGE_DOC_0001:015"}
    assert expanded[0].context_role == "table_caption"
    assert expanded[1].context_role == "table_header_or_unit"


def test_legal_bundle_crosses_page_boundary_for_continued_condition():
    page_one = evidence(
        17,
        "Lũ kiểm tra tần suất 0,01%",
        page=1,
        doc_id="QD922",
    )
    page_two = evidence(
        0,
        "đối với Hòa Bình và Thác Bà; lũ kiểm tra tần suất 0,02% đối với Tuyên Quang.",
        page=2,
        doc_id="QD922",
        rank=1,
    )
    expanded = expand_grounded_evidence(
        [page_two],
        [page_one, page_two],
        "Trong Quyết định 922, có áp 0,01% cho Tuyên Quang không?",
    )
    assert [item.evidence_id for item in expanded] == [page_one.evidence_id, page_two.evidence_id]
    assert all(item.context_role == "legal_condition" for item in expanded)


def test_legal_bundle_keeps_document_identity_and_condition_markers():
    identity = evidence(3, "Số: 922/QĐ-TTg, ngày 14 tháng 5 năm 2025", doc_id="QD922")
    condition = evidence(
        17,
        "Trợ cấp tai nạn từ 5% trở lên thuộc thẩm quyền cấp tỉnh.",
        doc_id="QD922",
    )
    expanded = expand_grounded_evidence(
        [condition],
        [identity, condition],
        "Theo QĐ 922/2025, trường hợp từ 5% trở lên do ai quyết định?",
    )
    context = build_context(expanded, 500)
    assert identity.evidence_id in {item.evidence_id for item in expanded}
    assert "context_role=legal_identity" in context.text
    assert "condition_markers=AT_LEAST" in context.text


def test_grounded_prompt_contains_table_and_legal_safety_rules():
    context = build_context([evidence(1, "Từ 5% trở lên thuộc cấp tỉnh.")], 500)
    messages = build_grounded_prompt("Ai quyết định?", context)
    assert "header" in messages[0]["content"]
    assert "từ 5% trở lên" in messages[0]["content"]
    assert "Mỗi citation" in messages[0]["content"]


def test_grounding_guard_rejects_non_context_citation():
    item = evidence(1, "Mực nước báo động II là 10,4 m.")
    context = build_context([item], 500)
    result, audit = enforce_citation_grounding(
        generation(
            "Mực nước báo động II là 10,4 m.",
            [{"doc_id": "DOC", "page_number": 9, "evidence_id": item.evidence_id}],
        ),
        context,
    )
    assert result.abstained is True
    assert result.citations == []
    assert audit["reason"] == "NO_EXACT_CONTEXT_CITATION"


def test_grounding_guard_rejects_valid_id_that_does_not_support_claim():
    item = evidence(1, "Bản đồ thể hiện vị trí các trạm quan trắc.")
    context = build_context([item], 500)
    result, audit = enforce_citation_grounding(
        generation("Mực nước báo động II là 10,4 m.", [citation(item)]),
        context,
    )
    assert result.abstained is True
    assert audit["reason"] == "CITATIONS_DO_NOT_SUPPORT_ANY_CLAIM"


def test_grounding_guard_rejects_broad_document_with_incidental_term_overlap():
    item = evidence(
        1,
        (
            "Việt Nam chú trọng công tác cảnh báo sớm thiên tai bằng các bản tin dự báo "
            "thời tiết ngắn hạn và dài hạn. Việc phối hợp xả lũ hồ chứa với dự báo lũ "
            "được đề cập trong các quy trình liên hồ, trong khi cảnh báo cần truyền đến "
            "người dân qua truyền hình, phát thanh và lực lượng xung kích địa phương. "
            "Các chính sách phù hợp có thể cải thiện việc chuẩn bị ứng phó và giảm thiệt hại."
        ),
    )
    context = build_context([item], 5000)
    result, audit = enforce_citation_grounding(
        generation(
            "Lệnh điều hành qua điện thoại mà chủ hồ không lưu lại thì không bảo đảm truy vết.",
            [citation(item)],
        ),
        context,
    )
    assert result.abstained is True
    assert audit["reason"] == "CITATIONS_DO_NOT_SUPPORT_ANY_CLAIM"


def test_grounding_guard_accepts_collective_table_support():
    header = evidence(1, "TT Trạm DO trung bình Đơn vị mg/L")
    row = evidence(2, "BHH10 Cầu Cất 4,93 mg/L")
    header = Evidence(**{**header.to_dict(), "context_group": "TABLE:X", "context_role": "table_header_or_unit"})
    row = Evidence(**{**row.to_dict(), "context_group": "TABLE:X", "context_role": "table_row"})
    context = build_context([header, row], 500)
    result, audit = enforce_citation_grounding(
        generation(
            "DO trung bình tại BHH10 Cầu Cất là 4,93 mg/L.",
            [citation(header), citation(row)],
        ),
        context,
    )
    assert result.abstained is False
    assert result.evidence_supported is True
    assert len(result.citations) == 2
    assert audit["action"] == "PASS"


def test_grounding_guard_rejects_reversed_legal_threshold():
    item = evidence(
        1,
        "Tai nạn làm suy giảm khả năng lao động từ 5% trở lên do Chủ tịch UBND cấp tỉnh quyết định.",
    )
    context = build_context([item], 500)
    result, audit = enforce_citation_grounding(
        generation(
            "Trường hợp dưới 5% do Chủ tịch UBND cấp tỉnh quyết định.",
            [citation(item)],
        ),
        context,
    )
    assert result.abstained is True
    assert audit["reason"] == "CONTRADICTED_ANSWER_CLAIM"
    assert audit["support_status"] == "CONTRADICTED"


@pytest.mark.parametrize(
    ("source", "answer", "dimension"),
    [
        (
            "Chủ hồ phải lưu lại lệnh điều hành qua điện thoại để bảo đảm truy vết.",
            "Chủ hồ không phải lưu lại lệnh điều hành qua điện thoại để bảo đảm truy vết.",
            "OBLIGATION",
        ),
        (
            "Hai kết quả đo DO tại trạm BHH10 là nhất quán ở mức 4,93 mg/L.",
            "Hai kết quả đo DO tại trạm BHH10 không nhất quán ở mức 4,93 mg/L.",
            "CONSISTENCY",
        ),
        (
            "Hai mức cảnh báo 10,4 m và 11,2 m là hai mức khác nhau.",
            "Hai mức cảnh báo 10,4 m và 11,2 m là hai mức giống nhau.",
            "EQUALITY",
        ),
    ],
)
def test_grounding_guard_rejects_semantic_opposites(source, answer, dimension):
    item = evidence(1, source)
    context = build_context([item], 500)
    result, audit = enforce_citation_grounding(
        generation(answer, [citation(item)]),
        context,
    )
    assert result.abstained is True
    assert result.evidence_supported is False
    assert audit["reason"] == "CONTRADICTED_ANSWER_CLAIM"
    assert audit["support_status"] == "CONTRADICTED"
    assert dimension in audit["claim_support"][0]["contradicted_dimensions"]


@pytest.mark.parametrize(
    ("source", "answer", "dimension"),
    [
        (
            "Chủ hồ phải lưu lại lệnh điều hành qua điện thoại để bảo đảm truy vết.",
            "Chủ hồ bắt buộc phải lưu lệnh điều hành qua điện thoại để bảo đảm truy vết.",
            "OBLIGATION",
        ),
        (
            "Hai kết quả đo DO tại trạm BHH10 là nhất quán ở mức 4,93 mg/L.",
            "Hai kết quả DO 4,93 mg/L tại BHH10 phù hợp nhau.",
            "CONSISTENCY",
        ),
        (
            "Hai mức cảnh báo 10,4 m và 11,2 m là hai mức khác nhau.",
            "Hai mức cảnh báo 10,4 m và 11,2 m có sự chênh lệch.",
            "EQUALITY",
        ),
    ],
)
def test_grounding_guard_keeps_semantically_aligned_claims(source, answer, dimension):
    item = evidence(1, source)
    context = build_context([item], 500)
    result, audit = enforce_citation_grounding(
        generation(answer, [citation(item)]),
        context,
    )
    assert result.abstained is False
    assert result.evidence_supported is True
    assert audit["action"] == "PASS"
    assert audit["support_status"] == "SUPPORTED"
    assert dimension in audit["claim_support"][0]["aligned_dimensions"]


def test_grounding_guard_marks_numeric_and_lexical_overlap_unverified():
    item = evidence(1, "Báo cáo so sánh hai mức cảnh báo 10,4 m và 11,2 m.")
    context = build_context([item], 500)
    result, audit = enforce_citation_grounding(
        generation(
            "Hai mức cảnh báo 10,4 m và 11,2 m là giống nhau.",
            [citation(item)],
        ),
        context,
    )
    assert result.abstained is True
    assert audit["reason"] == "UNVERIFIED_ANSWER_CLAIM"
    assert audit["support_status"] == "INSUFFICIENT"
    assert audit["claim_support"][0]["status"] == "INSUFFICIENT"


def test_grounding_guard_marks_high_lexical_overlap_unverified():
    item = evidence(
        1,
        "Quy trình ghi nhận lệnh điều hành qua điện thoại và lưu hồ sơ vận hành.",
    )
    context = build_context([item], 500)
    result, audit = enforce_citation_grounding(
        generation(
            "Quy trình ghi nhận lệnh điều hành qua điện thoại đã được phê duyệt.",
            [citation(item)],
        ),
        context,
    )
    assert result.abstained is True
    assert audit["reason"] == "UNVERIFIED_ANSWER_CLAIM"
    assert audit["support_status"] == "INSUFFICIENT"


def test_grounding_guard_accepts_exact_supported_statement():
    item = evidence(1, "Mực nước báo động II tại trạm là 10,4 m.")
    context = build_context([item], 500)
    result, audit = enforce_citation_grounding(
        generation("Mực nước báo động II tại trạm là 10,4 m.", [citation(item)]),
        context,
    )
    assert result.abstained is False
    assert result.evidence_supported is True
    assert audit["support_status"] == "SUPPORTED"


def test_grounding_guard_rejects_value_from_another_table_row():
    header = evidence(1, "Trạm DO trung bình Đơn vị mg/L")
    station_bhh10 = evidence(2, "BHH10 Cầu Cất 4,93 mg/L")
    station_bhh01 = evidence(3, "BHH01 Cống Xuân Quan 7,5 mg/L")
    items = [
        Evidence(**{**header.to_dict(), "context_group": "TABLE:DO", "context_role": "table_header_or_unit"}),
        Evidence(**{**station_bhh10.to_dict(), "context_group": "TABLE:DO", "context_role": "table_row"}),
        Evidence(**{**station_bhh01.to_dict(), "context_group": "TABLE:DO", "context_role": "table_row"}),
    ]
    context = build_context(items, 500)
    result, audit = enforce_citation_grounding(
        generation(
            "DO trung bình tại trạm BHH10 Cầu Cất là 7,5 mg/L.",
            [citation(item) for item in items],
        ),
        context,
    )
    assert result.abstained is True
    assert audit["support_status"] == "CONTRADICTED"


def test_grounding_guard_accepts_correct_branch_in_mixed_conditions():
    item = evidence(
        1,
        (
            "Trường hợp dưới 5% do cấp xã xử lý; "
            "trường hợp từ 5% trở lên do Chủ tịch UBND cấp tỉnh quyết định."
        ),
    )
    item = Evidence(**{**item.to_dict(), "context_role": "legal_condition"})
    context = build_context([item], 500)
    result, audit = enforce_citation_grounding(
        generation(
            "Trường hợp từ 5% trở lên do Chủ tịch UBND cấp tỉnh quyết định.",
            [citation(item)],
        ),
        context,
    )
    assert result.abstained is False
    assert audit["support_status"] == "SUPPORTED"


def test_grounding_guard_normalizes_decimal_comma_and_dot_within_table_row():
    header = Evidence(
        **{**evidence(1, "Trạm DO trung bình Đơn vị mg/L").to_dict(), "context_group": "TABLE:DO", "context_role": "table_header_or_unit"}
    )
    row = Evidence(
        **{**evidence(2, "BHH10 Cầu Cất 4,93 mg/L").to_dict(), "context_group": "TABLE:DO", "context_role": "table_row"}
    )
    context = build_context([header, row], 500)
    result, audit = enforce_citation_grounding(
        generation("DO trung bình tại BHH10 Cầu Cất là 4.93 mg/L.", [citation(header), citation(row)]),
        context,
    )
    assert result.abstained is False
    assert audit["support_status"] == "SUPPORTED"


def test_grounding_guard_rejects_wrong_reservoir_storage_row():
    header = Evidence(
        **{**evidence(1, "Hồ Dung tích phòng lũ Đơn vị triệu m3").to_dict(), "context_group": "TABLE:STORAGE", "context_role": "table_header_or_unit"}
    )
    son_la = Evidence(
        **{**evidence(2, "Sơn La 9,5 triệu m3").to_dict(), "context_group": "TABLE:STORAGE", "context_role": "table_row"}
    )
    hoa_binh = Evidence(
        **{**evidence(3, "Hòa Bình 8,0 triệu m3").to_dict(), "context_group": "TABLE:STORAGE", "context_role": "table_row"}
    )
    context = build_context([header, son_la, hoa_binh], 500)
    result, audit = enforce_citation_grounding(
        generation("Dung tích phòng lũ của hồ Sơn La là 8,0 triệu m3.", [citation(item) for item in [header, son_la, hoa_binh]]),
        context,
    )
    assert result.abstained is True
    assert audit["support_status"] == "CONTRADICTED"


@pytest.mark.parametrize(
    ("source", "answer", "expected_status"),
    [
        (
            "Năm 2024, DO trung bình tại trạm BHH10 là 4,93 mg/L.",
            "Năm 2025, DO trung bình tại trạm BHH10 là 4,93 mg/L.",
            "INSUFFICIENT",
        ),
        (
            "Mực nước tại trạm BHH10 là 4,93 m.",
            "Mực nước tại trạm BHH10 là 4,93 cm.",
            "CONTRADICTED",
        ),
        (
            "Trạm BHH10 được quan trắc DO trung bình trong tháng 4.",
            "DO trung bình tại trạm BHH10 là 4,93 mg/L.",
            "INSUFFICIENT",
        ),
    ],
)
def test_grounding_guard_checks_numeric_year_unit_and_missing_relation(source, answer, expected_status):
    item = evidence(1, source)
    context = build_context([item], 500)
    result, audit = enforce_citation_grounding(generation(answer, [citation(item)]), context)
    assert result.abstained is True
    assert audit["support_status"] == expected_status


def test_grounding_guard_rejects_wrong_authority_for_matching_condition():
    item = evidence(
        1,
        "Trường hợp dưới 5% do cấp xã xử lý; trường hợp từ 5% trở lên do Chủ tịch UBND cấp tỉnh quyết định.",
    )
    item = Evidence(**{**item.to_dict(), "context_role": "legal_condition"})
    context = build_context([item], 500)
    result, audit = enforce_citation_grounding(
        generation("Trường hợp từ 5% trở lên do Chủ tịch UBND cấp huyện quyết định.", [citation(item)]),
        context,
    )
    assert result.abstained is True
    assert audit["support_status"] == "CONTRADICTED"


@pytest.mark.parametrize(
    ("answer", "expected_status"),
    [
        ("Trường hợp trên 5% do Chủ tịch UBND cấp tỉnh quyết định.", "SUPPORTED"),
        ("Chủ tịch UBND cấp tỉnh quyết định.", "INSUFFICIENT"),
    ],
)
def test_grounding_guard_checks_condition_boundaries_and_missing_condition(answer, expected_status):
    item = evidence(
        1,
        "Trường hợp dưới 5% do cấp xã xử lý; trường hợp từ 5% trở lên do Chủ tịch UBND cấp tỉnh quyết định.",
    )
    item = Evidence(**{**item.to_dict(), "context_role": "legal_condition"})
    context = build_context([item], 500)
    result, audit = enforce_citation_grounding(generation(answer, [citation(item)]), context)
    if expected_status == "SUPPORTED":
        assert result.abstained is False
    else:
        assert result.abstained is True
    assert audit["support_status"] == expected_status


def test_grounding_guard_rejects_disjoint_inclusive_boundary():
    item = evidence(1, "Trường hợp không quá 5% do cấp xã xử lý.")
    item = Evidence(**{**item.to_dict(), "context_role": "legal_condition"})
    context = build_context([item], 500)
    result, audit = enforce_citation_grounding(
        generation("Trường hợp trên 5% do cấp xã xử lý.", [citation(item)]),
        context,
    )
    assert result.abstained is True
    assert audit["support_status"] == "CONTRADICTED"


def test_grounding_guard_requires_all_claims_to_be_supported():
    item = evidence(1, "Mực nước báo động II tại trạm BHH10 là 10,4 m.")
    context = build_context([item], 500)
    result, audit = enforce_citation_grounding(
        generation(
            "Mực nước báo động II tại trạm BHH10 là 10,4 m. Dung tích hồ là 200 triệu m3.",
            [citation(item)],
        ),
        context,
    )
    assert result.abstained is True
    assert audit["support_status"] == "INSUFFICIENT"
    assert [item["status"] for item in audit["claim_support"]] == ["SUPPORTED", "INSUFFICIENT"]


def test_grounding_guard_rejects_wrong_legal_year_in_matching_branch():
    identity = evidence(1, "Quyết định số 922/QĐ-TTg ngày 14 tháng 5 năm 2025.")
    branch = evidence(2, "Trường hợp từ 5% trở lên do Chủ tịch UBND cấp tỉnh quyết định.")
    identity = Evidence(**{**identity.to_dict(), "context_group": "LEGAL:922", "context_role": "legal_identity"})
    branch = Evidence(**{**branch.to_dict(), "context_group": "LEGAL:922", "context_role": "legal_condition"})
    context = build_context([identity, branch], 500)
    result, audit = enforce_citation_grounding(
        generation("Theo Quyết định 922 năm 2024, trường hợp từ 5% trở lên do Chủ tịch UBND cấp tỉnh quyết định.", [citation(identity), citation(branch)]),
        context,
    )
    assert result.abstained is True
    assert audit["support_status"] == "INSUFFICIENT"

