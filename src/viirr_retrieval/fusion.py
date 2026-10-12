from __future__ import annotations

import numpy as np

from .bm25 import result_from_unit
from .schema import RetrievalResult


def reciprocal_rank_fusion(rankings: list[list[str]], rrf_k: int = 60,
                           top_k: int | None = None) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, 1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (rrf_k + rank)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return ordered if top_k is None else ordered[:top_k]


def bounded_round_robin_union(rankings: list[list[str]], budget: int) -> list[str]:
    output, seen = [], set()
    position = 0
    while len(output) < budget and any(position < len(ranking) for ranking in rankings):
        for ranking in rankings:
            if position < len(ranking) and ranking[position] not in seen:
                seen.add(ranking[position])
                output.append(ranking[position])
                if len(output) == budget:
                    break
        position += 1
    return output


class RRFHybridRetriever:
    def __init__(self, units: list[dict], first, second, rrf_k: int = 60):
        self.units = units
        self.first, self.second, self.rrf_k = first, second, rrf_k
        self.ids = np.asarray([row["evidence_id"] for row in units], dtype=object)
        self.id_to_index = {item_id: index for index, item_id in enumerate(self.ids)}

    def rank_indices(self, query: str, top_k: int | None = None,
                     candidates: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        indexes = np.arange(len(self.units), dtype=np.int32) if candidates is None else np.asarray(candidates, dtype=np.int32)
        first, _ = self.first.rank_indices(query, candidates=indexes)
        second, _ = self.second.rank_indices(query, candidates=indexes)
        fused = reciprocal_rank_fusion([[str(self.ids[i]) for i in first], [str(self.ids[i]) for i in second]],
                                       self.rrf_k, top_k)
        ranked = np.asarray([self.id_to_index[item_id] for item_id, _ in fused], dtype=np.int32)
        scores = np.asarray([score for _, score in fused], dtype=np.float64)
        return ranked, scores

    def retrieve(self, query: str, top_k: int) -> list[RetrievalResult]:
        indexes, scores = self.rank_indices(query, top_k)
        return [result_from_unit(self.units[int(index)], float(score), rank)
                for rank, (index, score) in enumerate(zip(indexes, scores), 1)]


class PageRegionRetriever:
    def __init__(self, units: list[dict], pages: list[dict], page_retriever: RRFHybridRetriever,
                 region_retriever: RRFHybridRetriever, page_top_p: int = 10):
        self.units, self.pages = units, pages
        self.page_retriever, self.region_retriever = page_retriever, region_retriever
        self.page_top_p = page_top_p
        self.page_to_unit_indexes: dict[str, list[int]] = {}
        for index, unit in enumerate(units):
            self.page_to_unit_indexes.setdefault(unit["page_id"], []).append(index)

    def page_ranking(self, query: str, top_p: int = 100) -> list[RetrievalResult]:
        return self.page_retriever.retrieve(query, top_p)

    def candidate_indexes(self, selected_page_ids: list[str]) -> np.ndarray:
        indexes = sorted({index for page_id in selected_page_ids
                          for index in self.page_to_unit_indexes.get(page_id, [])})
        return np.asarray(indexes, dtype=np.int32)

    def retrieve_with_pages(self, query: str, selected_page_ids: list[str], top_k: int) -> list[RetrievalResult]:
        candidates = self.candidate_indexes(selected_page_ids)
        if not len(candidates):
            return []
        indexes, scores = self.region_retriever.rank_indices(query, top_k, candidates)
        return [result_from_unit(self.units[int(index)], float(score), rank)
                for rank, (index, score) in enumerate(zip(indexes, scores), 1)]

    def retrieve(self, query: str, top_k: int) -> list[RetrievalResult]:
        pages = self.page_ranking(query, self.page_top_p)
        return self.retrieve_with_pages(query, [row.page_id for row in pages], top_k)

