from __future__ import annotations

import json

from viirr_rag.pipeline import (
    Evidence,
    build_context,
    build_prompt,
    evaluate_answer,
    expand_table_evidence,
    parse_generation,
)
from viirr_rag.retrieval import fusion_order


def evidence(rank: int, text: str = "Mực nước báo động II là 10,4 m.") -> Evidence:
    return Evidence(
        rank=rank,
        evidence_id=f"REG_DOC_P0001_B{rank:03d}",
        doc_id="DOC",
        page_id="PAGE_DOC_0001",
        page_number=1,
        unit_type="TEXT_REGION",
        score=1.0 / rank,
        text=text,
        source="synthetic_test",
    )


def test_context_budget_keeps_provenance_and_marks_truncation():
    context = build_context([evidence(1, "x" * 400), evidence(2, "y" * 400)], budget_tokens=120)
    assert context.evidence
    assert context.estimated_tokens <= 120
    assert context.truncated is True
    assert "evidence_id=REG_DOC_P0001_B001" in context.text


def test_parse_generation_normalizes_structured_citation():
    raw = json.dumps(
        {
            "answer": "Không thể áp chung.",
            "citations": [{"doc_id": "DOC", "page_number": 1, "evidence_id": "REG_DOC_P0001_B001"}],
            "abstained": False,
            "abstention_reason": "",
            "evidence_supported": True,
        },
        ensure_ascii=False,
    )
    result = parse_generation(raw)
    assert result.parse_error == ""
    assert result.citations[0]["page_number"] == 1
    assert result.evidence_supported is True


def test_evaluation_requires_exact_context_citation():
    context = build_context([evidence(1)], budget_tokens=500)
    generation = parse_generation(
        json.dumps(
            {
                "answer": "Mực nước báo động II là 10,4 m.",
                "citations": [
                    {"doc_id": "DOC", "page_number": 2, "evidence_id": "REG_DOC_P0001_B001"}
                ],
                "abstained": False,
                "abstention_reason": "",
                "evidence_supported": True,
            },
            ensure_ascii=False,
        )
    )
    evaluation = evaluate_answer(
        generation,
        "Mực nước báo động II là 10,4 m.",
        context,
        "COMPLETE_REFERENCE_PAGE_COVERAGE",
    )
    assert evaluation["citation_validity"] == "INVALID"
    assert evaluation["numeric_recall"] == 1.0


def test_valid_citation_id_does_not_imply_claim_support():
    context = build_context([evidence(1, "Bản đồ thể hiện vị trí các trạm quan trắc.")], budget_tokens=500)
    generation = parse_generation(
        json.dumps(
            {
                "answer": "Mực nước báo động II là 10,4 m.",
                "citations": [
                    {"doc_id": "DOC", "page_number": 1, "evidence_id": "REG_DOC_P0001_B001"}
                ],
                "abstained": False,
                "abstention_reason": "",
                "evidence_supported": True,
            },
            ensure_ascii=False,
        )
    )
    evaluation = evaluate_answer(
        generation,
        "Mực nước báo động II là 10,4 m.",
        context,
        "COMPLETE_REFERENCE_PAGE_COVERAGE",
    )
    assert evaluation["semantic_correctness"] == "MATCH"
    assert evaluation["citation_id_validity"] == "VALID"
    assert evaluation["citation_claim_support"] == "UNSUPPORTED"


def test_empty_context_expects_abstention():
    context = build_context([], budget_tokens=500)
    generation = parse_generation(
        json.dumps(
            {
                "answer": "Không đủ bằng chứng trong ngữ cảnh được cung cấp để trả lời đáng tin cậy.",
                "citations": [],
                "abstained": True,
                "abstention_reason": "Không có evidence.",
                "evidence_supported": False,
            },
            ensure_ascii=False,
        )
    )
    evaluation = evaluate_answer(generation, "Một đáp án tham chiếu.", context, "NONE")
    assert evaluation["abstention_behavior"] == "EXPECTED"
    assert evaluation["citation_validity"] == "NOT_APPLICABLE"


def test_synthetic_pipeline_smoke_builds_prompt_and_scores_answer():
    context = build_context([evidence(1)], budget_tokens=500)
    messages = build_prompt("Mực nước báo động II là bao nhiêu?", context)
    assert len(messages) == 2
    assert "QUESTION:" in messages[1]["content"]
    assert "doc_id=DOC" in messages[1]["content"]
    generation = parse_generation(
        '{"answer":"10,4 m.","citations":[{"doc_id":"DOC","page_number":1,'
        '"evidence_id":"REG_DOC_P0001_B001"}],"abstained":false,'
        '"abstention_reason":"","evidence_supported":true}'
    )
    evaluation = evaluate_answer(generation, "10,4 m.", context, "COMPLETE_REFERENCE_PAGE_COVERAGE")
    assert evaluation["provisional_correctness"] == "PROVISIONAL_MATCH"
    assert evaluation["citation_validity"] == "VALID"


def test_fusion_order_is_deterministic_for_ties():
    import numpy as np

    indexes, scores = fusion_order(
        ["B", "A", "C"],
        np.asarray([1.0, 1.0, 0.0]),
        np.asarray([1.0, 1.0, 0.0]),
    )
    assert indexes[:2] == [1, 0]
    assert scores[0] > scores[1]


