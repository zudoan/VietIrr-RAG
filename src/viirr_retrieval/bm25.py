from __future__ import annotations

import math
import pickle
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .schema import RetrievalResult
from .tokenization import tokenize


class BM25Retriever:
    def __init__(self, units: list[dict], cache_path: Path, corpus_sha256: str,
                 k1: float = 1.5, b: float = 0.75):
        self.units = units
        self.ids = np.asarray([row["evidence_id"] for row in units], dtype=object)
        self.k1, self.b = k1, b
        self.cache_path = cache_path
        self.build_seconds = 0.0
        self.cache_hit = False
        self._score_cache: dict[str, np.ndarray] = {}
        if cache_path.exists():
            with cache_path.open("rb") as handle:
                cached = pickle.load(handle)
            if cached.get("corpus_sha256") == corpus_sha256 and cached.get("ids") == list(self.ids):
                self.doc_lengths = cached["doc_lengths"]
                self.avgdl = cached["avgdl"]
                self.postings = cached["postings"]
                self.cache_hit = True
                return
        started = time.perf_counter()
        tokenized = [tokenize(row["index_text"]) for row in units]
        self.doc_lengths = np.asarray([len(tokens) for tokens in tokenized], dtype=np.float32)
        self.avgdl = float(self.doc_lengths.mean()) if len(self.doc_lengths) else 0.0
        raw_postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for index, tokens in enumerate(tokenized):
            for token, frequency in Counter(tokens).items():
                raw_postings[token].append((index, frequency))
        total = len(units)
        self.postings = {}
        for token, values in raw_postings.items():
            indexes = np.asarray([item[0] for item in values], dtype=np.int32)
            frequencies = np.asarray([item[1] for item in values], dtype=np.float32)
            df = len(values)
            idf = math.log(1.0 + (total - df + 0.5) / (df + 0.5))
            self.postings[token] = (indexes, frequencies, idf)
        self.build_seconds = time.perf_counter() - started
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("wb") as handle:
            pickle.dump({"corpus_sha256": corpus_sha256, "ids": list(self.ids),
                         "doc_lengths": self.doc_lengths, "avgdl": self.avgdl,
                         "postings": self.postings}, handle, protocol=pickle.HIGHEST_PROTOCOL)

    def score_all(self, query: str) -> np.ndarray:
        if query in self._score_cache:
            return self._score_cache[query]
        scores = np.zeros(len(self.units), dtype=np.float64)
        for token, query_frequency in Counter(tokenize(query)).items():
            posting = self.postings.get(token)
            if posting is None:
                continue
            indexes, frequencies, idf = posting
            norm = frequencies + self.k1 * (1.0 - self.b + self.b * self.doc_lengths[indexes] / self.avgdl)
            scores[indexes] += query_frequency * idf * frequencies * (self.k1 + 1.0) / norm
        self._score_cache[query] = scores
        return scores

    def rank_indices(self, query: str, top_k: int | None = None,
                     candidates: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        scores = self.score_all(query)
        indexes = np.arange(len(self.units), dtype=np.int32) if candidates is None else np.asarray(candidates, dtype=np.int32)
        order = np.lexsort((self.ids[indexes], -scores[indexes]))
        ranked = indexes[order]
        if top_k is not None:
            ranked = ranked[:top_k]
        return ranked, scores[ranked]

    def retrieve(self, query: str, top_k: int) -> list[RetrievalResult]:
        indexes, scores = self.rank_indices(query, top_k)
        return [result_from_unit(self.units[int(index)], float(score), rank)
                for rank, (index, score) in enumerate(zip(indexes, scores), 1)]


def result_from_unit(unit: dict, score: float, rank: int) -> RetrievalResult:
    return RetrievalResult(evidence_id=unit["evidence_id"], doc_id=unit["doc_id"],
                           page_id=unit["page_id"], page_number=int(unit["page_number"]),
                           unit_type=unit.get("unit_type", "PAGE"), score=score, rank=rank)

