from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from .bm25 import result_from_unit
from .io_utils import write_json
from .schema import RetrievalResult


class E5Retriever:
    def __init__(self, units: list[dict], cache_prefix: Path, corpus_sha256: str,
                 model_id: str = "intfloat/multilingual-e5-large", batch_size: int = 16,
                 max_length: int = 512, device: str | None = None):
        import torch
        from huggingface_hub import snapshot_download
        from sentence_transformers import SentenceTransformer

        self.units = units
        self.ids = np.asarray([row["evidence_id"] for row in units], dtype=object)
        self.model_id = model_id
        self.max_length = max_length
        self.initial_batch_size = batch_size
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model_path = Path(snapshot_download(model_id, local_files_only=True))
        self.revision = self.model_path.name
        self.model = SentenceTransformer(model_id, device=self.device, local_files_only=True)
        self.model.max_seq_length = max_length
        self.dimension = int(self.model.get_sentence_embedding_dimension())
        self._query_cache: dict[str, np.ndarray] = {}
        self.embedding_seconds = 0.0
        self.query_seconds = 0.0
        self.cache_hit = False
        embeddings_path = cache_prefix.with_suffix(".npy")
        metadata_path = cache_prefix.with_suffix(".json")
        expected = {"corpus_sha256": corpus_sha256, "model_id": model_id, "revision": self.revision,
                    "max_length": max_length, "count": len(units), "dimension": self.dimension,
                    "passage_prefix": "passage: ", "normalized": True}
        if embeddings_path.exists() and metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if all(metadata.get(key) == value for key, value in expected.items()):
                self.embeddings = np.load(embeddings_path, mmap_mode="r")
                self.metadata = metadata
                self.cache_hit = True
                return
        cache_prefix.parent.mkdir(parents=True, exist_ok=True)
        texts = ["passage: " + row["index_text"] for row in units]
        lengths = self._token_lengths(texts)
        self.embeddings, effective_batch = self._encode_adaptive(texts, batch_size)
        np.save(embeddings_path, self.embeddings.astype(np.float32))
        self.metadata = {**expected, "device": self.device, "initial_batch_size": batch_size,
                         "effective_batch_size": effective_batch,
                         "truncated_count": sum(length > max_length for length in lengths),
                         "truncated_rate": sum(length > max_length for length in lengths) / len(lengths),
                         "max_observed_tokens": max(lengths, default=0),
                         "embedding_seconds": self.embedding_seconds}
        write_json(metadata_path, self.metadata)

    def _token_lengths(self, texts: list[str]) -> list[int]:
        lengths = []
        for start in range(0, len(texts), 128):
            encoded = self.model.tokenizer(texts[start:start + 128], padding=False, truncation=False,
                                           add_special_tokens=True, return_length=True)
            lengths.extend(int(value) for value in encoded["length"])
        return lengths

    def _encode_adaptive(self, texts: list[str], batch_size: int) -> tuple[np.ndarray, int]:
        import torch
        while batch_size >= 1:
            try:
                started = time.perf_counter()
                vectors = self.model.encode(texts, batch_size=batch_size, show_progress_bar=True,
                                            normalize_embeddings=True, convert_to_numpy=True)
                if self.device == "cuda":
                    torch.cuda.synchronize()
                self.embedding_seconds = time.perf_counter() - started
                return np.asarray(vectors, dtype=np.float32), batch_size
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                batch_size //= 2
        raise RuntimeError("E5 encoding failed even at batch_size=1")

    def encode_query(self, query: str) -> np.ndarray:
        if query in self._query_cache:
            return self._query_cache[query]
        import torch
        started = time.perf_counter()
        vector = self.model.encode(["query: " + query], batch_size=1, show_progress_bar=False,
                                   normalize_embeddings=True, convert_to_numpy=True)[0].astype(np.float32)
        if self.device == "cuda":
            torch.cuda.synchronize()
        self.query_seconds += time.perf_counter() - started
        self._query_cache[query] = vector
        return vector

    def score_all(self, query: str) -> np.ndarray:
        return np.asarray(self.embeddings @ self.encode_query(query), dtype=np.float64)

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