def test_semantic_paraphrase_is_not_mislabeled_by_token_f1():
    context = build_context(
        [
            evidence(
                1,
                "Báo động II: Xuân Khánh 10,4 m; Lý Nhân 11,0 m.",
            )
        ],
        budget_tokens=500,
    )
    generation = parse_generation(
        json.dumps(
            {
                "answer": "Không thể áp chung 10,4 m vì hai trạm có ngưỡng báo động II khác nhau.",
                "citations": [
                    {"doc_id": "DOC", "page_number": 1, "evidence_id": "REG_DOC_P0001_B001"}
                ],
                "abstained": False,
                "abstention_reason": "",
                "evidence_supported": True,
            },
            ensure_ascii=False,
        )
    )
    evaluation = evaluate_answer(
        generation,
        "Không. Hai trạm thuộc hai sông với mốc báo động II khác nhau.",
        context,
        "COMPLETE_REFERENCE_PAGE_COVERAGE",
    )
    assert evaluation["provisional_correctness"] == "PROVISIONAL_SEMANTIC_MATCH"
    assert evaluation["semantic_correctness"] in {"MATCH", "SEMANTIC_MATCH"}
    assert evaluation["provisional_correctness"] != "ABSTAIN"
    assert evaluation["citation_id_validity"] == "VALID"
    assert evaluation["citation_claim_support"] == "SUPPORTED"


def test_semantic_evaluator_detects_opposite_conclusion():
    context = build_context(
        [evidence(1, "BHH10 có chín giá trị từ 5,12 đến 5,71 mg/L; ô trung bình in 4,93 mg/L.")],
        budget_tokens=500,
    )
    generation = parse_generation(
        json.dumps(
            {
                "answer": "Ô trung bình 4,93 mg/L phù hợp với dãy giá trị ngày.",
                "citations": [
                    {"doc_id": "DOC", "page_number": 1, "evidence_id": "REG_DOC_P0001_B001"}
                ],
                "abstained": False,
                "abstention_reason": "",
                "evidence_supported": True,
            },
            ensure_ascii=False,
        )
    )
    evaluation = evaluate_answer(
        generation,
        "Không. Ô 4,93 mg/L mâu thuẫn với chín giá trị ngày từ 5,12 đến 5,71 mg/L.",
        context,
        "COMPLETE_REFERENCE_PAGE_COVERAGE",
    )
    assert evaluation["semantic_correctness"] == "MISMATCH"
    assert evaluation["provisional_correctness"] == "PROVISIONAL_MISMATCH"
    assert evaluation["citation_id_validity"] == "VALID"


def test_semantic_evaluator_accepts_khong_nhat_quan_paraphrase():
    context = build_context(
        [evidence(1, "BHH10 có chín giá trị từ 5,12 đến 5,71 mg/L; ô trung bình in 4,93 mg/L.")],
        budget_tokens=500,
    )
    generation = parse_generation(
        json.dumps(
            {
                "answer": "Dãy giá trị ngày không nhất quán với trung bình 4,93 mg/L được nêu.",
                "citations": [
                    {"doc_id": "DOC", "page_number": 1, "evidence_id": "REG_DOC_P0001_B001"}
                ],
                "abstained": False,
                "abstention_reason": "",
                "evidence_supported": True,
            },
            ensure_ascii=False,
        )
    )
    evaluation = evaluate_answer(
        generation,
        "Không. Ô 4,93 mg/L mâu thuẫn với chín giá trị ngày từ 5,12 đến 5,71 mg/L.",
        context,
        "COMPLETE_REFERENCE_PAGE_COVERAGE",
    )
    assert evaluation["semantic_correctness"] == "SEMANTIC_MATCH"
    assert evaluation["provisional_correctness"] == "PROVISIONAL_SEMANTIC_MATCH"


def test_substantive_answer_is_scored_when_abstention_flag_is_inconsistent():
    context = build_context([evidence(1, "Bản đồ chỉ thể hiện vị trí trạm.")], budget_tokens=500)
    generation = parse_generation(
        json.dumps(
            {
                "answer": "Không thể suy ra đỉnh dự báo từng trạm chỉ từ bản đồ vị trí.",
                "citations": [],
                "abstained": True,
                "abstention_reason": "Thiếu bảng số liệu.",
                "evidence_supported": False,
            },
            ensure_ascii=False,
        )
    )
    evaluation = evaluate_answer(
        generation,
        "Không. Bản đồ vị trí không thay thế bảng số liệu dự báo từng trạm.",
        context,
        "COMPLETE_REFERENCE_PAGE_COVERAGE",
    )
    assert evaluation["semantic_correctness"] in {"MATCH", "SEMANTIC_MATCH"}
    assert evaluation["provisional_correctness"] != "ABSTAIN"
    assert evaluation["effective_abstention"] is False
    assert evaluation["abstention_flag_consistency"] == "INCONSISTENT"


def test_table_context_keeps_caption_header_station_values_and_units_together():
    page_rows = [
        evidence(1, "Bảng 2. Kết quả chất lượng nước ngày 14/03/2025"),
        evidence(2, "Đơn vị: mg/L; WQI: điểm"),
        evidence(3, "TT Trạm pH TSS DO WQI"),
        evidence(4, "5 MT5 (Kênh Trà)"),
        evidence(5, "6,97 24 7,55 97"),
    ]
    expanded = expand_table_evidence([page_rows[-1]], page_rows)
    assert [item.evidence_id for item in expanded] == [
        "REG_DOC_P0001_B001",
        "REG_DOC_P0001_B002",
        "REG_DOC_P0001_B003",
        "REG_DOC_P0001_B004",
        "REG_DOC_P0001_B005",
    ]
    assert all(item.page_number == 1 for item in expanded)
    assert expanded[-1].text.endswith("97")
