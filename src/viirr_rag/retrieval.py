from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from viirr_retrieval.bm25 import BM25Retriever
from viirr_retrieval.dense import E5Retriever
from viirr_retrieval.fusion import reciprocal_rank_fusion
from viirr_retrieval.windowed import build_page_windows, deterministic_id_hash, page_max_scores

from .pipeline import Evidence, expand_grounded_evidence, expand_table_evidence


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def fusion_order(
    ids: list[str],
    first_scores: np.ndarray,
    second_scores: np.ndarray,
    candidates: np.ndarray | None = None,
    top_k: int | None = None,
    rrf_k: int = 60,
) -> tuple[list[int], list[float]]:
    indexes = np.arange(len(ids), dtype=np.int32) if candidates is None else np.asarray(candidates, dtype=np.int32)
    id_array = np.asarray(ids, dtype=object)
    first_order = indexes[np.lexsort((id_array[indexes], -first_scores[indexes]))]
    second_order = indexes[np.lexsort((id_array[indexes], -second_scores[indexes]))]
    fused = reciprocal_rank_fusion(
        [[str(id_array[index]) for index in first_order], [str(id_array[index]) for index in second_order]],
        rrf_k,
        top_k,
    )
    id_to_index = {item_id: index for index, item_id in enumerate(ids)}
    return [id_to_index[item_id] for item_id, _ in fused], [float(score) for _, score in fused]


