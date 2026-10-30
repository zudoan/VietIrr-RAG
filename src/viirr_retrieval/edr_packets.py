"""Source-faithful multi-region packets for experimental EDR reranking."""
from __future__ import annotations
import hashlib, re
from typing import Any, Callable
from viirr_retrieval.ontology_query_guide import normalize_vietnamese
from viirr_retrieval.table_aware import is_table_unit

UNKNOWN = "UNKNOWN"

def _tokens(text: str) -> set[str]:
    return {x for x in re.findall(r"\w+", normalize_vietnamese(text)) if len(x) > 1}

def _score(query: str, unit: dict[str, Any]) -> tuple[int, int, str]:
    text = str(unit.get("raw_text") or unit.get("index_text") or "")
    return (len(_tokens(query) & _tokens(text)), int(is_table_unit(unit)), str(unit.get("evidence_id") or ""))

def build_evidence_packets(*, page: dict[str, Any], units: list[dict[str, Any]], unit_indices: list[int],
                           query: str, table_renderer: Callable[[dict[str, Any]], str] | None = None,
                           max_packets: int = 3) -> list[dict[str, Any]]:
    """Select <=3 authentic regions, preserving whole anchors and provenance."""
    ranked = sorted(unit_indices, key=lambda i: (-_score(query, units[i])[0], -_score(query, units[i])[1], _score(query, units[i])[2]))
    packets = []
    for idx in ranked[:max_packets]:
        u = units[idx]; raw = str(u.get("raw_text") or u.get("index_text") or "")
        if is_table_unit(u) and table_renderer:
            raw = table_renderer(u)
        content = raw.strip()
        packets.append({
            "packet_id": f"{page['page_id']}::{u.get('evidence_id', idx)}", "query": query,
            "document_id": str(page.get("doc_id") or u.get("doc_id") or UNKNOWN), "page_id": str(page["page_id"]),
            "page_number": page.get("page_number", UNKNOWN), "evidence_id": str(u.get("evidence_id") or UNKNOWN),
            "region_ids": [str(u.get("evidence_id") or UNKNOWN)], "unit_type": str(u.get("unit_type") or UNKNOWN),
            "content": content, "heading": UNKNOWN, "entity": UNKNOWN, "parameter": UNKNOWN,
            "unit": UNKNOWN, "time_period": UNKNOWN, "condition": UNKNOWN,
            "provenance_status": "EXTRACTED", "source_sha256": str(u.get("source_sha256") or UNKNOWN),
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(), "token_count": len(re.findall(r"\S+", content)),
            "extraction_confidence": "SOURCE_EXACT",
        })
    return packets

def serialize_packets(packets: list[dict[str, Any]]) -> str:
    """Shared deterministic judge/runtime serialization; never slices anchors."""
    return "\n\n".join(f"[EVIDENCE {p['evidence_id']}]\n{p['content']}" for p in packets)
