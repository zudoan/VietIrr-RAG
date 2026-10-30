"""Retrieval Adapter for Stage 3 Evidence-Targeted Correction MVP.

Provides a narrow adapter to retrieve Page / Region evidence units without
modifying the frozen P1–P5 retrieval ranking algorithms.

Supports:
- MockRetrievalBackend: deterministic, reproducible fixture and shared candidate pool retrieval for testing.
- RealRetrievalBackend: live index integration using WindowedPageRegionRetriever with strict
  provenance validation, runtime dependency checking, and explicit blocker tracking.
"""

from __future__ import annotations

import importlib.util
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from viirr_ontology.schema.evidence import EvidenceItem


class BaseRetrievalBackend(ABC):
    """Abstract retrieval backend interface."""

    @abstractmethod
    def search_regions(
        self,
        query: str,
        top_k: int = 3,
        filter_doc_id: Optional[str] = None,
    ) -> list[EvidenceItem]:
        """Retrieve candidate evidence items matching the query."""
        raise NotImplementedError

    @property
    @abstractmethod
    def is_mock(self) -> bool:
        """Indicate whether the backend is deterministic mock or live retrieval."""
        raise NotImplementedError

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Indicate whether the backend is ready and operational."""
        raise NotImplementedError


class MockRetrievalBackend(BaseRetrievalBackend):
    """Deterministic, reproducible mock backend supporting:
    1. Pattern-based fixtures (for unit regression scenarios).
    2. Shared Candidate Pool (for fair, matched-case comparisons where both targeted
       and untargeted strategies query the exact same set of evidence candidates).
    """

    def __init__(self, index_fixtures: Optional[list[dict]] = None):
        self._fixtures = list(index_fixtures or [])
        self._shared_candidate_pool: list[EvidenceItem] = []

    @property
    def is_mock(self) -> bool:
        return True

    @property
    def is_available(self) -> bool:
        return True

    def register_fixture(
        self,
        query_pattern: str,
        items: list[EvidenceItem],
        filter_doc_id: Optional[str] = None,
    ) -> None:
        """Register a canned response for a specific regex query pattern."""
        self._fixtures.append({
            "pattern": query_pattern,
            "filter_doc_id": filter_doc_id,
            "items": items,
        })

    def add_response(
        self,
        query_pattern: str,
        items: list[EvidenceItem],
        filter_doc_id: Optional[str] = None,
    ) -> None:
        """Alias for register_fixture for backward and test compatibility."""
        self.register_fixture(query_pattern, items, filter_doc_id=filter_doc_id)

    def clear_fixtures(self) -> None:
        """Clear all registered pattern fixtures and shared pools."""
        self._fixtures.clear()
        self._shared_candidate_pool.clear()

    def register_candidate_pool(self, items: list[EvidenceItem]) -> None:
        """Register a shared candidate pool from which all retrieval strategies retrieve."""
        self._shared_candidate_pool = list(items)

    def search_regions(
        self,
        query: str,
        top_k: int = 3,
        filter_doc_id: Optional[str] = None,
    ) -> list[EvidenceItem]:
        # Mode A: If a shared candidate pool is active, retrieve strictly from the pool
        if self._shared_candidate_pool:
            query_words = set(re.findall(r"\w+", query.lower()))
            scored_candidates: list[tuple[float, EvidenceItem]] = []
            for item in self._shared_candidate_pool:
                if filter_doc_id and item.doc_id != filter_doc_id:
                    continue
                item_words = set(re.findall(r"\w+", (item.text or "").lower()))
                overlap = len(query_words & item_words)
                if overlap > 0:
                    scored_candidates.append((float(overlap), item))
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            return [it for _, it in scored_candidates[:top_k]]

        # Mode B: Pattern fixture matching
        results: list[EvidenceItem] = []
        for fix in self._fixtures:
            pattern = fix["pattern"]
            expected_doc = fix.get("filter_doc_id")
            if expected_doc and filter_doc_id and expected_doc != filter_doc_id:
                continue
            if re.search(pattern, query, flags=re.IGNORECASE):
                for it in fix["items"]:
                    if it not in results:
                        results.append(it)
                        if len(results) >= top_k:
                            return results
        return results


def convert_p5_evidence(
    evidence_rows: list[Any],
    top_k: int = 100,
    filter_doc_id: Optional[str] = None,
) -> list[EvidenceItem]:
    """Convert raw retrieval output rows (dicts or P5 Evidence objects) into EvidenceItem models.

    Preserves exact:
    - doc_id, document_number, document_version
    - page_id, page_number
    - evidence_id, region_id, bbox
    - source, publication_date, legal_status, rank, truncated
    - extra custom provenance metadata without fabricating defaults or overwriting source metadata.
    Rejects rows missing mandatory provenance identities (doc_id, page_number, evidence_id).
    """
    if not isinstance(evidence_rows, list):
        raise ValueError(
            f"Malformed retrieval response: 'evidence' field must be a list, got {type(evidence_rows).__name__}"
        )
    if len(evidence_rows) == 0:
        return []

    items: list[EvidenceItem] = []
    for r in evidence_rows:
        # Extract strict provenance fields without fabricating defaults
        doc_id = getattr(r, "doc_id", None) or (r.get("doc_id") if isinstance(r, dict) else None)
        page_num = (
            getattr(r, "page_number", None)
            or (r.get("page_number") if isinstance(r, dict) else None)
            or getattr(r, "page", None)
            or (r.get("page") if isinstance(r, dict) else None)
        )
        ev_id = getattr(r, "evidence_id", None) or (r.get("evidence_id") if isinstance(r, dict) else None)
        text = (
            getattr(r, "text", "")
            or getattr(r, "content", "")
            or (r.get("text") if isinstance(r, dict) else "")
            or (r.get("content") if isinstance(r, dict) else "")
        )
        score = getattr(r, "score", 0.0) if hasattr(r, "score") else (r.get("score", 0.0) if isinstance(r, dict) else 0.0)
        unit_type = getattr(r, "unit_type", "text") if hasattr(r, "unit_type") else (r.get("unit_type", "text") if isinstance(r, dict) else "text")
        context_group = getattr(r, "context_group", None) if hasattr(r, "context_group") else (r.get("context_group") if isinstance(r, dict) else None)
        context_role = getattr(r, "context_role", None) if hasattr(r, "context_role") else (r.get("context_role") if isinstance(r, dict) else None)

        # Reject missing mandatory provenance identities (doc_id, page_number >= 1, evidence_id)
        if not doc_id or not str(doc_id).strip():
            continue
        try:
            if page_num is None or int(page_num) < 1:
                continue
            page_int = int(page_num)
        except (ValueError, TypeError):
            continue
        if not ev_id or not str(ev_id).strip():
            continue

        doc_id_str = str(doc_id).strip()
        if filter_doc_id and doc_id_str != filter_doc_id:
            continue

        prov_meta = (
            getattr(r, "provenance", None)
            or getattr(r, "provenance_metadata", None)
            or (r.get("provenance") if isinstance(r, dict) else None)
            or (r.get("provenance_metadata") if isinstance(r, dict) else None)
            or {}
        )
        if isinstance(r, dict):
            extra_meta = {
                k: v
                for k, v in r.items()
                if k not in (
                    "doc_id", "page_number", "page", "evidence_id", "text", "content", "score",
                    "unit_type", "context_group", "context_role", "page_id", "source", "document_number",
                    "document_version", "region_id", "bbox", "publication_date", "legal_status", "rank", "truncated"
                )
            }
            if extra_meta:
                prov_meta = {**extra_meta, **prov_meta}

        page_id = (
            (r.get("page_id") if isinstance(r, dict) else None)
            or getattr(r, "page_id", None)
            or f"P{page_int}"
        )
        source = (
            (r.get("source") if isinstance(r, dict) else None)
            or getattr(r, "source", None)
            or "live_retriever"
        )
        doc_number = (
            (r.get("document_number") if isinstance(r, dict) else None)
            or getattr(r, "document_number", None)
        )
        doc_version = (
            (r.get("document_version") if isinstance(r, dict) else None)
            or getattr(r, "document_version", None)
        )
        region_id = (
            (r.get("region_id") if isinstance(r, dict) else None)
            or getattr(r, "region_id", None)
        )
        raw_bbox = (
            (r.get("bbox") if isinstance(r, dict) else None)
            or getattr(r, "bbox", None)
        )
        publication_date = (
            (r.get("publication_date") if isinstance(r, dict) else None)
            or getattr(r, "publication_date", None)
        )
        legal_status = (
            (r.get("legal_status") if isinstance(r, dict) else None)
            or getattr(r, "legal_status", None)
        )
        rank = (
            (r.get("rank") if isinstance(r, dict) else None)
            or getattr(r, "rank", None)
        )
        truncated = bool(
            (r.get("truncated") if isinstance(r, dict) else False)
            or getattr(r, "truncated", False)
        )

        items.append(EvidenceItem(
            evidence_id=str(ev_id).strip(),
            doc_id=doc_id_str,
            page_id=str(page_id).strip(),
            page_number=page_int,
            text=str(text or ""),
            score=float(score) if score is not None else None,
            content_type=str(unit_type).lower() if str(unit_type).lower() in ("text", "table", "legal_clause", "caption", "heading", "list", "page") else "text",
            context_group=context_group,
            context_role=context_role,
            source=str(source).strip(),
            provenance_metadata=dict(prov_meta) if isinstance(prov_meta, dict) else {},
            document_number=str(doc_number).strip() if doc_number else None,
            document_version=str(doc_version).strip() if doc_version else None,
            publication_date=str(publication_date).strip() if publication_date else None,
            legal_status=str(legal_status).strip() if legal_status else None,
            region_id=str(region_id).strip() if region_id else None,
            rank=int(rank) if rank is not None else None,
            truncated=truncated,
            bbox=tuple(float(x) for x in raw_bbox) if raw_bbox is not None and len(raw_bbox) == 4 else None,
        ))

        if len(items) >= top_k:
            break

    return items


class RealRetrievalBackend(BaseRetrievalBackend):
    """Live Page->Region retrieval backend integrating with the project's WindowedPageRegionRetriever.

    Strictly:
    - Verifies dependencies and index artifacts.
    - Never fabricates default doc_id, page_number, or synthetic evidence IDs.
    - Distinguishes UNAVAILABLE_MISSING_DEPENDENCIES, UNAVAILABLE_MISSING_INDEX,
      INITIALIZATION_ERROR, and SEARCH_EXECUTION_ERROR.
    - Never swallows runtime exceptions to falsely report empty successful results.
    """

    def __init__(
        self,
        root_dir: Optional[Path] = None,
        retriever_instance: Optional[Any] = None,
        retriever: Optional[Any] = None,
    ):
        self.root = root_dir or Path(".")
        self.status: str = "UNINITIALIZED"
        self.blocker_details: str = ""
        self._retriever: Any = retriever_instance if retriever_instance is not None else retriever

        if self._retriever is not None:
            self.status = "READY"
            return

        # 1. Check Python dependencies (PyTorch, transformers)
        torch_spec = importlib.util.find_spec("torch")
        transformers_spec = importlib.util.find_spec("transformers")
        if not torch_spec or not transformers_spec:
            self.status = "UNAVAILABLE_MISSING_DEPENDENCIES"
            self.blocker_details = "PyTorch or transformers package is not installed in the active environment."
            return

        # 2. Check index files
        pages_path = self.root / "outputs/V4_EXPERIMENT/index/pages_v4.jsonl"
        units_path = self.root / "outputs/V4_EXPERIMENT/index/evidence_units_v4.jsonl"
        if not pages_path.exists() or not units_path.exists():
            self.status = "UNAVAILABLE_MISSING_INDEX"
            self.blocker_details = (
                f"Missing required index files at: {pages_path} or {units_path}."
            )
            return

        # 3. Initialize frozen WindowedPageRegionRetriever
        try:
            from viirr_rag.retrieval import WindowedPageRegionRetriever  # type: ignore
            self._retriever = WindowedPageRegionRetriever(self.root)
            self.status = "READY"
        except Exception as e:
            self.status = "INITIALIZATION_ERROR"
            self.blocker_details = f"Failed to initialize WindowedPageRegionRetriever: {type(e).__name__}: {e}"

    @property
    def is_mock(self) -> bool:
        return False

    @property
    def is_available(self) -> bool:
        return self.status == "READY"

    def _convert_p5_evidence(
        self,
        evidence_rows: list[Any],
        top_k: int = 3,
        filter_doc_id: Optional[str] = None,
    ) -> list[EvidenceItem]:
        return convert_p5_evidence(evidence_rows, top_k=top_k, filter_doc_id=filter_doc_id)

    def search_regions(
        self,
        query: str,
        top_k: int = 3,
        filter_doc_id: Optional[str] = None,
    ) -> list[EvidenceItem]:
        if self.status != "READY":
            raise RuntimeError(
                f"RealRetrievalBackend is not operational. Status: {self.status}. Details: {self.blocker_details}"
            )

        try:
            # Execute search through frozen WindowedPageRegionRetriever
            raw_output = self._retriever.retrieve(question=query, region_top_k=max(top_k * 4, 20))

            # Strict P5 Contract Validation: must be a dict containing 'evidence' list
            if not isinstance(raw_output, dict):
                raise ValueError(
                    f"Malformed retrieval response: expected dict, got {type(raw_output).__name__}"
                )
            if "evidence" not in raw_output:
                raise ValueError(
                    "Malformed retrieval response: missing mandatory 'evidence' field in retriever response contract"
                )

            evidence_rows = raw_output["evidence"]
            if not isinstance(evidence_rows, list):
                raise ValueError(
                    f"Malformed retrieval response: 'evidence' field must be a list, got {type(evidence_rows).__name__}"
                )

            return convert_p5_evidence(evidence_rows, top_k=top_k, filter_doc_id=filter_doc_id)
        except Exception as e:
            if not isinstance(e, (ValueError, RuntimeError)):
                self.status = "SEARCH_EXECUTION_ERROR"
                self.blocker_details = f"Search execution failed: {type(e).__name__}: {e}"
            raise


class PageRegionRetrievalAdapter:
    """Narrow adapter coordinating corrective queries to the underlying backend."""

    def __init__(
        self,
        backend: Optional[BaseRetrievalBackend] = None,
        retrieval_backend: Optional[BaseRetrievalBackend] = None,
    ):
        self._backend = backend or retrieval_backend or MockRetrievalBackend()

    @property
    def backend(self) -> BaseRetrievalBackend:
        return self._backend

    def set_backend(self, backend: BaseRetrievalBackend) -> None:
        self._backend = backend

    def _convert_p5_evidence(
        self,
        evidence_rows: list[Any],
        top_k: int = 100,
        filter_doc_id: Optional[str] = None,
    ) -> list[EvidenceItem]:
        return convert_p5_evidence(evidence_rows, top_k=top_k, filter_doc_id=filter_doc_id)

    def search_regions(
        self,
        query: str,
        top_k: int = 3,
        filter_doc_id: Optional[str] = None,
    ) -> list[EvidenceItem]:
        return self._backend.search_regions(query=query, top_k=top_k, filter_doc_id=filter_doc_id)

