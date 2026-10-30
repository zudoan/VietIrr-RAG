"""Non-breaking adapter between P5 Evidence and Stage 2 EvidenceItem.

This adapter:
1. Converts P5 Evidence objects to EvidenceItem preserving 100% of P5 data fields.
2. Supports optional verified metadata enrichment (bbox, document metadata) without fabrication.
3. Separates document identifier/number, publication date, legal status, and version identifier.
4. Validates complete join identities and rejects mismatched metadata.
5. Detects duplicate/conflicting lookup records rather than silently overwriting them.
6. Provides a clean projection back to P5 Evidence when required by legacy consumers.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from viirr_rag.pipeline import Evidence

from ..schema.evidence import EvidenceItem


def _map_p5_content_type(unit_type: str, context_role: str) -> str:
    """Derive standard Stage 2 content_type from P5 unit_type and context_role."""
    if context_role in {"table_caption", "table_header_or_unit", "table_row"}:
        return "table"
    if context_role in {"legal_identity", "legal_condition"}:
        return "legal_clause"

    clean_unit = unit_type.upper().strip()
    if clean_unit == "PAGE":
        return "page"
    if clean_unit in {"TEXT_REGION", "PARAGRAPH"}:
        return "text"
    if clean_unit == "HEADING":
        return "heading"
    if clean_unit == "CAPTION":
        return "caption"
    if clean_unit == "TABLE_CELL":
        return "table"
    return "unknown"


def _map_content_type_to_p5_unit(content_type: str, fallback_unit: str = "TEXT_REGION") -> str:
    """Project Stage 2 content_type back to P5 unit_type."""
    if content_type == "table":
        return "TABLE_CELL"
    if content_type == "page":
        return "PAGE"
    if content_type in {"text", "legal_clause", "heading", "caption"}:
        return "TEXT_REGION"
    return fallback_unit


class MetadataLookup:
    """In-memory lookup for verified region and document metadata.

    Detects and rejects conflicting duplicate records during initialization.
    """

    def __init__(
        self,
        region_records: Optional[Mapping[tuple[str, int, str], dict[str, Any]]] = None,
        document_records: Optional[Mapping[str, dict[str, Any]]] = None,
    ) -> None:
        self.region_records = dict(region_records or {})
        self.document_records = dict(document_records or {})

    def lookup_region(self, doc_id: str, page_number: int, region_id: str) -> Optional[dict[str, Any]]:
        return self.region_records.get((doc_id, page_number, region_id))

    def lookup_document(self, doc_id: str) -> Optional[dict[str, Any]]:
        return self.document_records.get(doc_id)

    @classmethod
    def from_dicts(
        cls,
        regions: Optional[list[dict[str, Any]]] = None,
        documents: Optional[list[dict[str, Any]]] = None,
    ) -> MetadataLookup:
        """Construct MetadataLookup from record lists, detecting duplicate/conflicting records."""
        reg_map: dict[tuple[str, int, str], dict[str, Any]] = {}
        if regions:
            for r in regions:
                doc_id = str(r.get("doc_id", "")).strip()
                page_num = int(r.get("page_number", 0))
                reg_id = str(r.get("region_id", "")).strip()
                if not (doc_id and page_num and reg_id):
                    continue
                key = (doc_id, page_num, reg_id)
                if key in reg_map:
                    existing = reg_map[key]
                    if existing != r:
                        raise ValueError(
                            f"Conflicting duplicate region lookup record for key {key}: "
                            f"{existing} vs {r}"
                        )
                else:
                    reg_map[key] = r

        doc_map: dict[str, dict[str, Any]] = {}
        if documents:
            for d in documents:
                doc_id = str(d.get("doc_id", "")).strip()
                if not doc_id:
                    continue
                if doc_id in doc_map:
                    existing = doc_map[doc_id]
                    if existing != d:
                        raise ValueError(
                            f"Conflicting duplicate document lookup record for doc_id '{doc_id}': "
                            f"{existing} vs {d}"
                        )
                else:
                    doc_map[doc_id] = d

        return cls(region_records=reg_map, document_records=doc_map)


class P5EvidenceAdapter:
    """Bidirectional adapter between P5 Evidence and Stage 2 EvidenceItem.

    Guarantees:
    - Zero mutation of the incoming P5 Evidence.
    - Full retention of all 11 fields of P5 Evidence.
    - Zero fabrication of bbox or document_version when unverified or absent.
    - Strict separation of document_number, publication_date, legal_status, and document_version.
    - Rejection of mismatched document, page, or region joins.
    """

    @staticmethod
    def from_p5_evidence(
        p5_item: Evidence,
        lookup: Optional[MetadataLookup] = None,
    ) -> EvidenceItem:
        """Convert a P5 Evidence dataclass to an enriched EvidenceItem.

        Args:
            p5_item: Frozen P5 Evidence instance.
            lookup: Optional MetadataLookup providing verified bbox and document metadata.

        Returns:
            EvidenceItem populated with all P5 fields and verified enriched metadata.
        """
        region_id = p5_item.evidence_id if p5_item.evidence_id.startswith("REG_") else None
        content_type = _map_p5_content_type(p5_item.unit_type, p5_item.context_role)

        bbox: Optional[tuple[float, float, float, float]] = None
        document_number: Optional[str] = None
        document_version: Optional[str] = None
        publication_date: Optional[str] = None
        legal_status: Optional[str] = None

        provenance_metadata: dict[str, Any] = {
            "adapter": "P5EvidenceAdapter",
            "p5_source": p5_item.source,
            "p5_unit_type": p5_item.unit_type,
            "p5_truncated": p5_item.truncated,
            "enriched_fields": [],
        }

        if lookup is not None:
            # 1. Verified region lookup with full identity validation
            expected_reg_id = region_id or p5_item.evidence_id
            reg_key = (p5_item.doc_id, p5_item.page_number, expected_reg_id)
            region_record = lookup.lookup_region(*reg_key)
            if region_record is not None:
                rec_doc = str(region_record.get("doc_id", "")).strip()
                rec_page = int(region_record.get("page_number", 0))
                rec_reg = str(region_record.get("region_id", "")).strip()
                if rec_doc != p5_item.doc_id or rec_page != p5_item.page_number or rec_reg != expected_reg_id:
                    raise ValueError(
                        f"Mismatched region metadata join: expected ({p5_item.doc_id}, {p5_item.page_number}, {expected_reg_id}), "
                        f"got ({rec_doc}, {rec_page}, {rec_reg})"
                    )
                raw_bbox = region_record.get("bbox")
                if raw_bbox is not None and len(raw_bbox) == 4:
                    bbox = tuple(float(x) for x in raw_bbox)
                    provenance_metadata["enriched_fields"].append("bbox")
                    provenance_metadata["bbox_source"] = "verified_region_record"

            # 2. Verified document lookup with doc_id validation and clean field separation
            doc_record = lookup.lookup_document(p5_item.doc_id)
            if doc_record is not None:
                rec_doc_id = str(doc_record.get("doc_id", "")).strip()
                if rec_doc_id != p5_item.doc_id:
                    raise ValueError(
                        f"Mismatched document metadata join: expected doc_id '{p5_item.doc_id}', "
                        f"got '{rec_doc_id}'"
                    )

                # Separate document_number, publication_date, legal_status, and document_version
                raw_doc_num = doc_record.get("document_number")
                if raw_doc_num:
                    document_number = str(raw_doc_num).strip()
                    provenance_metadata["enriched_fields"].append("document_number")

                raw_pub_date = doc_record.get("publication_date")
                if raw_pub_date:
                    publication_date = str(raw_pub_date).strip()
                    provenance_metadata["enriched_fields"].append("publication_date")

                raw_legal_status = doc_record.get("version_status")
                if raw_legal_status:
                    legal_status = str(raw_legal_status).strip()
                    provenance_metadata["enriched_fields"].append("legal_status")

                # Document version: MUST NOT be inferred solely from date or document number!
                raw_version = doc_record.get("document_version") or doc_record.get("version_id") or doc_record.get("version")
                if raw_version:
                    document_version = str(raw_version).strip()
                    provenance_metadata["enriched_fields"].append("document_version")
                    provenance_metadata["document_version_source"] = "verified_document_record"
                else:
                    document_version = None

        return EvidenceItem(
            evidence_id=p5_item.evidence_id,
            doc_id=p5_item.doc_id,
            page_id=p5_item.page_id,
            page_number=p5_item.page_number,
            content_type=content_type,
            text=p5_item.text,
            source=p5_item.source,
            region_id=region_id,
            bbox=bbox,
            document_number=document_number,
            document_version=document_version,
            publication_date=publication_date,
            legal_status=legal_status,
            rank=p5_item.rank,
            score=p5_item.score,
            context_group=p5_item.context_group or None,
            context_role=p5_item.context_role or None,
            truncated=p5_item.truncated,
            provenance_metadata=provenance_metadata,
        )

    @staticmethod
    def to_p5_evidence(item: EvidenceItem) -> Evidence:
        """Project an EvidenceItem back to a P5 Evidence dataclass.

        Note: New Stage 2 fields (bbox, document_version, document_number, etc.)
        cannot be stored in the frozen P5 Evidence contract and are dropped.
        """
        unit_type = item.provenance_metadata.get("p5_unit_type")
        if not unit_type:
            unit_type = _map_content_type_to_p5_unit(item.content_type)

        return Evidence(
            rank=item.rank if item.rank is not None else 1,
            evidence_id=item.evidence_id,
            doc_id=item.doc_id,
            page_id=item.page_id,
            page_number=item.page_number,
            unit_type=unit_type,
            score=item.score if item.score is not None else 0.0,
            text=item.text,
            source=item.source,
            truncated=item.truncated,
            context_group=item.context_group or "",
            context_role=item.context_role or "",
        )
