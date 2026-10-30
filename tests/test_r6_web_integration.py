from pathlib import Path

from viirr_api.r6_service import RAGInferenceService
from viirr_api.schemas import QARequest


ROOT = Path(__file__).resolve().parents[1]


def test_qa_schema_rejects_non_r6_and_long_question():
    assert QARequest(question="Cho tôi biết tài liệu này nói gì?").pipeline == "r6"
    try:
        QARequest(question="x", pipeline="bm25")
    except Exception:
        pass
    else:
        raise AssertionError("QA schema accepted an unsupported pipeline")


def test_r6_capability_and_pdf_registry_are_source_bounded():
    service = RAGInferenceService(ROOT)
    status = service.capability_status()
    assert status["pipeline"] == "r6"
    assert status["corpus_version"] == "V4_R6_FROZEN"
    assert status["artifacts_available"] is True
    assert service.resolve_pdf("IRR_CP_2018_b4331af5") is not None
    assert service.resolve_pdf("../../Windows/system32") is None
