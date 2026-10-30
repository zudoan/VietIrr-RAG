# -*- coding: utf-8 -*-
"""
VIETIRR-RAG: HIGH-PERFORMANCE GLOBAL HYBRID RETRIEVER & MULTI-WINDOW RERANKER
Implements:
1. Global Lexical BM25 (Pages + Regions Max-Pooling)
2. Global Dense BGE-M3 (Full 8,192 tokens per page, no truncation)
3. Global Reciprocal Rank Fusion (RRF, k=60, Top-100 global pool, NO hard doc pruning)
4. Technical Identifier-Aware Enrichment (Reservoirs, Basins, Regulations, Hydraulic Parameters)
5. True Multi-Window Cross-Encoder Reranking (BAAI/bge-reranker-v2-m3 with window aggregation)
6. Dual Budget Support:
   - Budget A: Top-5 unique pages
   - Budget B: Top-5 authentic evidence units via SourceFaithfulEvidenceAllocator
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
import torch
from sentence_transformers import CrossEncoder, SentenceTransformer

from viirr_retrieval.bm25 import BM25Retriever
from viirr_retrieval.evidence_allocator import SourceFaithfulEvidenceAllocator
from viirr_retrieval.fusion import reciprocal_rank_fusion
from viirr_retrieval.ontology_query_guide import OntologyQueryGuide, normalize_vietnamese
from viirr_retrieval.table_aware import TableAwareEvidenceResolver, is_table_unit
from viirr_retrieval.query_aware_windows import build_query_aware_windows
from viirr_retrieval.evidence_view_builder import build_evidence_views

# -----------------------------------------------------------------------------
# 1. TECHNICAL DICTIONARIES & PATTERNS
# -----------------------------------------------------------------------------

TECHNICAL_ACRONYMS = [
    (r"\bMNDBT\b", "MNDBT mực nước dâng bình thường cao trình dâng bình thường"),
    (r"\bMNC\b", "MNC mực nước chết cao trình chết"),
    (r"\bMNDGC\b", "MNDGC mực nước dâng gia cường"),
    (r"\bMNGC\b", "MNGC mực nước dâng gia cường"),
    (r"\bMNMN\b", "MNMN mực nước mùa nổi"),
    (r"\bMNMC\b", "MNMC mực nước mùa cạn"),
    (r"\bMNKT\b", "MNKT mực nước lũ kiểm tra"),
    (r"\bMNLKT\b", "MNLKT mực nước lũ kiểm tra"),
    (r"\bMNLT\b", "MNLT mực nước lũ thiết kế"),
    (r"\bMNĐL\b", "MNĐL mực nước đón lũ"),
    (r"\bMNTK\b", "MNTK mực nước thiết kế"),
    (r"\bQTVH\b", "QTVH quy trình vận hành liên hồ chứa"),
    (r"\bKHSDN\b", "KHSDN kế hoạch sử dụng nước"),
    (r"\bĐBSCL\b", "ĐBSCL đồng bằng sông cửu long mekong"),
    (r"\bDB\b", "dự báo"),
    (r"\bTBNN\b", "TBNN trung bình nhiều năm"),
    (r"\bCTL\b", "Cái Lớn Cái Bé"),
    (r"\bWtb\b", "Wtb dung tích toàn bộ"),
    (r"\bWhi\b", "Whi dung tích hữu ích dung tích hiệu dụng"),
    (r"\bWc\b", "Wc dung tích chết"),
    (r"\bWpl\b", "Wpl dung tích phòng lũ dung tích cắt lũ"),
    (r"\bQ xả\b", "Q xả lưu lượng xả qua tràn qua đáy"),
    (r"\bQ đến\b", "Q đến lưu lượng đến lưu lượng về hồ"),
]

RESERVOIRS = [
    # Red River Basin
    ("hòa bình", "hoa binh"),
    ("sơn la", "son la"),
    ("tuyên quang", "tuyen quang"),
    ("thác bà", "thac ba"),
    ("lai châu", "lai chau"),
    ("huội quảng", "huoi quang"),
    ("bản chát", "ban chat"),
    ("nậm chiến", "nam chien"),
    # Dong Nai Basin
    ("dầu tiếng", "dau tieng"),
    ("trị an", "tri an"),
    ("thác mơ", "thac mo"),
    ("cần đơn", "can don"),
    ("srok phu miêng", "srok phu mieng"),
    ("đơn dương", "don duong"),
    ("đại ninh", "dai ninh"),
    ("hàm thuận", "ham thuan"),
    ("đa mi", "da mi"),
    ("đồng nai 2", "dong nai 2"),
    ("đồng nai 3", "dong nai 3"),
    ("đồng nai 4", "dong nai 4"),
    # Huong River Basin
    ("tả trạch", "ta trach"),
    ("bình điền", "binh dien"),
    ("hương điền", "huong dien"),
    ("a lưới", "a luoi"),
    # Vu Gia - Thu Bon Basin
    ("a vương", "a vuong"),
    ("sông tranh 2", "song tranh 2"),
    ("đăk mi 4", "dak mi 4"),
    ("sông bung 2", "song bung 2"),
    ("sông bung 4", "song bung 4"),
    ("sông bung 4a", "song bung 4a"),
    ("sông bung 5", "song bung 5"),
    ("sông bung 6", "song bung 6"),
    ("a roàng", "a roang"),
    # Ba River Basin
    ("sông hinh", "song hinh"),
    ("sông ba hạ", "song ba ha"),
    ("krông hnăng", "krong hnang"),
    ("ayun hạ", "ayun ha"),
    ("an khê", "an khe"),
    ("ka nak", "ka nak"),
    # Kon - Ha Thanh Basin
    ("vĩnh sơn", "vinh son"),
    ("định bình", "dinh binh"),
    ("núi một", "nui mot"),
    ("thuận ninh", "thuan ninh"),
    # Se San Basin
    ("pleikrông", "pleikrong"),
    ("ialy", "ia ly"),
    ("ia ly", "ia ly"),
    ("sê san 3", "se san 3"),
    ("sê san 3a", "se san 3a"),
    ("sê san 4", "se san 4"),
    ("sê san 4a", "se san 4a"),
    # Srepok Basin
    ("buôn tua srah", "buon tua srah"),
    ("buôn kuốp", "buon kuop"),
    ("srêpôk 3", "srepok 3"),
    ("srêpôk 4", "srepok 4"),
    ("dray hling", "dray hling"),
    # Ma & Ca Basin
    ("trung sơn", "trung son"),
    ("bá thước 1", "ba thuoc 1"),
    ("bá thước 2", "ba thuoc 2"),
    ("cẩm thủy 1", "cam thuy 1"),
    ("hủa na", "hua na"),
    ("cửa đạt", "cua dat"),
    ("bản vẽ", "ban ve"),
    ("khe bố", "khe bo"),
    ("chi khê", "chi khe"),
    # Mekong / Irrigation Structures
    ("cái lớn", "cai lon"),
    ("cái bé", "cai be"),
    ("ba lai", "ba lai"),
    ("phú ninh", "phu ninh"),
    ("cửa đại", "cua dai"),
    ("yên lập", "yen lap"),
    ("đại lải", "dai lai"),
    ("hồ núi cốc", "nui coc"),
    ("hồ cấm sơn", "cam son"),
    ("quảng trị", "quang tri"),
]

REGULATIONS = [
    ("1606", "1606"),
    ("1865", "1865"),
    ("940", "940"),
    ("922", "922"),
    ("1478", "1478"),
    ("2026", "2026"),
    ("2025", "2025"),
    ("2024", "2024"),
    ("2023", "2023"),
    ("2021", "2021"),
    ("2018", "2018"),
    ("1560", "1560"),
    ("1570", "1570"),
    ("1390", "1390"),
    ("770", "770"),
    ("1537", "1537"),
    ("1841", "1841"),
]

BASINS = [
    ("mê công", "me kong"),
    ("mekong", "me kong"),
    ("sông hồng", "song hong"),
    ("đồng nai", "dong nai"),
    ("sông mã", "song ma"),
    ("sông cả", "song ca"),
    ("lục nam", "luc nam"),
    ("hoàng long", "hoang long"),
    ("sông hương", "song huong"),
    ("vu gia", "thu bon"),
    ("thu bồn", "thu bon"),
    ("sông ba", "song ba"),
    ("ba", "song ba"),
    ("kôn", "kon"),
    ("hà thanh", "ha thanh"),
    ("sê san", "se san"),
    ("srêpôk", "srepok"),
    ("srepok", "srepok"),
]

HYDRAULIC_PARAMETERS = [
    ("dung tích toàn bộ", "dung tích toàn bộ Wtb"),
    ("dung tích hữu ích", "dung tích hữu ích Whi dung tích hiệu dụng"),
    ("dung tích chết", "dung tích chết Wc"),
    ("dung tích phòng lũ", "dung tích phòng lũ Wpl cắt lũ"),
    ("mực nước dâng bình thường", "mực nước dâng bình thường MNDBT cao trình dâng bình thường"),
    ("mực nước chết", "mực nước chết MNC cao trình chết"),
    ("mực nước gia cường", "mực nước gia cường MNDGC MNGC"),
    ("mực nước lũ thiết kế", "mực nước lũ thiết kế MNLT"),
    ("mực nước lũ kiểm tra", "mực nước lũ kiểm tra MNKT MNLKT"),
    ("mực nước đón lũ", "mực nước đón lũ MNĐL"),
    ("lưu lượng xả", "lưu lượng xả Q xả xả tràn qua đáy"),
    ("lưu lượng tràn", "lưu lượng qua tràn xả lũ"),
    ("lưu lượng về hồ", "lưu lượng đến lưu lượng về hồ"),
    ("lưu lượng đến", "lưu lượng đến lưu lượng về hồ"),
    ("lượng mưa", "lượng mưa mưa tuần mưa lũy tích"),
]


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def normalize_query(query: str) -> str:
    res = query.strip()
    for pattern, replacement in TECHNICAL_ACRONYMS:
        res = re.sub(pattern, replacement, res, flags=re.IGNORECASE)
    return res


def expand_technical_query(query: str) -> str:
    """
    Deterministically expand technical query with hydraulic terms,
    reservoir synonyms, and regulatory keywords without LLM calls.
    """
    q_norm = normalize_query(query)
    q_lower = query.lower()
    additions = []

    for term, expansion in HYDRAULIC_PARAMETERS:
        if term in q_lower:
            additions.append(expansion)

    # Check for decision / quy trinh references
    if re.search(r"\b(quyết định|quy trình|qđ|qđ-ttg|liên hồ)\b", q_lower):
        additions.append("quy trình vận hành liên hồ chứa quyết định thủ tướng chính phủ")

    # Check for reporting or weekly forecast bulletin
    if re.search(r"\b(báo cáo|bản tin|dự báo|kỳ|tuần)\b", q_lower):
        additions.append("bản tin dự báo nguồn nước báo cáo diễn biến")

    if additions:
        return f"{q_norm} " + " ".join(dict.fromkeys(additions))
    return q_norm


# -----------------------------------------------------------------------------
# 2. HIGH PERFORMANCE RETRIEVER CLASS
# -----------------------------------------------------------------------------

class HighPerformanceRetriever:
    def __init__(
        self,
        workspace_dir: Path,
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
        load_reranker: bool = True,
    ):
        self.workspace = workspace_dir
        self.device = device

        corpus_dir = self.workspace / "outputs" / "V4_EXPERIMENT" / "index"
        cache_dir = self.workspace / "outputs" / "V4_EXPERIMENT" / "cache"
        bge_cache_dir = self.workspace / "outputs" / "RETRIEVAL_UPGRADE" / "cache"

        # 1. Load Corpus
        print("[HP-RETRIEVER] Loading pages and evidence units...")
        with open(corpus_dir / "pages_v4.jsonl", "r", encoding="utf-8") as f:
            self.pages = [json.loads(line) for line in f if line.strip()]
        with open(corpus_dir / "evidence_units_v4.jsonl", "r", encoding="utf-8") as f:
            self.units = [json.loads(line) for line in f if line.strip()]

        self.page_ids = [p["page_id"] for p in self.pages]
        self.page_by_id = {p["page_id"]: p for p in self.pages}
        self.page_to_idx = {pid: i for i, pid in enumerate(self.page_ids)}

        self.page_to_unit_indices: dict[str, list[int]] = {}
        for idx, u in enumerate(self.units):
            pid = str(u["page_id"])
            self.page_to_unit_indices.setdefault(pid, []).append(idx)

        # 2. Load BM25
        print("[HP-RETRIEVER] Loading BM25 indexes...")
        page_units = [{**row, "evidence_id": row["page_id"], "unit_type": "PAGE"} for row in self.pages]
        self.page_bm25 = BM25Retriever(page_units, cache_dir / "bm25_pages.pkl", "cached", 1.5, 0.75)
        self.region_bm25 = BM25Retriever(self.units, cache_dir / "bm25_regions.pkl", "cached", 1.5, 0.75)

        # 3. Load BGE-M3 Dense Embeddings & Model
        print(f"[HP-RETRIEVER] Loading BGE-M3 Dense Embeddings on {device}...")
        self.bge_pages = np.load(bge_cache_dir / "bge_m3_pages.npy", mmap_mode="r")
        self.embedder = SentenceTransformer("BAAI/bge-m3", device=device, local_files_only=True)
        self.embedder.max_seq_length = 8192

        # 4. Load CrossEncoder Reranker
        if load_reranker:
            print(f"[HP-RETRIEVER] Loading BGE-Reranker-v2-m3 on {device}...")
            self.reranker = CrossEncoder("BAAI/bge-reranker-v2-m3", device=device, local_files_only=True)
        else:
            self.reranker = None

        # 5. Build Document / Identifier Index
        print("[HP-RETRIEVER] Building Identifier Traversal Index...")
        self._build_identifier_index()

        # 6. Build source-faithful table facts and ontology query guide.  The
        # entity lexicon is derived only from parser-emitted table rows.
        initial_guide = OntologyQueryGuide()
        self.table_resolver = TableAwareEvidenceResolver(self.units, query_guide=initial_guide)
        table_entities = {fact.entity for fact in self.table_resolver.facts}
        self.query_guide = OntologyQueryGuide(extra_entities=table_entities)
        self.table_resolver.query_guide = self.query_guide
        self.normalized_page_texts = [
            normalize_vietnamese(
                f"{self.doc_titles.get(p['doc_id'], '')} {p.get('index_text') or p.get('raw_text') or ''}"
            )
            for p in self.pages
        ]

        # 7. Precompute Table Unit Mask for vectorized structure-aware retrieval
        print("[HP-RETRIEVER] Precomputing table unit mask...")
        self.is_table_unit = np.array(
            [is_table_unit(u) for u in self.units],
            dtype=bool,
        )

        # 8. Allocator
        self.allocator = SourceFaithfulEvidenceAllocator(max_units_budget=5, max_per_page=2)
        table_stats = self.table_resolver.stats()
        print(
            "[HP-RETRIEVER] Initialized successfully "
            f"({table_stats['tables']} tables, {table_stats['facts']} typed facts)."
        )

    def _build_identifier_index(self):
        """Map identifiers to document IDs and page IDs."""
        self.doc_to_page_ids: dict[str, list[str]] = {}
        for p in self.pages:
            self.doc_to_page_ids.setdefault(p["doc_id"], []).append(p["page_id"])

        # Inverted index: identifier -> set of page indices
        self.identifier_to_pages: dict[str, set[int]] = {}

        manifest_path = self.workspace / "data" / "v4_corpus" / "metadata" / "v4_corpus_manifest.jsonl"
        self.doc_titles: dict[str, str] = {}
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        r = json.loads(line)
                        self.doc_titles[r["doc_id"]] = (r.get("source_title") or "").strip()

        for idx, p in enumerate(self.pages):
            doc_id = p["doc_id"]
            d_title = self.doc_titles.get(doc_id, "").lower()
            p_text = ((p.get("raw_text") or "") + " " + (p.get("index_text") or "")).lower()
            combined = d_title + " " + p_text

            for r_raw, r_norm in RESERVOIRS:
                if r_raw in combined or r_norm in combined:
                    self.identifier_to_pages.setdefault(r_norm, set()).add(idx)

            for reg_raw, reg_norm in REGULATIONS:
                if reg_raw in combined or reg_norm in combined:
                    self.identifier_to_pages.setdefault(reg_norm, set()).add(idx)

            for b_raw, b_norm in BASINS:
                if b_raw in combined or b_norm in combined:
                    self.identifier_to_pages.setdefault(b_norm, set()).add(idx)

    def extract_identifiers(self, query: str) -> list[str]:
        """Extract recognized reservoir, regulation, and basin identifiers from query."""
        q_lower = query.lower()
        q_norm = strip_accents(query)
        detected = []

        for r_raw, r_norm in RESERVOIRS:
            if r_raw in q_lower or r_norm in q_norm:
                detected.append(r_norm)

        for reg_raw, reg_norm in REGULATIONS:
            if reg_raw in q_lower:
                detected.append(reg_norm)

        for b_raw, b_norm in BASINS:
            if b_raw in q_lower or b_norm in q_norm:
                detected.append(b_norm)

        return list(dict.fromkeys(detected))

    def retrieve_candidates(
        self,
        query: str,
        top_k_candidates: int = 100,
        use_identifier_boost: bool = True,
        use_dual_variant: bool = False,
        use_structure_aware: bool = False,
        use_ontology_guide: bool = False,
        rrf_k: int = 60,
    ) -> list[dict[str, Any]]:
        """
        Task A: High-Recall Global Candidate Retrieval.
        Merges Global BM25 + Global BGE-M3 Dense via RRF, with optional:
        - Technical Identifier Enrichment
        - Dual-Variant Technical Query Expansion (norm_q + exp_q)
        - Structure-Aware Candidate Recovery (table headers & cells)
        Returns Top-K global page candidates (NO document-first pruning).
        """
        norm_q = normalize_query(query)
        intent = self.query_guide.understand(query) if use_ontology_guide else None
        if use_ontology_guide:
            guided_q = self.query_guide.expand_query(query, intent)
            exp_q = guided_q if use_dual_variant else norm_q
        else:
            exp_q = expand_technical_query(query) if use_dual_variant else norm_q

        # 1. Lexical Scoring (Page + Region Max Pooling)
        page_bm_scores = self.page_bm25.score_all(norm_q)
        reg_bm_scores = self.region_bm25.score_all(norm_q)

        if use_dual_variant and exp_q != norm_q:
            exp_page_bm = self.page_bm25.score_all(exp_q)
            exp_reg_bm = self.region_bm25.score_all(exp_q)
            page_bm_scores = np.maximum(page_bm_scores, exp_page_bm)
            reg_bm_scores = np.maximum(reg_bm_scores, exp_reg_bm)

        # Max pooling of regions per page with optional structure-aware weighting
        pooled_bm_scores = np.copy(page_bm_scores)
        has_tech_params = any(term in query.lower() for term, _ in HYDRAULIC_PARAMETERS)

        if use_structure_aware and has_tech_params:
            effective_reg_bm = np.where(self.is_table_unit, reg_bm_scores * 1.15, reg_bm_scores)
        else:
            effective_reg_bm = reg_bm_scores

        for p_idx, pid in enumerate(self.page_ids):
            u_indices = self.page_to_unit_indices.get(pid, [])
            if u_indices:
                max_u_score = float(np.max(effective_reg_bm[u_indices]))
                pooled_bm_scores[p_idx] = max(pooled_bm_scores[p_idx], max_u_score)

        # 2. Dense Scoring (BGE-M3 8192-token page vectors)
        if use_dual_variant and exp_q != norm_q:
            q_vecs = self.embedder.encode(
                ["query: " + norm_q, "query: " + exp_q],
                normalize_embeddings=True,
                show_progress_bar=False,
            ).astype(np.float32)
            dense_scores_v1 = np.asarray(self.bge_pages @ q_vecs[0], dtype=np.float64)
            dense_scores_v2 = np.asarray(self.bge_pages @ q_vecs[1], dtype=np.float64)
            dense_scores = np.maximum(dense_scores_v1, dense_scores_v2)
        else:
            q_vec = self.embedder.encode(
                ["query: " + norm_q],
                normalize_embeddings=True,
                show_progress_bar=False,
            )[0].astype(np.float32)
            dense_scores = np.asarray(self.bge_pages @ q_vec, dtype=np.float64)

        # 3. Reciprocal Rank Fusion
        order_bm25 = np.argsort(-pooled_bm_scores)
        order_dense = np.argsort(-dense_scores)

        # Build RRF score dictionary
        rrf_scores: dict[int, float] = {i: 0.0 for i in range(len(self.pages))}
        for rank, idx in enumerate(order_bm25):
            rrf_scores[idx] += 1.0 / (rrf_k + rank + 1)
        for rank, idx in enumerate(order_dense):
            rrf_scores[idx] += 1.0 / (rrf_k + rank + 1)

        # 4. Technical Identifier-Aware Enrichment (A4 + Structure-Aware)
        if use_identifier_boost:
            identifiers = self.extract_identifiers(query)
            if identifiers:
                matching_page_indices = set()
                for ident in identifiers:
                    matching_page_indices.update(self.identifier_to_pages.get(ident, set()))

                # Boost matching pages with an additive RRF reward
                base_boost = 0.018 if use_structure_aware else 0.015
                for idx in matching_page_indices:
                    rrf_scores[idx] += base_boost

        # 5. Ontology-guided soft constraints.  These are boosts, never hard
        # filters, so uncertain entity extraction cannot discard relevant pages.
        if use_ontology_guide and intent:
            entity_norm = normalize_vietnamese(intent.entity or "")
            parameter_terms = [intent.parameter, *intent.aliases] if intent.parameter else []
            parameter_norms = [normalize_vietnamese(term) for term in parameter_terms if term]
            document_norm = normalize_vietnamese(intent.document_identity or "")
            for idx, page_text in enumerate(self.normalized_page_texts):
                if entity_norm and entity_norm in page_text:
                    rrf_scores[idx] += 0.012
                if document_norm and document_norm in page_text:
                    rrf_scores[idx] += 0.010
                if parameter_norms and any(term in page_text for term in parameter_norms):
                    rrf_scores[idx] += 0.004

        # Sort global candidates
        ranked_indices = sorted(rrf_scores.keys(), key=lambda i: rrf_scores[i], reverse=True)[:top_k_candidates]

        candidates = []
        for rank, idx in enumerate(ranked_indices, 1):
            p = self.pages[idx]
            candidates.append({
                "candidate_rank": rank,
                "page_index": idx,
                "page_id": p["page_id"],
                "doc_id": p["doc_id"],
                "page_number": p["page_number"],
                "rrf_score": rrf_scores[idx],
                "bm25_score": float(pooled_bm_scores[idx]),
                "dense_score": float(dense_scores[idx]),
            })

        return candidates

    def _build_page_windows(
        self,
        page_index: int,
        query: str,
        enhanced_mode: bool = False,
        table_aware: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Segment a candidate page into 2-3 structured, query-relevant windows.
        Window 1: Page Header + Table Blocks (with row-column context)
        Window 2: Relevant technical paragraphs with parameter density
        Window 3: Clause / Full sequence fallback
        """
        p = self.pages[page_index]
        pid = p["page_id"]
        u_indices = self.page_to_unit_indices.get(pid, [])

        if not u_indices:
            raw = (p.get("raw_text") or p.get("index_text") or "").strip()
            return [{"window_id": f"{pid}_W0", "text": raw[:1200], "unit_indices": []}]

        # Gather units
        table_units = []
        text_units = []
        for idx in u_indices:
            u = self.units[idx]
            utype = u.get("unit_type", "")
            if is_table_unit(u):
                table_units.append(idx)
            else:
                text_units.append(idx)

        windows = []
        doc_title = self.doc_titles.get(p["doc_id"], p["doc_id"])
        header = f"Tài liệu: {doc_title} (Mã: {p['doc_id']}) - Trang {p['page_number']}:"

        # Window 1: Tables first (crucial for technical water/reservoir specs)
        if table_units:
            t_texts = []
            ordered_table_units = table_units
            if enhanced_mode and table_aware:
                resolved = self.table_resolver.resolve(
                    query,
                    [{"page_id": pid}],
                    max_facts=6,
                    min_score=0.0,
                )
                preferred_ids = list(dict.fromkeys(str(row.get("table_id")) for row in resolved))
                preferred = [
                    idx for table_id in preferred_ids for idx in table_units
                    if str(self.units[idx].get("evidence_id")) == table_id
                ]
                ordered_table_units = preferred + [idx for idx in table_units if idx not in preferred]
            for u_idx in ordered_table_units[:3 if enhanced_mode else 2]:
                u = self.units[u_idx]
                raw_t = (
                    self.table_resolver.build_table_window(u, query)
                    if enhanced_mode and table_aware
                    else str(u.get("raw_text") or u.get("index_text") or "").strip()
                )
                if enhanced_mode:
                    t_texts.append(f"[BẢNG/SỐ LIỆU]: {raw_t}")
                else:
                    t_texts.append(raw_t)
            w1_text = header + "\n" + "\n---\n".join(t_texts)
            windows.append({
                "window_id": f"{pid}_WTables",
                "text": w1_text[:1800 if enhanced_mode else 1500],
                "unit_indices": table_units[:3 if enhanced_mode else 2],
            })

        # Window 2: Key text paragraphs
        if text_units:
            # Score paragraphs by query tokens and technical parameter density
            q_tokens = set(query.lower().split())
            tech_terms = [t.lower() for t, _ in HYDRAULIC_PARAMETERS]
            scored_text = []

            for u_idx in text_units:
                u = self.units[u_idx]
                u_text = str(u.get("raw_text") or u.get("index_text") or "").strip()
                u_lower = u_text.lower()
                overlap = len(q_tokens.intersection(set(u_lower.split())))
                if enhanced_mode:
                    # Give bonus if text contains hydraulic parameter terms
                    tech_bonus = sum(2 for t in tech_terms if t in u_lower)
                    score = overlap + tech_bonus
                else:
                    score = overlap
                scored_text.append((score, u_idx, u_text))

            scored_text.sort(key=lambda x: x[0], reverse=True)
            top_paragraphs = scored_text[:3]
            p_texts = [item[2] for item in top_paragraphs]
            w2_text = header + "\n" + "\n".join(p_texts)
            windows.append({
                "window_id": f"{pid}_WProse",
                "text": w2_text[:1800 if enhanced_mode else 1500],
                "unit_indices": [item[1] for item in top_paragraphs],
            })

        # Window 3: Full sequence fallback if windows are few
        if len(windows) < 2:
            raw_full = (p.get("raw_text") or p.get("index_text") or "").strip()
            windows.append({
                "window_id": f"{pid}_WFull",
                "text": (header + "\n" + raw_full)[:1500],
                "unit_indices": u_indices[:4],
            })

        return windows

    def rerank_candidates(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k_rerank: int = 40,
        batch_size: int = 32,
        enhanced_mode: bool = False,
        table_aware: bool = False,
        window_strategy: str = "r6",
    ) -> list[dict[str, Any]]:
        """
        Task B: True Multi-Window Cross-Encoder Reranking.
        Evaluates (query, window) pairs across multiple windows per page,
        aggregates into a robust page score, and preserves best window.
        """
        if not self.reranker:
            raise RuntimeError("CrossEncoder reranker is not initialized.")

        pool = candidates[:top_k_rerank]
        if not pool:
            return []

        # Build all (query, window) pairs across candidate pages
        pairs_to_score = []
        page_window_map: list[tuple[int, dict[str, Any]]] = []  # (cand_idx, window_obj)

        for c_idx, cand in enumerate(pool):
            if window_strategy == "r6":
                windows = self._build_page_windows(
                    cand["page_index"], query, enhanced_mode=enhanced_mode, table_aware=table_aware
                )
            elif window_strategy == "evidence_view":
                page = self.pages[cand["page_index"]]
                title = self.doc_titles.get(page["doc_id"], page["doc_id"])
                header = f"Tài liệu: {title} (Mã: {page['doc_id']}) - Trang {page['page_number']}:"
                windows = build_evidence_views(
                    page=page, units=self.units,
                    unit_indices=self.page_to_unit_indices.get(page["page_id"], []), query=query,
                    header=header,
                    table_renderer=(lambda u: self.table_resolver.build_table_window(u, query)) if table_aware else None,
                )
            else:
                page = self.pages[cand["page_index"]]
                title = self.doc_titles.get(page["doc_id"], page["doc_id"])
                header = f"Tài liệu: {title} (Mã: {page['doc_id']}) - Trang {page['page_number']}:"
                windows = build_query_aware_windows(
                    page=page, units=self.units,
                    unit_indices=self.page_to_unit_indices.get(page["page_id"], []), query=query,
                    strategy=window_strategy, header=header,
                    table_renderer=(lambda u: self.table_resolver.build_table_window(u, query)) if table_aware else None,
                )
            cand["windows"] = windows
            for w in windows:
                pairs_to_score.append((query, w["text"]))
                page_window_map.append((c_idx, w))

        # Run batched cross-encoder inference under inference_mode to conserve VRAM
        with torch.inference_mode():
            scores = self.reranker.predict(
                pairs_to_score,
                batch_size=batch_size,
                show_progress_bar=False,
            )

        # Aggregate window scores per page
        cand_window_scores: dict[int, list[tuple[float, dict[str, Any]]]] = {i: [] for i in range(len(pool))}
        for (c_idx, w), s in zip(page_window_map, scores):
            cand_window_scores[c_idx].append((float(s), w))

        # Sort candidates initially by Cross-Encoder best window score
        def get_best_ce(idx: int) -> float:
            scores_w = cand_window_scores[idx]
            return max(s for s, _ in scores_w) if scores_w else -999.0

        ce_sorted_indices = sorted(range(len(pool)), key=get_best_ce, reverse=True)
        ce_rank_map = {c_idx: r for r, c_idx in enumerate(ce_sorted_indices, 1)}

        # Multi-stage fusion: Cross-Encoder Rank + Candidate RRF Rank + Raw CE confidence
        for c_idx, cand in enumerate(pool):
            w_scores = cand_window_scores[c_idx]
            if w_scores:
                best_score, best_w = max(w_scores, key=lambda x: x[0])
                r_rank = ce_rank_map[c_idx]
                c_rank = cand["candidate_rank"]

                if enhanced_mode:
                    # Enhanced fusion: 80% Cross-Encoder ranking + 20% Candidate pool + CE logit boost (0.08)
                    ce_rank_component = (1.0 / (15 + r_rank)) * 0.80
                    candidate_rank_component = (1.0 / (25 + c_rank)) * 0.20
                    fusion_score = ce_rank_component + candidate_rank_component
                    raw_ce_bonus = float(best_score) * 0.08
                    cand["rerank_score"] = fusion_score + raw_ce_bonus
                else:
                    # Classic R3 fusion
                    ce_rank_component = (1.0 / (20 + r_rank)) * 0.70
                    candidate_rank_component = (1.0 / (20 + c_rank)) * 0.30
                    fusion_score = ce_rank_component + candidate_rank_component
                    raw_ce_bonus = float(best_score) * 0.05
                    cand["rerank_score"] = fusion_score + raw_ce_bonus

                cand["best_window"] = best_w
                cand["best_window_score"] = best_score
                # Trace-only fields: they make offline fusion replay auditable
                # and do not influence ranking beyond the existing formula.
                cand["ce_rank"] = r_rank
                cand["ce_rank_component"] = ce_rank_component
                cand["candidate_rank_component"] = candidate_rank_component
                cand["raw_ce_bonus"] = raw_ce_bonus
            else:
                cand["rerank_score"] = -999.0
                cand["best_window"] = None

        # Sort by rerank score descending
        pool.sort(key=lambda x: x["rerank_score"], reverse=True)
        for new_rank, cand in enumerate(pool, 1):
            cand["final_rank"] = new_rank

        return pool

    def allocate_budget_b_evidence(
        self,
        query: str,
        reranked_pages: list[dict[str, Any]],
        max_units: int = 5,
        table_aware: bool = False,
        selection_policy: str = "a0",
    ) -> list[dict[str, Any]]:
        """
        Selects 5 authentic evidence units using SourceFaithfulEvidenceAllocator
        from Top-5 reranked pages with max 2 units per page.
        """
        if selection_policy == "s5":
            from viirr_retrieval.need_aware_selection import select_relation_aware
            return select_relation_aware(self, query, reranked_pages, max_units=max_units)
        if selection_policy in {"s2", "s3", "s4"}:
            from viirr_retrieval.need_aware_selection import select_structure_preserving
            return select_structure_preserving(self, query, reranked_pages, max_units=max_units, policy=selection_policy)
        page_scores = [float(p.get("rerank_score", 1.0)) for p in reranked_pages[:5]]
        allocated = self.allocator.allocate_evidence(
            ranked_pages=reranked_pages[:5],
            page_to_unit_indices=self.page_to_unit_indices,
            units_corpus=self.units,
            query=query,
            page_scores=page_scores,
        )
        if not table_aware:
            return allocated[:max_units]

        intent = self.query_guide.understand(query)
        requested_entities = sum(
            1 for fact_entity in {normalize_vietnamese(f.entity) for f in self.table_resolver.facts}
            if fact_entity and fact_entity in normalize_vietnamese(query)
        )
        max_table_facts = min(3, max(1, requested_entities))
        resolved = self.table_resolver.resolve(
            query,
            reranked_pages[:5],
            max_facts=max_table_facts,
        )
        if not resolved:
            return allocated[:max_units]

        selected = list(resolved)
        selected_ids = {str(row["evidence_id"]) for row in selected}
        selected_parent_tables = {str(row.get("table_id")) for row in selected}
        for row in allocated:
            row_id = str(row.get("evidence_id"))
            # A compact cell supersedes its full parent table inside the fixed
            # budget, but other authentic regions remain available.
            if row_id in selected_ids or row_id in selected_parent_tables:
                continue
            selected.append(row)
            selected_ids.add(row_id)
            if len(selected) >= max_units:
                break
        return selected[:max_units]
