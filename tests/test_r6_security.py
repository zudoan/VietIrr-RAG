import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from viirr_api.app import create_app
from viirr_api.repository import PhaseERepository
from viirr_api.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def make_test_settings(db_path: Path, *, public_mode: bool = False, rate_limit: int = 60) -> Settings:
    return Settings(
        environment="development",
        database_url=f"sqlite+pysqlite:///{db_path}",
        allowed_origins=("http://127.0.0.1:5173",),
        public_mode=public_mode,
        public_evidence_excerpts=False,
        auto_create_schema=True,
        auto_seed=True,
        rate_limit_per_minute=rate_limit,
        search_timeout_seconds=5.0,
        max_request_bytes=65536,
        search_analytics_enabled=False,
        r6_enabled=True,
        r6_max_concurrency=1,
        r6_context_budget_tokens=4000,
        root=ROOT,
    )


def test_v4_document_detail_in_local_research_mode(tmp_path):
    app = create_app(make_test_settings(tmp_path / "sec1.db", public_mode=False), PhaseERepository(ROOT))
    with TestClient(app) as client:
        # V4 document exists in v4 manifest but not seeded in SQLite
        res = client.get("/api/v1/documents/IRR_SIWRP_2026_cd19368f")
        assert res.status_code == 200
        payload = res.json()
        assert payload["doc_id"] == "IRR_SIWRP_2026_cd19368f"
        assert payload["pdf_available"] is True
        assert payload["pdf_url"] == "/api/v1/documents/IRR_SIWRP_2026_cd19368f/pdf"


def test_v4_document_detail_blocked_in_public_mode_when_unapproved(tmp_path):
    app = create_app(make_test_settings(tmp_path / "sec2.db", public_mode=True), PhaseERepository(ROOT))
    with TestClient(app) as client:
        # V4 document not in V3.2 SQLite that is unapproved for redistribution
        res = client.get("/api/v1/documents/V4_BNNMT_2025_594e7382")
        assert res.status_code == 403
        assert "not approved for public redistribution" in res.json()["detail"]


def test_v4_pdf_blocked_in_public_mode_and_allowed_in_local_research(tmp_path):
    # Public mode: blocked
    app_pub = create_app(make_test_settings(tmp_path / "sec3_pub.db", public_mode=True), PhaseERepository(ROOT))
    with TestClient(app_pub) as client_pub:
        res = client_pub.get("/api/v1/documents/IRR_SIWRP_2026_cd19368f/pdf")
        assert res.status_code == 403

    # Local research mode: allowed and returns PDF content
    app_local = create_app(make_test_settings(tmp_path / "sec3_loc.db", public_mode=False), PhaseERepository(ROOT))
    with TestClient(app_local) as client_local:
        res = client_local.get("/api/v1/documents/IRR_SIWRP_2026_cd19368f/pdf")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert len(res.content) > 1000


def test_nonexistent_and_traversal_document_access(tmp_path):
    app = create_app(make_test_settings(tmp_path / "sec4.db", public_mode=False), PhaseERepository(ROOT))
    with TestClient(app) as client:
        # Non-existent doc
        res = client.get("/api/v1/documents/NONEXISTENT_DOCUMENT_ID")
        assert res.status_code == 404

        # Non-existent PDF
        res = client.get("/api/v1/documents/NONEXISTENT_DOCUMENT_ID/pdf")
        assert res.status_code == 404

        # Path traversal attempts
        res = client.get("/api/v1/documents/..%2F..%2FWindows%2Fsystem.ini/pdf")
        assert res.status_code in {404, 400}

        res = client.get("/api/v1/documents/%2E%2E%2Fsettings.py")
        assert res.status_code in {404, 400}


def test_qa_endpoint_rate_limiting(tmp_path):
    # Set limit to 3 requests per minute
    app = create_app(make_test_settings(tmp_path / "sec5.db", rate_limit=3), PhaseERepository(ROOT))
    with TestClient(app) as client:
        # First 3 requests should pass the rate limiter (they fail with validation 422 before inference)
        for _ in range(3):
            res = client.post("/api/v1/qa", json={"question": "x", "pipeline": "bm25"})
            assert res.status_code == 422

        # 4th request must be rejected with 429 Too Many Requests
        res4 = client.post("/api/v1/qa", json={"question": "x", "pipeline": "bm25"})
        assert res4.status_code == 429
        assert "Quá nhiều truy vấn" in res4.json()["detail"]


def test_qa_trace_redacted_in_public_mode(tmp_path, monkeypatch):
    app = create_app(make_test_settings(tmp_path / "sec6.db", public_mode=True), PhaseERepository(ROOT))
    fake_result = {
        "request_id": "test-uuid",
        "answer": "Câu trả lời mẫu.",
        "pipeline": "r6",
        "generation_model": "qwen2.5:7b",
        "corpus_version": "V4_R6_FROZEN",
        "verification": {"mode": "off", "status": "NOT_RUN"},
        "correction": {"mode": "off", "status": "NOT_RUN"},
        "citations": [],
        "retrieved_references": [],
        "timing_ms": {"retrieval": 10.0, "reranking": None, "generation": 20.0, "total": 30.0},
        "trace": {"candidate_page_ids": ["P1"], "context": "sensitive raw context"},
    }
    with TestClient(app) as client:
        monkeypatch.setattr(client.app.state.r6_service, "ask", lambda *args, **kwargs: fake_result)
        res = client.post("/api/v1/qa", json={"question": "Thủy lợi Việt Nam là gì?", "pipeline": "r6"})
        assert res.status_code == 200
        payload = res.json()
        assert payload["trace"] == {"diagnostic_status": "REDACTED_IN_PUBLIC_MODE"}
        assert "sensitive raw context" not in str(payload)
