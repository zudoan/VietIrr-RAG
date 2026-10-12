from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass(frozen=True)
class RetrievalResult:
    evidence_id: str
    doc_id: str
    page_id: str
    page_number: int
    unit_type: str
    score: float
    rank: int

    def to_dict(self) -> dict:
        return asdict(self)


class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int) -> list[RetrievalResult]: ...