class WindowedPageRegionRetriever:
    """Frozen P2 B3: window-max page hybrid Top-10 then region hybrid."""

    def __init__(self, root: Path):
        self.root = root
        self.pages_path = root / "outputs/V4_EXPERIMENT/index/pages_v4.jsonl"
        self.units_path = root / "outputs/V4_EXPERIMENT/index/evidence_units_v4.jsonl"
        self.pages = read_jsonl(self.pages_path)
        self.units = read_jsonl(self.units_path)
        self.page_ids = [str(row["page_id"]) for row in self.pages]
        self.evidence_ids = [str(row["evidence_id"]) for row in self.units]
        self.page_by_pair = {(str(row["doc_id"]), int(row["page_number"])): row for row in self.pages}
        self.page_to_unit_indexes: dict[str, list[int]] = defaultdict(list)
        self.document_to_unit_indexes: dict[str, list[int]] = defaultdict(list)
        for index, unit in enumerate(self.units):
            self.page_to_unit_indexes[str(unit["page_id"])].append(index)
            self.document_to_unit_indexes[str(unit["doc_id"])].append(index)

        page_units = [{**row, "evidence_id": row["page_id"], "unit_type": "PAGE"} for row in self.pages]
        self.region_bm25 = BM25Retriever(
            self.units,
            root / "outputs/V4_EXPERIMENT/cache/bm25_regions.pkl",
            sha256(self.units_path),
            1.5,
            0.75,
        )
        self.page_bm25 = BM25Retriever(
            page_units,
            root / "outputs/V4_EXPERIMENT/cache/bm25_pages.pkl",
            sha256(self.pages_path),
            1.5,
            0.75,
        )
        self.region_dense = E5Retriever(
            self.units,
            root / "outputs/V4_EXPERIMENT/cache/e5_regions",
            sha256(self.units_path),
            model_id="intfloat/multilingual-e5-large",
            batch_size=16,
            max_length=512,
        )
        expected_revision = "3d7cfbdacd47fdda877c5cd8a79fbcc4f2a574f3"
        if self.region_dense.revision != expected_revision:
            raise RuntimeError("E5 revision differs from frozen P1/P2 configuration")
        windows, self.window_page_indexes, _ = build_page_windows(
            self.pages, self.region_dense.model.tokenizer, content_tokens=384, overlap=128
        )
        metadata_path = root / "outputs/P2_CONTROLLED_ROUTING/cache/e5_page_windows.json"
        embeddings_path = root / "outputs/P2_CONTROLLED_ROUTING/cache/e5_page_windows.npy"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        checks = {
            "pages_sha256": sha256(self.pages_path),
            "model_id": self.region_dense.model_id,
            "model_revision": self.region_dense.revision,
            "content_tokens": 384,
            "overlap_tokens": 128,
            "window_count": len(windows),
            "window_ids_sha256": deterministic_id_hash([window.window_id for window in windows]),
        }
        mismatches = [key for key, value in checks.items() if metadata.get(key) != value]
        if mismatches:
            raise RuntimeError(f"Frozen P2 window cache mismatch: {mismatches}")
        self.window_embeddings = np.load(embeddings_path, mmap_mode="r")
        if len(self.window_embeddings) != len(windows):
            raise RuntimeError("Frozen P2 window embedding count mismatch")

    def _score(self, question: str) -> dict[str, Any]:
        import torch

        started = time.perf_counter()
        vector = self.region_dense.encode_query(question)
        if self.region_dense.device == "cuda":
            torch.cuda.synchronize()
        page_bm_scores = self.page_bm25.score_all(question)
        window_scores = np.asarray(self.window_embeddings @ vector, dtype=np.float64)
        page_dense_scores = page_max_scores(window_scores, self.page_ids, self.window_page_indexes)
        page_indexes, page_scores = fusion_order(self.page_ids, page_bm_scores, page_dense_scores)
        region_bm_scores = self.region_bm25.score_all(question)
        region_dense_scores = np.asarray(self.region_dense.embeddings @ vector, dtype=np.float64)
        return {
            "page_indexes": page_indexes,
            "page_scores": page_scores,
            "region_bm_scores": region_bm_scores,
            "region_dense_scores": region_dense_scores,
            "scoring_ms": (time.perf_counter() - started) * 1000,
        }

    def _evidence_rows(
        self,
        indexes: list[int],
        scores: list[float],
        source: str,
    ) -> list[Evidence]:
        rows = []
        for rank, (index, score) in enumerate(zip(indexes, scores), 1):
            unit = self.units[index]
            rows.append(
                Evidence(
                    rank=rank,
                    evidence_id=str(unit["evidence_id"]),
                    doc_id=str(unit["doc_id"]),
                    page_id=str(unit["page_id"]),
                    page_number=int(unit["page_number"]),
                    unit_type=str(unit.get("unit_type") or "UNKNOWN"),
                    score=float(score),
                    text=str(unit.get("raw_text") or unit.get("index_text") or ""),
                    source=source,
                )
            )
        return rows

    def retrieve(self, question: str, region_top_k: int = 50) -> dict[str, Any]:
        scored = self._score(question)
        selected_pages = [self.page_ids[index] for index in scored["page_indexes"][:10]]
        candidates = np.asarray(
            sorted(
                {
                    index
                    for page_id in selected_pages
                    for index in self.page_to_unit_indexes.get(page_id, [])
                }
            ),
            dtype=np.int32,
        )
        indexes, scores = fusion_order(
            self.evidence_ids,
            scored["region_bm_scores"],
            scored["region_dense_scores"],
            candidates=candidates,
            top_k=region_top_k,
        )
        return {
            "evidence": self._evidence_rows(indexes, scores, "retrieved_b3_window_top10"),
            "selected_page_ids": selected_pages,
            "latency_ms": scored["scoring_ms"],
        }

    def reference_page_context(
        self,
        question: str,
        reference_pairs: list[tuple[str, int]],
        region_top_k: int = 80,
    ) -> dict[str, Any]:
        scored = self._score(question)
        page_ids = []
        for pair in reference_pairs:
            page = self.page_by_pair.get(pair)
            if page is None:
                raise KeyError(f"Reference page is absent from index: {pair}")
            page_ids.append(str(page["page_id"]))
        candidates = np.asarray(
            sorted({index for page_id in page_ids for index in self.page_to_unit_indexes.get(page_id, [])}),
            dtype=np.int32,
        )
        indexes, scores = fusion_order(
            self.evidence_ids,
            scored["region_bm_scores"],
            scored["region_dense_scores"],
            candidates=candidates,
            top_k=region_top_k,
        )
        return {
            "evidence": self._evidence_rows(indexes, scores, "reference_page_context"),
            "selected_page_ids": page_ids,
            "latency_ms": scored["scoring_ms"],
        }

    def expand_table_context(self, evidence: list[Evidence]) -> list[Evidence]:
        page_ids = {item.page_id for item in evidence}
        indexes = [
            index
            for page_id in page_ids
            for index in self.page_to_unit_indexes.get(page_id, [])
        ]
        page_evidence = self._evidence_rows(
            indexes,
            [0.0] * len(indexes),
            "same_page_context_pool",
        )
        return expand_table_evidence(evidence, page_evidence)

    def expand_grounded_context(self, evidence: list[Evidence], question: str) -> list[Evidence]:
        document_ids = {item.doc_id for item in evidence}
        indexes = [
            index
            for document_id in document_ids
            for index in self.document_to_unit_indexes.get(document_id, [])
        ]
        document_evidence = self._evidence_rows(
            indexes,
            [0.0] * len(indexes),
            "document_context_pool",
        )
        return expand_grounded_evidence(evidence, document_evidence, question)

    def close(self) -> None:
        import gc

        try:
            import torch

            del self.region_dense.model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        finally:
            gc.collect()
