import os
from pathlib import Path

import pytest

from viirr_api.app import create_app
from viirr_api.database import Base, create_database_engine, create_session_factory
from viirr_api.models import DataQualitySummary, Document
from viirr_api.repository import PhaseERepository, repair_text
from viirr_api.seed import seed_verified_artifacts
from viirr_api.settings import Settings


ROOT = Path(__file__).resolve().parents[1]


def make_settings(database_url: str, *, public_mode: bool = False) -> Settings:
    return Settings(
        environment="test",
        database_url=database_url,
        allowed_origins=("http://testserver",),
        public_mode=public_mode,
        public_evidence_excerpts=False,
        auto_create_schema=True,
        auto_seed=True,
        rate_limit_per_minute=100,
        search_timeout_seconds=8,
        max_request_bytes=65536,
        search_analytics_enabled=False,
        r6_enabled=True,
        r6_max_concurrency=1,
        r6_context_budget_tokens=4000,
        root=ROOT,
    )


def test_repairs_legacy_metadata_without_touching_clean_text():
    assert repair_text("Thủy lợi Việt Nam") == "Thủy lợi Việt Nam"
    assert repair_text("Cá»¥c Thá»§y lá»£i") == "Cục Thủy lợi"


def test_phase_e_repository_uses_real_frozen_artifacts():
    repository = PhaseERepository(ROOT)
    status = repository.status()
    assert status["mode"] == "EVIDENCE_SEARCH"
    assert status["answer_generation"] is False
    assert status["evidence_units"] == 27045

    result = repository.search("hồ chứa", top_k=3)
    assert result["answer"] is None
    assert result["retrieval_method"] == "BM25_B1_FROZEN_CORPUS"
    assert 0 < len(result["results"]) <= 3
    assert all(item["evidence_id"] for item in result["results"])


def test_seed_is_idempotent_and_uses_aggregate_v4_data(tmp_path):
    repository = PhaseERepository(ROOT)
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'seed.db'}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        first = seed_verified_artifacts(session, repository)
        second = seed_verified_artifacts(session, repository)
        assert first == second
        assert session.query(Document).count() == 89
        v4 = session.query(DataQualitySummary).filter_by(version="V4_BATCH_01_09").one()
        assert v4.qa_total == 793
        assert v4.human_gold == 0
    engine.dispose()


def test_fastapi_contract_and_live_search(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    del fastapi
    from fastapi.testclient import TestClient

    database_url = f"sqlite+pysqlite:///{tmp_path / 'api.db'}"
    app = create_app(make_settings(database_url), PhaseERepository(ROOT))
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["database"] == "ready"

        stages = client.get("/api/v1/stages")
        assert stages.status_code == 200
        assert [item["id"] for item in stages.json()["items"]] == ["corpus", "qa", "retrieval", "evaluation", "training", "deployment"]

        report = client.get("/api/v1/report")
        assert report.status_code == 200
        assert report.json()["datasets"]["v4_candidate_expansion"]["human_gold_true"] == 0

        search = client.post("/api/v1/search", json={"query": "quy trình vận hành hồ chứa", "top_k": 3})
        assert search.status_code == 200
        payload = search.json()
        assert payload["answer"] is None
        assert payload["excerpt_policy"] == "local_research"
        assert payload["result_count"] > 0
        assert payload["results"][0]["text"]

        listing = client.get("/api/v1/documents?page_size=5")
        assert listing.status_code == 200
        assert listing.json()["total"] == 89
        assert len(listing.json()["items"]) == 5


def test_public_mode_blocks_unclear_pdf_and_excerpt(tmp_path):
    from fastapi.testclient import TestClient

    database_url = f"sqlite+pysqlite:///{tmp_path / 'public.db'}"
    app = create_app(make_settings(database_url, public_mode=True), PhaseERepository(ROOT))
    with TestClient(app) as client:
        search = client.post("/api/v1/search", json={"query": "hồ chứa", "top_k": 1})
        assert search.status_code == 200
        result = search.json()["results"][0]
        assert result["text"] is None
        assert result["pdf_available"] is False

        readiness = client.get("/api/v1/readiness").json()
        assert readiness["source"] == "verified release snapshot"
        assert "manifest_path" not in readiness["canonical_corpus"]
        assert "paths_read" not in readiness["v3_2_frozen"]
        assert "semantic_duplicate_quarantine_ids" not in readiness["v4_candidate_expansion"]
        assert "candidate_schema_issues" not in readiness["validation"]
        assert all("qa_id" not in query for query in readiness["phase_e_demo"]["queries"])

        report = client.get("/api/v1/report").json()
        assert report["sources"] == ["verified release snapshot", "PostgreSQL"]
        assert all("qa_id" not in query for query in report["retrieval"]["demo_queries"])

        document_id = client.get("/api/v1/documents?page_size=1").json()["items"][0]["doc_id"]
        blocked = client.get(f"/api/v1/documents/{document_id}/pdf")
        assert blocked.status_code == 403


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required for PostgreSQL integration")
def test_postgresql_schema_and_seed_roundtrip():
    database_url = os.environ["TEST_DATABASE_URL"]
    assert database_url.startswith(("postgresql://", "postgresql+psycopg://"))
    engine = create_database_engine(database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with create_session_factory(engine)() as session:
        counts = seed_verified_artifacts(session, PhaseERepository(ROOT))
        assert counts["documents"] == 89
    Base.metadata.drop_all(engine)
    engine.dispose()
