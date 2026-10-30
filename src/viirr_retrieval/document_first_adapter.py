"""
Automatic Document-First Retrieval Adapter for VietIRR-RAG.

Pipeline:
Step 1: Global Document Discovery:
        Uses hybrid fusion of:
        - BM25 on Document Titles & Descriptions
        - Dense similarity on Document Representative Text
        - Source-supported domain entity & regulation matching (NO references / NO oracle)
        Selects a bounded shortlist of top documents (k_doc = 3 to 5).

Step 2: Genuine Within-Document Page Retrieval:
        Gathers pages specifically from the selected document shortlist.
        Includes a safe global fallback if document selection confidence is low.

Step 3: Within-Document Page Candidate Ranking:
        Ranks pages using BM25 and Windowed E5 Max-pooling conditioned on the query.

Step 4: Query-Relevant Region Selection:
        Ranks regions within the top pages by technical entity, parameter, and keyword match.
"""

from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", str(text))
    return text.lower().strip()


@dataclass
class DocumentCandidate:
    doc_id: str
    title: str
    score: float
    rank: int
    match_reasons: list[str]


class AutomaticDocumentSelector:
    """
    Selects candidate documents autonomously using ONLY:
    - Original user query.
    - Official corpus document metadata (titles, agencies, basins, types).
    - Source-supported hydraulic entities and regulation regexes.
    NEVER uses expected answers, gold doc IDs, or benchmark reference labels.
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.doc_metadata: dict[str, dict[str, Any]] = {}
        self.doc_ids: list[str] = []
        self._load_corpus_metadata()

    def _load_corpus_metadata(self) -> None:
        quality_path = self.workspace / "reports/EXPERIMENTS/CORPUS_DOCUMENT_QUALITY.csv"
        if quality_path.exists():
            with open(quality_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    doc_id = r.get("doc_id")
                    if doc_id:
                        title = r.get("title", "")
                        basin = r.get("basin", "")
                        agency = r.get("agency", "")
                        doc_type = r.get("doc_type", "")
                        self.doc_metadata[doc_id] = {
                            "doc_id": doc_id,
                            "title": title,
                            "basin": basin,
                            "agency": agency,
                            "doc_type": doc_type,
                            "norm_title": normalize_text(title),
                            "norm_basin": normalize_text(basin),
                            "norm_agency": normalize_text(agency),
                            "canonical_pages": int(r.get("canonical_pages", 1) or 1),
                        }
        self.doc_ids = sorted(self.doc_metadata.keys())

    def select_documents(
        self,
        query: str,
        page_bm25_scores: np.ndarray,
        page_dense_scores: np.ndarray,
        pages: list[dict[str, Any]],
        top_k_docs: int = 4,
    ) -> list[DocumentCandidate]:
        """
        Ranks all 93 canonical documents using hybrid evidence:
        1. Query-Title exact phrase and token overlap.
        2. Regulation number regex matches.
        3. Hydraulic facility & basin matches.
        4. Aggregated BM25 and Dense scores from top pages belonging to each document.
        """
        norm_q = normalize_text(query)
        doc_scores: dict[str, float] = defaultdict(float)
        match_reasons: dict[str, list[str]] = defaultdict(list)

        # 1. Regulation ID extraction from query
        reg_patterns = [
            r"(\d+/(?:qđ|qd|nđ|nd|tt|ct)[\w\-/]*)",
            r"(?:quyết định|quyét dinh|qđ|qd)\s*(?:số)?\s*(\d+(?:/[\w\-/]+)?)",
            r"(qcvn\s*[\d\-:/]+(?:/\w+)?)",
            r"(tcvn\s*[\d\-:/]+(?:/\w+)?)",
        ]
        query_regs = []
        for pat in reg_patterns:
            for m in re.findall(pat, norm_q):
                m_str = m.strip()
                if len(m_str) >= 3 and m_str not in query_regs:
                    query_regs.append(m_str)

        # 2. Known Hydraulic Entities
        facility_list = [
            "tả trạch", "bình điền", "hương điền", "hòa bình", "sơn la", "thác bà",
            "dầu tiếng", "trị an", "bản vẽ", "cửa đạt", "ngàn trươi", "núi cốc", "đại lải",
            "yên lập", "sông đà", "sông đáy", "bằng giang", "lục nam", "đồng nai",
            "sông hương", "sông hồng", "mê công", "đbscl", "bắc nam hà", "nam trung bộ"
        ]
        query_facilities = [fac for fac in facility_list if fac in norm_q]

        # 3. Score each document based on metadata & rules
        for doc_id, meta in self.doc_metadata.items():
            title = meta["norm_title"]
            basin = meta["norm_basin"]
            agency = meta["norm_agency"]

            # Exact or Substring title match
            if title and len(title) > 10:
                if title in norm_q:
                    doc_scores[doc_id] += 20.0
                    match_reasons[doc_id].append("full_title_in_query")
                else:
                    # Token overlap
                    t_words = set(title.split())
                    q_words = set(norm_q.split())
                    overlap = len(t_words.intersection(q_words))
                    if overlap >= 3:
                        doc_scores[doc_id] += overlap * 1.5
                        match_reasons[doc_id].append(f"title_token_overlap:{overlap}")

            # Regulation match
            for reg in query_regs:
                clean_reg = re.sub(r"[^\w]", "", reg)
                clean_title = re.sub(r"[^\w]", "", title)
                if reg in title or (len(clean_reg) >= 4 and clean_reg in clean_title):
                    doc_scores[doc_id] += 15.0
                    match_reasons[doc_id].append(f"reg_match:{reg}")

            # Facility & Basin match
            for fac in query_facilities:
                if fac in title:
                    doc_scores[doc_id] += 6.0
                    match_reasons[doc_id].append(f"facility_in_title:{fac}")
                elif fac in basin:
                    doc_scores[doc_id] += 3.0
                    match_reasons[doc_id].append(f"facility_in_basin:{fac}")

        # 4. Aggregate Page BM25 and Dense scores per document
        doc_page_bm25: dict[str, list[float]] = defaultdict(list)
        doc_page_dense: dict[str, list[float]] = defaultdict(list)

        for p_idx, p in enumerate(pages):
            d_id = str(p["doc_id"])
            doc_page_bm25[d_id].append(float(page_bm25_scores[p_idx]))
            doc_page_dense[d_id].append(float(page_dense_scores[p_idx]))

        for doc_id in self.doc_ids:
            # Take max top-3 page scores for this document
            bm_vals = sorted(doc_page_bm25[doc_id], reverse=True)[:3]
            dense_vals = sorted(doc_page_dense[doc_id], reverse=True)[:3]

            bm_agg = sum(bm_vals) / len(bm_vals) if bm_vals else 0.0
            dense_agg = sum(dense_vals) / len(dense_vals) if dense_vals else 0.0

            # Normalize and add to doc score
            doc_scores[doc_id] += (bm_agg * 0.4) + (dense_agg * 10.0)

        # Sort documents by total score
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for rank, (doc_id, score) in enumerate(sorted_docs[:top_k_docs], start=1):
            title = self.doc_metadata[doc_id]["title"]
            results.append(DocumentCandidate(
                doc_id=doc_id,
                title=title,
                score=float(score),
                rank=rank,
                match_reasons=match_reasons.get(doc_id, ["aggregated_page_scores"]),
            ))

        return results


def filter_pages_by_doc_shortlist(
    pages: list[dict[str, Any]],
    doc_shortlist: list[str],
    global_top_pages: list[dict[str, Any]],
    fallback_budget: int = 5,
) -> list[dict[str, Any]]:
    """
    Gathers candidate pages genuine to the shortlisted documents.
    Adds a safe global fallback of top pages to guard against doc selection misses.
    """
    shortlist_set = set(doc_shortlist)
    scoped_pages = [p for p in pages if str(p["doc_id"]) in shortlist_set]

    # Deduplicate while preserving order, then append global fallback
    seen = {str(p["page_id"]) for p in scoped_pages}
    fallback_pages = []
    for p in global_top_pages:
        pid = str(p["page_id"])
        if pid not in seen:
            seen.add(pid)
            fallback_pages.append(p)
        if len(fallback_pages) >= fallback_budget:
            break

    return scoped_pages + fallback_pages
