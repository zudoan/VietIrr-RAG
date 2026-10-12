import json
import threading
import urllib.request
from pathlib import Path

from viirr_api.app import PhaseERepository, create_server, repair_text


ROOT = Path(__file__).resolve().parents[1]


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


def test_document_inventory_and_pdf_paths_are_scoped():
    repository = PhaseERepository(ROOT)
    listing = repository.list_documents(page_size=5)
    assert listing["total"] == 89
    assert len(listing["items"]) == 5
    assert all("pdf_available" in item for item in listing["items"])


def test_http_search_and_pdf_range_end_to_end():
    server = create_server("127.0.0.1", 0, ROOT)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/api/health") as response:
            health = json.load(response)
        assert health["status"] == "ready"

        payload = json.dumps({"query": "quy trình vận hành hồ chứa", "top_k": 3},
                             ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{base}/api/search", data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"}, method="POST",
        )
        with urllib.request.urlopen(request) as response:
            search = json.load(response)
        assert search["answer"] is None
        assert search["result_count"] > 0

        repository = server.repository
        pdf_document = next(doc for doc in repository.documents if repository.pdf_path(doc["doc_id"]))
        pdf_request = urllib.request.Request(
            f"{base}/api/documents/{pdf_document['doc_id']}/pdf",
            headers={"Range": "bytes=0-127"},
        )
        with urllib.request.urlopen(pdf_request) as response:
            assert response.status == 206
            assert response.headers["Content-Range"].startswith("bytes 0-127/")
            assert response.read(4) == b"%PDF"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
