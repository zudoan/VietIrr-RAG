"""Dependency-light HTTP API over the frozen VietIrr retrieval artifacts.

The adapter intentionally exposes evidence retrieval, not generated answers.  It reads
the canonical corpus and the existing BM25 cache without modifying research outputs.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
import time
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from viirr_retrieval.bm25 import BM25Retriever  # noqa: E402
from viirr_retrieval.io_utils import read_jsonl, sha256  # noqa: E402


_MOJIBAKE_MARKERS = ("Ã", "Ä", "Æ", "Â", "â€", "á»", "áº")


def _mojibake_score(value: str) -> int:
    return sum(value.count(marker) for marker in _MOJIBAKE_MARKERS)


def repair_text(value: Any) -> Any:
    """Repair the legacy double-decoded UTF-8 metadata on output only."""
    if not isinstance(value, str) or not any(marker in value for marker in _MOJIBAKE_MARKERS):
        return value
    best = value
    for _ in range(2):
        candidates = [best]
        for encoding in ("cp1252", "latin1"):
            try:
                candidates.append(best.encode(encoding).decode("utf-8"))
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        candidate = min(candidates, key=lambda item: (_mojibake_score(item), -len(item)))
        if _mojibake_score(candidate) >= _mojibake_score(best):
            break
        best = candidate
    return best


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _safe_int(value: str | None, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


class PhaseERepository:
    """In-memory metadata plus the existing corpus BM25 index."""

    def __init__(self, root: Path = ROOT) -> None:
        self.root = root.resolve()
        self.units_path = self.root / "data" / "processed" / "evidence_units.jsonl"
        self.documents_path = self.root / "data" / "v3_1" / "metadata" / "documents.jsonl"
        self.stats_path = self.root / "reports" / "v3_2_final_semantic" / "dataset_stats.json"
        self.readiness_path = self.root / "reports" / "v3_2_final_semantic" / "V3_2_FINAL_SEMANTIC_READINESS.json"
        self.manifest_path = self.root / "data" / "processed" / "B1_INPUT_MANIFEST.json"
        for path in (self.units_path, self.documents_path, self.stats_path, self.readiness_path, self.manifest_path):
            if not path.exists():
                raise FileNotFoundError(f"Required Phase E artifact is missing: {path}")

        self.started_at = time.time()
        self.units = read_jsonl(self.units_path)
        self.unit_by_id = {row["evidence_id"]: row for row in self.units}
        self.units_by_doc: dict[str, list[dict[str, Any]]] = {}
        for unit in self.units:
            self.units_by_doc.setdefault(unit["doc_id"], []).append(unit)
        self.documents = read_jsonl(self.documents_path)
        self.document_by_id = {row["doc_id"]: row for row in self.documents}
        self.stats_data = _read_json(self.stats_path)
        self.readiness = _read_json(self.readiness_path)
        self.manifest = _read_json(self.manifest_path)
        self.retriever = BM25Retriever(
            self.units,
            self.root / "outputs" / "B2" / "cache" / "bm25_regions.pkl",
            sha256(self.units_path),
        )

    def status(self) -> dict[str, Any]:
        counts = self.manifest["counts"]
        return {
            "status": "ready",
            "service": "VietIrr Evidence API",
            "mode": "EVIDENCE_SEARCH",
            "answer_generation": False,
            "retrieval_method": "BM25_B1_FROZEN_CORPUS",
            "corpus_version": self.stats_data.get("canonical_stats_version", "UNKNOWN"),
            "index_cache": "hit" if self.retriever.cache_hit else "rebuilt",
            "evidence_units": counts["evidence_units"],
            "uptime_seconds": round(time.time() - self.started_at, 1),
        }

    def stats(self) -> dict[str, Any]:
        corpus = self.stats_data["corpus"]
        qa = self.stats_data["qa"]
        negatives = self.stats_data["negatives"]
        return {
            "corpus_version": self.stats_data["canonical_stats_version"],
            "frozen": bool(self.readiness.get("DATASET_FROZEN")),
            "human_validated": bool(self.stats_data.get("human_validated")),
            "documents": corpus["documents"],
            "pages": corpus["pages"],
            "regions": corpus["regions"],
            "tables": corpus["tables"],
            "evidence_units": self.manifest["counts"]["evidence_units"],
            "qa_total": qa["total"],
            "qa_core": qa["core"],
            "qa_challenge": qa["challenge"],
            "source_grounded_negatives": negatives["source_grounded"],
            "retrieval_method": "BM25_B1_FROZEN_CORPUS",
        }

    def _document_view(self, document: dict[str, Any], include_detail: bool = False) -> dict[str, Any]:
        local = (self.root / str(document.get("local_path", ""))).resolve()
        pdf_available = local.is_file() and (local == self.root or self.root in local.parents)
        view = {
            "doc_id": document["doc_id"],
            "title": repair_text(document.get("title") or document["doc_id"]),
            "doc_type": repair_text(document.get("doc_type") or "Không xác định"),
            "source_agency": repair_text(document.get("source_agency") or "Không xác định"),
            "source_domain": document.get("source_domain"),
            "source_url": document.get("source_url"),
            "publication_date": document.get("publication_date"),
            "page_count": document.get("page_count"),
            "core_or_temporal": document.get("core_or_temporal"),
            "basin": [repair_text(item) for item in (document.get("basin") or [])],
            "province": [repair_text(item) for item in (document.get("province") or [])],
            "acceptance_status": document.get("acceptance_status"),
            "redistribution_status": document.get("redistribution_status"),
            "pdf_available": pdf_available,
            "pdf_url": f"/api/documents/{document['doc_id']}/pdf" if pdf_available else None,
        }
        if include_detail:
            units = sorted(self.units_by_doc.get(document["doc_id"], []),
                           key=lambda row: (int(row["page_number"]), row["evidence_id"]))
            view.update({
                "document_number": document.get("document_number"),
                "effective_date": document.get("effective_date"),
                "reporting_period": document.get("document_reporting_period"),
                "landing_page_url": document.get("landing_page_url"),
                "version_status": document.get("version_status"),
                "is_scanned": document.get("is_scanned"),
                "ocr_used": document.get("ocr_used"),
                "human_validated": document.get("human_validated", False),
                "evidence_count": len(units),
                "regions": [{
                    "evidence_id": unit["evidence_id"],
                    "page_number": unit["page_number"],
                    "unit_type": unit["unit_type"],
                    "text": repair_text(unit.get("raw_text") or unit.get("index_text") or ""),
                } for unit in units[:8]],
            })
        return view

    def list_documents(self, query: str = "", doc_type: str = "", page: int = 1,
                       page_size: int = 24) -> dict[str, Any]:
        needle = query.casefold().strip()
        type_filter = doc_type.casefold().strip()
        rows = []
        for document in self.documents:
            view = self._document_view(document)
            haystack = " ".join(str(view.get(key) or "") for key in
                                ("title", "doc_type", "source_agency", "doc_id")).casefold()
            if needle and needle not in haystack:
                continue
            if type_filter and str(view["doc_type"]).casefold() != type_filter:
                continue
            rows.append(view)
        rows.sort(key=lambda item: (item.get("publication_date") or "", item["title"]), reverse=True)
        start = (page - 1) * page_size
        types = sorted({repair_text(doc.get("doc_type") or "Không xác định") for doc in self.documents})
        return {
            "items": rows[start:start + page_size],
            "total": len(rows),
            "page": page,
            "page_size": page_size,
            "types": types,
        }

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        document = self.document_by_id.get(doc_id)
        return self._document_view(document, include_detail=True) if document else None

    def pdf_path(self, doc_id: str) -> Path | None:
        document = self.document_by_id.get(doc_id)
        if not document or not document.get("local_path"):
            return None
        path = (self.root / document["local_path"]).resolve()
        if self.root not in path.parents or not path.is_file() or path.suffix.lower() != ".pdf":
            return None
        return path

    def search(self, query: str, top_k: int = 8) -> dict[str, Any]:
        query = re.sub(r"\s+", " ", query).strip()
        if len(query) < 2:
            raise ValueError("Truy vấn cần ít nhất 2 ký tự.")
        started = time.perf_counter()
        ranked = [result for result in self.retriever.retrieve(query, min(top_k, 20)) if result.score > 0]
        top_score = ranked[0].score if ranked else 1.0
        items = []
        for result in ranked:
            unit = self.unit_by_id[result.evidence_id]
            document = self.document_by_id.get(result.doc_id, {"doc_id": result.doc_id})
            text = repair_text(unit.get("raw_text") or unit.get("index_text") or "")
            items.append({
                **asdict(result),
                "score": round(result.score, 6),
                "relevance": round(result.score / top_score, 4),
                "text": text,
                "title": repair_text(document.get("title") or result.doc_id),
                "source_agency": repair_text(document.get("source_agency") or "Không xác định"),
                "source_url": document.get("source_url"),
                "doc_type": repair_text(document.get("doc_type") or "Không xác định"),
                "pdf_available": self.pdf_path(result.doc_id) is not None,
                "pdf_url": (f"/api/documents/{result.doc_id}/pdf#page={result.page_number}"
                            if self.pdf_path(result.doc_id) else None),
            })
        return {
            "query": query,
            "mode": "EVIDENCE_SEARCH",
            "answer": None,
            "answer_notice": "Không có LLM trong workspace; hệ thống chỉ trả về bằng chứng truy xuất.",
            "retrieval_method": "BM25_B1_FROZEN_CORPUS",
            "result_count": len(items),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "results": items,
        }


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def make_handler(repository: PhaseERepository):
    class PhaseEHandler(BaseHTTPRequestHandler):
        server_version = "VietIrrEvidence/1.0"

        def log_message(self, format: str, *args: Any) -> None:
            sys.stderr.write("[phase-e-api] " + format % args + "\n")

        def _headers(self, status: int, content_type: str, length: int | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", os.getenv("VIETIRR_CORS_ORIGIN", "http://localhost:5173"))
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            if length is not None:
                self.send_header("Content-Length", str(length))
            self.end_headers()

        def _send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
            body = _json_bytes(payload)
            self._headers(status, "application/json; charset=utf-8", len(body))
            self.wfile.write(body)

        def _send_error_json(self, message: str, status: int) -> None:
            self._send_json({"error": message, "status": status}, status)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._headers(HTTPStatus.NO_CONTENT, "text/plain", 0)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            params = parse_qs(parsed.query)
            try:
                if path == "/api/health":
                    self._send_json(repository.status())
                    return
                if path == "/api/stats":
                    self._send_json(repository.stats())
                    return
                if path == "/api/documents":
                    self._send_json(repository.list_documents(
                        query=params.get("q", [""])[0],
                        doc_type=params.get("type", [""])[0],
                        page=_safe_int(params.get("page", ["1"])[0], 1, 1, 10_000),
                        page_size=_safe_int(params.get("page_size", ["24"])[0], 24, 1, 100),
                    ))
                    return
                pdf_match = re.fullmatch(r"/api/documents/([^/]+)/pdf", path)
                if pdf_match:
                    pdf = repository.pdf_path(pdf_match.group(1))
                    if not pdf:
                        self._send_error_json("PDF không khả dụng trong workspace.", HTTPStatus.NOT_FOUND)
                        return
                    self._send_file(pdf)
                    return
                doc_match = re.fullmatch(r"/api/documents/([^/]+)", path)
                if doc_match:
                    document = repository.get_document(doc_match.group(1))
                    if document is None:
                        self._send_error_json("Không tìm thấy tài liệu.", HTTPStatus.NOT_FOUND)
                    else:
                        self._send_json(document)
                    return
                self._send_error_json("Endpoint không tồn tại.", HTTPStatus.NOT_FOUND)
            except Exception as exc:  # pragma: no cover - defensive server boundary
                self._send_error_json(f"Lỗi dịch vụ: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)

        def _send_file(self, path: Path) -> None:
            size = path.stat().st_size
            range_header = self.headers.get("Range")
            start, end = 0, size - 1
            status = HTTPStatus.OK
            if range_header:
                match = re.match(r"bytes=(\d*)-(\d*)", range_header)
                if match:
                    start = int(match.group(1) or 0)
                    end = min(int(match.group(2) or size - 1), size - 1)
                    status = HTTPStatus.PARTIAL_CONTENT
            length = max(0, end - start + 1)
            self.send_response(status)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/pdf")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with path.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining:
                    chunk = handle.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/search":
                self._send_error_json("Endpoint không tồn tại.", HTTPStatus.NOT_FOUND)
                return
            try:
                length = _safe_int(self.headers.get("Content-Length"), 0, 0, 64 * 1024)
                payload = json.loads(self.rfile.read(length) or b"{}")
                query = str(payload.get("query") or "")
                top_k = _safe_int(str(payload.get("top_k", 8)), 8, 1, 20)
                self._send_json(repository.search(query, top_k))
            except ValueError as exc:
                self._send_error_json(str(exc), HTTPStatus.BAD_REQUEST)
            except json.JSONDecodeError:
                self._send_error_json("JSON không hợp lệ.", HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # pragma: no cover
                self._send_error_json(f"Lỗi dịch vụ: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)

    return PhaseEHandler


def create_server(host: str = "127.0.0.1", port: int = 8000,
                  root: Path = ROOT) -> ThreadingHTTPServer:
    repository = PhaseERepository(root)
    server = ThreadingHTTPServer((host, port), make_handler(repository))
    server.repository = repository  # type: ignore[attr-defined]
    return server


def main() -> None:
    host = os.getenv("VIETIRR_API_HOST", "127.0.0.1")
    port = int(os.getenv("VIETIRR_API_PORT", "8000"))
    server = create_server(host, port)
    print(f"VietIrr Evidence API ready at http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
