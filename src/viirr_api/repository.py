"""Read-only access to the verified VietIrr artifacts and live BM25 index."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from viirr_retrieval.bm25 import BM25Retriever
from viirr_retrieval.io_utils import read_jsonl, sha256

from .settings import ROOT


_MOJIBAKE_MARKERS = ("Ã", "Ä", "Æ", "Â", "â€", "á»", "áº")


def _mojibake_score(value: str) -> int:
    return sum(value.count(marker) for marker in _MOJIBAKE_MARKERS)


def repair_text(value: Any) -> Any:
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


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


class PhaseERepository:
    """In-memory metadata plus the existing frozen-corpus BM25 index."""

    def __init__(self, root: Path = ROOT) -> None:
        self.root = root.resolve()
        self.units_path = self.root / "data" / "processed" / "evidence_units.jsonl"
        self.documents_path = self.root / "data" / "v3_1" / "metadata" / "documents.jsonl"
        self.stats_path = self.root / "reports" / "v3_2_final_semantic" / "dataset_stats.json"
        self.readiness_path = self.root / "reports" / "v3_2_final_semantic" / "V3_2_FINAL_SEMANTIC_READINESS.json"
        self.manifest_path = self.root / "data" / "processed" / "B1_INPUT_MANIFEST.json"
        self.snapshot_path = self.root / "READINESS_COUNTS.json"
        required = (self.units_path, self.documents_path, self.stats_path, self.readiness_path, self.manifest_path)
        for path in required:
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
        self.stats_data = read_json(self.stats_path)
        self.readiness = read_json(self.readiness_path)
        self.manifest = read_json(self.manifest_path)
        self.snapshot = read_json(self.snapshot_path) if self.snapshot_path.exists() else {}
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

    def document_view(self, document: dict[str, Any], include_detail: bool = False) -> dict[str, Any]:
        local = (self.root / str(document.get("local_path", ""))).resolve()
        pdf_available = local.is_file() and self.root in local.parents
        view: dict[str, Any] = {
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
            "redistribution_status": document.get("redistribution_status") or "UNCLEAR",
            "pdf_available": pdf_available,
            "pdf_url": f"/api/v1/documents/{document['doc_id']}/pdf" if pdf_available else None,
        }
        if include_detail:
            units = sorted(
                self.units_by_doc.get(document["doc_id"], []),
                key=lambda row: (int(row["page_number"]), row["evidence_id"]),
            )
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

    def list_documents(self, query: str = "", doc_type: str = "", page: int = 1, page_size: int = 24) -> dict[str, Any]:
        needle = query.casefold().strip()
        type_filter = doc_type.casefold().strip()
        rows = []
        for document in self.documents:
            view = self.document_view(document)
            haystack = " ".join(str(view.get(key) or "") for key in ("title", "doc_type", "source_agency", "doc_id")).casefold()
            if needle and needle not in haystack:
                continue
            if type_filter and str(view["doc_type"]).casefold() != type_filter:
                continue
            rows.append(view)
        rows.sort(key=lambda item: (item.get("publication_date") or "", item["title"]), reverse=True)
        start = (page - 1) * page_size
        types = sorted({repair_text(doc.get("doc_type") or "Không xác định") for doc in self.documents})
        return {"items": rows[start:start + page_size], "total": len(rows), "page": page, "page_size": page_size, "types": types}

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        document = self.document_by_id.get(doc_id)
        return self.document_view(document, include_detail=True) if document else None

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
        if len(query) > 500:
            raise ValueError("Truy vấn không được vượt quá 500 ký tự.")
        started = time.perf_counter()
        ranked = [result for result in self.retriever.retrieve(query, min(top_k, 20)) if result.score > 0]
        top_score = ranked[0].score if ranked else 1.0
        items = []
        for result in ranked:
            unit = self.unit_by_id[result.evidence_id]
            document = self.document_by_id.get(result.doc_id, {"doc_id": result.doc_id})
            items.append({
                **asdict(result),
                "score": round(result.score, 6),
                "relevance": round(result.score / top_score, 4),
                "text": repair_text(unit.get("raw_text") or unit.get("index_text") or ""),
                "title": repair_text(document.get("title") or result.doc_id),
                "source_agency": repair_text(document.get("source_agency") or "Không xác định"),
                "source_url": document.get("source_url"),
                "doc_type": repair_text(document.get("doc_type") or "Không xác định"),
                "redistribution_status": document.get("redistribution_status") or "UNCLEAR",
                "pdf_available": self.pdf_path(result.doc_id) is not None,
                "pdf_url": f"/api/v1/documents/{result.doc_id}/pdf#page={result.page_number}" if self.pdf_path(result.doc_id) else None,
            })
        return {
            "query": query,
            "mode": "EVIDENCE_SEARCH",
            "answer": None,
            "answer_notice": "Không có LLM trong hệ thống phục vụ; kết quả là bằng chứng truy xuất.",
            "retrieval_method": "BM25_B1_FROZEN_CORPUS",
            "corpus_version": self.stats_data.get("canonical_stats_version", "UNKNOWN"),
            "result_count": len(items),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "results": items,
        }
