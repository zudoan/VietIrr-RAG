"""Unit tests for the Canonical QA Response Contract (Phase 1 / Gate A).

Validates:
1. Valid accepted answer contract: abstained=False, abstention_type="NONE", guard_verdict="PASS", final_status="FINAL_ANSWER_ACCEPTED"
2. Raw model abstention contract: abstained=True, abstention_type="MODEL_ABSTAINED", final_status="FINAL_ABSTAINED"
3. Raw answer rejected by Guard: abstained=True, abstention_type="GUARD_REJECTED", guard_verdict="ABSTAIN", final_status="FINAL_ABSTAINED"
4. Missing required schema field raises ValidationError.
5. Invalid schema field value raises ValidationError.
6. Valid citation response with viewer_url and provenance_status="VALID".
7. No citation response (empty list).
8. Verification shadow payload enabled structure.
"""

import pytest
from pydantic import ValidationError
from viirr_api.schemas import CitationResponse, QARequest, QAResponse


def test_01_valid_accepted_answer_contract():
    data = {
        "request_id": "REQ-101",
        "answer": "Cao trình đáy cống Bắc Trang là -3 m và Bông Bót là -4,5 m.",
        "pipeline": "r6",
        "generation_model": "qwen2.5:7b",
        "corpus_version": "V4_R6_FROZEN",
        "verification": {"mode": "off", "status": "NOT_RUN"},
        "correction": {"mode": "off", "status": "NOT_RUN"},
        "citations": [
            {
                "document_id": "IRR_CTL_2024_9a520097",
                "page_id": "PAGE_0056",
                "page_number": 56,
                "evidence_id": "TAB_IRR_CTL_2024_9a520097_P0056_01_R007_C005",
                "source_version": "V4_R6_FROZEN",
                "snippet": "Cao trình -3 m",
                "provenance_status": "VALID",
                "viewer_url": "/api/v1/documents/IRR_CTL_2024_9a520097/pdf?page=56",
                "title": "Báo cáo giám sát",
                "source_agency": "Cục Thủy lợi",
                "unit_type": "TABLE_CELL",
            }
        ],
        "retrieved_references": [],
        "timing_ms": {"retrieval": 150.0, "reranking": None, "generation": 1200.0, "total": 1350.0},
        "trace": {"grounding": {"action": "PASS", "reason": "OK"}},
        "abstained": False,
        "abstention_type": "NONE",
        "guard_verdict": "PASS",
        "guard_reason": "OK",
        "model_generated_answer": True,
        "final_status": "FINAL_ANSWER_ACCEPTED",
    }
    resp = QAResponse(**data)
    assert resp.abstained is False
    assert resp.abstention_type == "NONE"
    assert resp.guard_verdict == "PASS"
    assert resp.final_status == "FINAL_ANSWER_ACCEPTED"
    assert len(resp.citations) == 1
    assert resp.citations[0].viewer_url is not None


def test_02_raw_model_abstention_contract():
    data = {
        "request_id": "REQ-102",
        "answer": "Không đủ bằng chứng trong ngữ cảnh được cung cấp để trả lời đáng tin cậy.",
        "pipeline": "r6",
        "generation_model": "qwen2.5:7b",
        "corpus_version": "V4_R6_FROZEN",
        "verification": {"mode": "off", "status": "NOT_RUN"},
        "correction": {"mode": "off", "status": "NOT_RUN"},
        "citations": [],
        "retrieved_references": [],
        "timing_ms": {"retrieval": 100.0, "reranking": None, "generation": 500.0, "total": 600.0},
        "trace": {"grounding": {"action": "ABSTAIN", "reason": "MODEL_SELF_ABSTAINED"}},
        "abstained": True,
        "abstention_type": "MODEL_ABSTAINED",
        "guard_verdict": "ABSTAIN",
        "guard_reason": "MODEL_SELF_ABSTAINED",
        "model_generated_answer": False,
        "final_status": "FINAL_ABSTAINED",
    }
    resp = QAResponse(**data)
    assert resp.abstained is True
    assert resp.abstention_type == "MODEL_ABSTAINED"
    assert resp.final_status == "FINAL_ABSTAINED"
    assert len(resp.citations) == 0


def test_03_raw_answer_rejected_by_guard():
    data = {
        "request_id": "REQ-103",
        "answer": "Không đủ bằng chứng trong ngữ cảnh được cung cấp để trả lời đáng tin cậy.",
        "pipeline": "r6",
        "generation_model": "qwen2.5:7b",
        "corpus_version": "V4_R6_FROZEN",
        "verification": {"mode": "off", "status": "NOT_RUN"},
        "correction": {"mode": "off", "status": "NOT_RUN"},
        "citations": [],
        "retrieved_references": [],
        "timing_ms": {"retrieval": 120.0, "reranking": None, "generation": 1100.0, "total": 1220.0},
        "trace": {
            "grounding": {
                "action": "ABSTAIN",
                "reason": "P5 grounding guard: CONTRADICTED_ANSWER_CLAIM",
            }
        },
        "abstained": True,
        "abstention_type": "GUARD_REJECTED",
        "guard_verdict": "ABSTAIN",
        "guard_reason": "P5 grounding guard: CONTRADICTED_ANSWER_CLAIM",
        "model_generated_answer": True,
        "final_status": "FINAL_ABSTAINED",
    }
    resp = QAResponse(**data)
    assert resp.abstained is True
    assert resp.abstention_type == "GUARD_REJECTED"
    assert resp.guard_verdict == "ABSTAIN"
    assert resp.model_generated_answer is True  # Model generated content, but Guard blocked it
    assert resp.final_status == "FINAL_ABSTAINED"


def test_04_missing_required_schema_field():
    # Missing answer field
    data = {
        "request_id": "REQ-104",
        "pipeline": "r6",
        "generation_model": "qwen2.5:7b",
        "corpus_version": "V4_R6_FROZEN",
    }
    with pytest.raises(ValidationError):
        QAResponse(**data)


def test_05_invalid_pipeline_value_rejected():
    data = {
        "request_id": "REQ-105",
        "answer": "Ans",
        "pipeline": "invalid_pipeline_xyz",
        "generation_model": "qwen2.5:7b",
        "corpus_version": "V4_R6_FROZEN",
        "verification": {},
        "correction": {},
        "citations": [],
        "timing_ms": {},
        "trace": {},
    }
    with pytest.raises(ValidationError):
        QAResponse(**data)


def test_06_verification_shadow_enabled():
    data = {
        "request_id": "REQ-106",
        "answer": "Ans",
        "pipeline": "r6",
        "generation_model": "qwen2.5:7b",
        "corpus_version": "V4_R6_FROZEN",
        "verification": {
            "mode": "shadow",
            "status": "RUN_SHADOW",
            "canonical_verdict": "SUPPORTED",
            "total_claims": 2,
            "supported_count": 2,
            "contradicted_count": 0,
        },
        "correction": {"mode": "off", "status": "NOT_RUN"},
        "citations": [],
        "timing_ms": {},
        "trace": {},
        "abstained": False,
        "abstention_type": "NONE",
        "final_status": "FINAL_ANSWER_ACCEPTED",
    }
    resp = QAResponse(**data)
    assert resp.verification["mode"] == "shadow"
    assert resp.verification["status"] == "RUN_SHADOW"
    assert resp.verification["supported_count"] == 2
