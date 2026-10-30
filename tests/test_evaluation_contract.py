"""Tests for the 4-layer evaluation contract and answer correctness rubric.
Verifies all 12 scenarios required by GATE 1.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from scripts.evaluator_rubric import evaluate_answer_correctness, load_manifest


def test_01_correct_reference_answer_loading(tmp_path: Path):
    manifest_data = {
        "records": [
            {
                "qa_id": "QA_01",
                "question": "Mực nước hồ?",
                "reference_answer": "Mực nước là 42,08 m.",
                "entity": "Hồ Núi Cốc",
                "unit": "m",
            }
        ]
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest_data), encoding="utf-8")
    loaded = load_manifest(path)
    assert len(loaded) == 1
    assert loaded[0]["reference_answer"] == "Mực nước là 42,08 m."
    assert loaded[0]["qa_id"] == "QA_01"


def test_02_missing_reference_handling():
    res = evaluate_answer_correctness(
        actual_answer="Mực nước là 42,08 m.",
        reference_answer="",
    )
    assert res["verdict"] == "NOT_EVALUABLE"
    assert res["reason"] == "REFERENCE_MISSING"


def test_03_correct_complete_answer():
    res = evaluate_answer_correctness(
        actual_answer="Cao trình đáy của Hàm Giang là -3 m và Long Hiệp là -2 m.",
        reference_answer="Hàm Giang có mực nước -3 m. Long Hiệp có mực nước -2 m.",
        entity="Hàm Giang",
        unit="m",
    )
    assert res["verdict"] == "CORRECT_COMPLETE"


def test_04_correct_but_partial_answer_missing_secondary_clause():
    res = evaluate_answer_correctness(
        actual_answer="Cao trình đáy của Trà Vinh là -3 m.",
        reference_answer="Trà Vinh có mực nước -3 m. Nhận xét: Kết quả kiểm định mô phỏng phản ánh phù hợp chế độ dòng chảy.",
        entity="Trà Vinh",
        unit="m",
    )
    assert res["verdict"] == "CORRECT_PARTIAL"
    assert res["reason"] == "MISSING_QUALITATIVE_CLAUSE"


def test_05_wrong_numeric_value():
    res = evaluate_answer_correctness(
        actual_answer="Mực nước Hồ Núi Cốc hiện tại là 40,89 m.",
        reference_answer="Mực nước Hồ Núi Cốc hiện tại đạt cao trình +42,08m.",
        entity="Hồ Núi Cốc",
        unit="m",
    )
    assert res["verdict"] == "INCORRECT"
    assert res["reason"] == "NUMERIC_VALUE_MISMATCH"


def test_06_wrong_unit():
    res = evaluate_answer_correctness(
        actual_answer="Mực nước tại trạm BHH10 là 4,93 cm.",
        reference_answer="Mực nước tại trạm BHH10 là 4,93 m.",
        entity="Trạm BHH10",
        unit="m",
    )
    assert res["verdict"] == "INCORRECT"
    assert res["reason"] == "UNIT_MISMATCH"


def test_07_wrong_entity():
    res = evaluate_answer_correctness(
        actual_answer="Mực nước tại trạm Tân Hồng là 2,94 m.",
        reference_answer="Mực nước tại trạm An Long là 2,94 m.",
        entity="An Long",
        unit="m",
    )
    assert res["verdict"] == "INCORRECT"
    assert res["reason"] == "ENTITY_MISMATCH"


def test_08_wrong_period():
    res = evaluate_answer_correctness(
        actual_answer="Tại lưu vực sông Srêpốk năm 2024, tổng dung tích giảm 11 triệu m3.",
        reference_answer="Lưu vực sông Srêpốk năm 2025: tổng dung tích các hồ giảm khoảng 11 triệu m3.",
        entity="Srêpốk",
        unit="triệu m3",
    )
    assert res["verdict"] == "INCORRECT"
    assert res["reason"] == "TEMPORAL_PERIOD_MISMATCH"


def test_09_unrelated_but_cited_fact():
    # V3_CORE_00268 case: Answered 71% DTTK instead of Srêpốk -11 triệu m3
    res = evaluate_answer_correctness(
        actual_answer="Tại Srêpốk dung tích hữu ích các hồ thủy điện trong vùng trung bình đạt khoảng 71% DTTK.",
        reference_answer="Lưu vực sông Srêpốk: Tuần qua tổng dung tích các hồ giảm khoảng 11 triệu m3.",
        entity="Srêpốk",
        unit="triệu m3",
    )
    assert res["verdict"] == "INCORRECT"


def test_10_valid_citation_with_incomplete_answer():
    # V3_1_CHAL_00158 case: Answer has number 2,12m with citation, but missed local government recommendations
    res = evaluate_answer_correctness(
        actual_answer="Mực nước lớn nhất dự báo (m) — 06/10 của Trường Xuân là 2,12 m.",
        reference_answer="Trường Xuân có mực nước 2,12 m. Khuyến nghị: Kiến nghị các địa phương trên vùng ĐTM cần thường xuyên theo dõi chặt chẽ...",
        entity="Trường Xuân",
        unit="m",
    )
    assert res["verdict"] == "CORRECT_PARTIAL"


def test_11_abstention():
    res = evaluate_answer_correctness(
        actual_answer="Không đủ bằng chứng trong ngữ cảnh được cung cấp để trả lời đáng tin cậy.",
        reference_answer="Mực nước lớn nhất là 2,85 m.",
        is_abstained=True,
        guard_action="ABSTAIN",
    )
    assert res["verdict"] == "ABSTAINED"


def test_12_citation_guard_pass_but_reference_mismatch():
    # Guard says PASS because 71% DTTK is grounded in text, but reference answer required 11 triệu m3
    res = evaluate_answer_correctness(
        actual_answer="Tại Srêpốk dung tích hữu ích các hồ thủy điện trung bình đạt 71% DTTK.",
        reference_answer="Lưu vực sông Srêpốk: tổng dung tích giảm khoảng 11 triệu m3.",
        entity="Srêpốk",
        unit="triệu m3",
        guard_action="PASS",
    )
    assert res["verdict"] == "INCORRECT"
