# -*- coding: utf-8 -*-
"""
M3-B: Source-Faithful Evidence Allocator for VietIRR-RAG
Optimizes the allocation of the fixed 5-unit evidence budget across retrieved pages.
Consumes frozen AB1 page rankings, preserving Output A (Top-5 Pages) while maximizing
the delivery of authentic, query-relevant evidence regions (Output B).
"""

from typing import Any, Sequence
import math
import re

HYDRAULIC_PARAMETERS = [
    "dung tích toàn bộ", "dung tích chết", "dung tích hữu ích", "dung tích phòng lũ",
    "mực nước dâng bình thường", "mực nước chết", "mực nước gia cường", "mực nước lũ thiết kế",
    "mực nước lũ kiểm tra", "mực nước đón lũ", "mực nước cao nhất", "lưu lượng xả", "lưu lượng tràn",
    "mndbt", "mnc", "mngc", "mnlt", "mnlkt", "mnđl", "q thiết kế", "q kiểm tra", "q xả", "hồ chứa",
    "lượng mưa", "mực nước", "dung tích", "lưu lượng", "cao trình", "độ mặn",
]

HYDRAULIC_UNITS = ["m", "triệu m3", "m3/s", "mm", "mg/l", "g/l", "%", "ha"]


class SourceFaithfulEvidenceAllocator:
    """
    Allocates a fixed budget of K evidence units (Budget B) across the top candidate pages
    without modifying the page ranking order (Budget A).
    """

    def __init__(self, max_units_budget: int = 5, max_per_page: int = 2):
        self.max_units_budget = max_units_budget
        self.max_per_page = max_per_page

    def score_region(
        self,
        region_dict: dict[str, Any],
        query: str,
        page_rank: int,
        page_score: float,
    ) -> float:
        """
        Computes relevance score of an evidence unit combining:
        - Query lexical match
        - Hydraulic parameter presence
        - Unit type boost (tables prioritized for quantitative queries)
        - Page rank discount
        """
        text = str(region_dict.get("text") or region_dict.get("raw_text") or "").lower()
        q_lower = query.lower()
        q_tokens = set(q_lower.split())

        # 1. Lexical overlap
        text_tokens = set(text.split())
        overlap = len(q_tokens.intersection(text_tokens))

        # 2. Parameter match
        param_match = any(param in text for param in HYDRAULIC_PARAMETERS if param in q_lower)
        param_boost = 3.0 if param_match else 0.0

        # 3. Table priority
        ev_id = str(region_dict.get("evidence_id") or region_dict.get("region_id") or "")
        is_table = region_dict.get("unit_type") == "table" or "TAB_" in ev_id
        is_quantitative_q = any(p in q_lower for p in ["bao nhiêu", "mực nước", "dung tích", "lưu lượng", "lượng mưa", "chỉ tiêu"])
        table_boost = 4.0 if (is_table and is_quantitative_q) else (1.5 if is_table else 0.0)

        # 4. Numeric density
        num_count = len(re.findall(r"\b\d+(?:[.,]\d+)?\b", text))
        num_boost = min(2.0, num_count * 0.2) if is_quantitative_q else 0.0

        # 5. Page rank discount: ensures top-ranked pages retain priority unless lower page has vastly better evidence
        rank_weight = 1.0 / math.log2(page_rank + 1)

        raw_score = (overlap * 1.0 + param_boost + table_boost + num_boost) * rank_weight
        return raw_score

    def allocate_evidence(
        self,
        ranked_pages: Sequence[dict[str, Any]],
        page_to_unit_indices: dict[str, list[int]],
        units_corpus: list[dict[str, Any]],
        query: str,
        page_scores: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Produces Output B: exactly up to max_units_budget evidence units.
        Applies relevance-aware diversity:
        - Scans candidate regions across all top-5 pages.
        - Caps units per page (max_per_page=2) to prevent page 1 from starving pages 2-5.
        - Selects globally best candidate regions across the diverse pool.
        """
        if not ranked_pages:
            return []

        top_pages = ranked_pages[:5]
        candidate_pool: list[tuple[float, dict[str, Any], str]] = []

        for p_rank, p_obj in enumerate(top_pages, 1):
            pid = p_obj["page_id"]
            p_score = page_scores[p_rank - 1] if page_scores and len(page_scores) >= p_rank else 1.0 / p_rank
            unit_idxs = page_to_unit_indices.get(pid, [])
            if not unit_idxs:
                continue

            for u_idx in unit_idxs:
                u = units_corpus[u_idx]
                row = {
                    "evidence_id": str(u["evidence_id"]),
                    "region_id": str(u["evidence_id"]),
                    "doc_id": str(u["doc_id"]),
                    "page_id": str(u["page_id"]),
                    "page_number": int(u["page_number"]),
                    "unit_type": str(u.get("unit_type", "")),
                    "text": str(u.get("raw_text") or u.get("index_text") or ""),
                    "page_rank": p_rank,
                    "page_score": float(p_score),
                }
                score = self.score_region(row, query, p_rank, float(p_score))
                row["allocated_score"] = score
                candidate_pool.append((score, row, pid))

        # Sort all candidate units across top pages descending by allocation score
        candidate_pool.sort(key=lambda x: x[0], reverse=True)

        selected_units: list[dict[str, Any]] = []
        page_counts: dict[str, int] = {}

        # Round 1: Select up to max_per_page per page to enforce diversity
        for score, unit_row, pid in candidate_pool:
            if len(selected_units) >= self.max_units_budget:
                break
            if page_counts.get(pid, 0) < self.max_per_page:
                selected_units.append(unit_row)
                page_counts[pid] = page_counts.get(pid, 0) + 1

        # Round 2: If budget still not full, backfill without page caps
        if len(selected_units) < self.max_units_budget:
            selected_ids = {u["evidence_id"] for u in selected_units}
            for score, unit_row, pid in candidate_pool:
                if len(selected_units) >= self.max_units_budget:
                    break
                if unit_row["evidence_id"] not in selected_ids:
                    selected_units.append(unit_row)
                    selected_ids.add(unit_row["evidence_id"])

        return selected_units[:self.max_units_budget]
