"""
Source-Faithful Evidence Bundler for VietIRR-RAG (Hardened & Scientific Integrity Compliant).

Strict Scientific Contracts:
1. IMMUTABLE RAW SOURCE: `raw_source_text` is NEVER overwritten, modified, or constructed
   from downstream claim values or benchmark reference answers.
2. NO CO-OCCURRENCE VERIFICATION: Co-occurrence of a number and an entity NEVER automatically
   makes a relationship VERIFIED_STRUCTURAL.
3. EXPLICIT STRUCTURAL CRITERIA: A relationship is labeled `VERIFIED_STRUCTURAL` ONLY when
   authentic source layout metadata (such as explicit table grid, row/column bindings, or cell coordinates)
   is independently present. Otherwise, it is strictly labeled `RELATION_UNVERIFIED`.
4. PREVENTS SELF-CONFIRMATION: Does not accept `claim.value` or reference answers as inputs.
5. DOWNSTREAM CONVERSION: Provides conversion to `EvidenceItem` and `EvidenceSet` for Stage 2 & 3.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from viirr_ontology.schema.evidence import EvidenceItem, EvidenceSet


HYDRAULIC_ENTITIES_CANONICAL = [
    "Tả Trạch", "Bình Điền", "Hương Điền", "Hòa Bình", "Sơn La", "Thác Bà",
    "Dầu Tiếng", "Trị An", "Bản Vẽ", "Cửa Đạt", "Ngàn Trươi", "Núi Cốc", "Đại Lải",
    "Yên Lập", "Bằng Giang", "Lục Nam", "Đồng Nai", "Sông Hương", "Sông Hồng",
    "Mê Công", "Đồng bằng sông Cửu Long", "ĐBSCL", "Bắc Nam Hà", "Nam Trung Bộ",
    "Cao Bằng", "Lạng Sơn", "Bắc Giang"
]

HYDRAULIC_PARAMS_CANONICAL = [
    "mực nước dâng bình thường", "mực nước chết", "mực nước lũ thiết kế", "mực nước lũ kiểm tra",
    "mực nước", "cao trình", "dung tích hữu ích", "dung tích toàn bộ", "dung tích phòng lũ",
    "dung tích", "lưu lượng xả", "lưu lượng đến", "lưu lượng", "lượng mưa lũy tích",
    "lượng mưa trong tháng", "lượng mưa", "diện tích đáp ứng", "độ mặn", "chất lượng nước"
]

HYDRAULIC_UNITS_CANONICAL = [
    "triệu m3", "m3/s", "mg/l", "g/l", "mm", "ha", "m", "%", "‰"
]


@dataclass
class EvidenceBundle:
    """Represents an immutable, source-anchored evidence unit (M3-C Compliant)."""
    bundle_id: str
    doc_id: str
    page_number: int
    region_id: str
    page_id: str
    unit_type: str                   # 'paragraph', 'table_block', 'table_row', 'table_cell'
    raw_source_text: str             # Immutable raw source text from PDF/OCR
    document_hash: str = ""          # Immutable document hash or canonical version
    source_locator: str = ""         # Canonical locator e.g. doc:page:region
    content_type: str = "text"       # 'text' or 'table'
    table_id: Optional[str] = None   # Table ID if authentic layout proves it
    row_id: Optional[str] = None     # Row ID if authentic layout proves it
    column_id: Optional[str] = None  # Column ID if authentic layout proves it
    extracted_entity: Optional[str] = None
    extracted_parameter: Optional[str] = None
    extracted_value: Optional[float] = None
    extracted_unit: Optional[str] = None
    condition: Optional[str] = None
    relationship_status: str = "RELATION_UNVERIFIED" # 'VERIFIED_STRUCTURAL' or 'RELATION_UNVERIFIED'
    confidence: float = 0.5
    source_provenance: str = ""
    structural_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_evidence_item(self) -> EvidenceItem:
        """Converts to official Stage 2 EvidenceItem preserving provenance identity."""
        content_type = "table" if ("table" in self.unit_type or "TAB_" in self.region_id) else "text"
        return EvidenceItem(
            evidence_id=self.region_id,
            doc_id=self.doc_id,
            page_id=self.page_id,
            page_number=self.page_number,
            content_type=content_type,
            text=self.raw_source_text,
            source=self.source_provenance,
            region_id=self.region_id,
            document_number=self.doc_id,
            document_version=self.doc_id,
            provenance_metadata={
                "bundle_id": self.bundle_id,
                "relationship_status": self.relationship_status,
                "confidence": self.confidence,
                "extracted_entity": self.extracted_entity,
                "extracted_parameter": self.extracted_parameter,
                "extracted_value": self.extracted_value,
                "extracted_unit": self.extracted_unit,
                "condition": self.condition,
                "table_id": self.table_id,
                "row_id": self.row_id,
                "column_id": self.column_id,
                "structural_metadata": self.structural_metadata,
            }
        )


class SourceFaithfulEvidenceBundler:
    """
    Constructs Evidence Bundles strictly from retrieved raw evidence units.
    Adheres strictly to scientific integrity:
    - Never uses claim values or reference answers to fabricate evidence.
    - Never marks co-occurring text as VERIFIED_STRUCTURAL without layout proof.
    """

    def __init__(self):
        pass

    def extract_independent_fields(self, text: str) -> dict[str, Any]:
        """
        Extracts entities, parameters, numbers, and units strictly from raw text
        using deterministic regex and canonical vocabulary.
        """
        text_lower = text.lower()

        # 1. Entity
        found_entity = None
        for ent in HYDRAULIC_ENTITIES_CANONICAL:
            if ent.lower() in text_lower:
                found_entity = ent
                break

        # 2. Parameter
        found_param = None
        for param in HYDRAULIC_PARAMS_CANONICAL:
            if param.lower() in text_lower:
                found_param = param
                break

        # 3. Numeric Value & Unit
        found_val = None
        found_unit = None

        unit_pattern = r"((?<!\w)[+-]?\d+([.,]\d+)?)\s*(triệu\s*m3|m3/s|mg/l|g/l|mm|ha|m|%|‰)\b"
        match = re.search(unit_pattern, text, re.IGNORECASE)
        if match:
            num_str = match.group(1).replace(",", ".")
            try:
                found_val = float(num_str)
                found_unit = match.group(3).strip()
            except ValueError:
                pass
        else:
            num_match = re.search(r"(?<!\w)[+-]?\d+([.,]\d+)?\b", text)
            if num_match:
                try:
                    found_val = float(num_match.group(0).replace(",", "."))
                except ValueError:
                    pass

        # 4. Condition / Temporal Scope
        found_condition = None
        condition_keywords = [
            "mùa lũ", "mùa kiệt", "mùa cạn", "thời kỳ gia tăng", "lũ chính vụ",
            "tuần", "tháng", "đợt 1", "đợt 2", "đợt 3", "đợt 4", "đợt 5"
        ]
        for cond in condition_keywords:
            if cond in text_lower:
                found_condition = cond
                break

        return {
            "entity": found_entity,
            "parameter": found_param,
            "value": found_val,
            "unit": found_unit,
            "condition": found_condition,
        }

    def bundle_evidence_unit(
        self,
        raw_unit: dict[str, Any],
        structural_layout_meta: Optional[dict[str, Any]] = None,
    ) -> EvidenceBundle:
        """
        Wraps a raw evidence unit into a verified EvidenceBundle.
        Guarantees that raw_source_text remains 100% faithful to the source.
        Only marks VERIFIED_STRUCTURAL when explicit layout proof exists.
        """
        doc_id = str(raw_unit.get("doc_id", "UNKNOWN"))
        page_num = int(raw_unit.get("page_number", 1))
        region_id = str(raw_unit.get("evidence_id") or raw_unit.get("region_id") or "UNKNOWN")
        unit_type = str(raw_unit.get("unit_type", "paragraph"))
        raw_text = str(raw_unit.get("text") or raw_unit.get("raw_text") or raw_unit.get("index_text") or "")

        # Extract fields independently
        extracted = self.extract_independent_fields(raw_text)

        # STRICT RELATIONSHIP VERIFICATION POLICY:
        # A relationship is VERIFIED_STRUCTURAL ONLY if:
        # 1. Explicit table layout metadata proves authentic grid / cell coordinate structure.
        # 2. OR an explicit table row binding exists with verified header alignment.
        # Mere lexical co-occurrence or table block presence alone is NOT enough!
        has_verified_grid = False
        if structural_layout_meta and structural_layout_meta.get("has_explicit_grid"):
            has_verified_grid = True
        elif structural_layout_meta and structural_layout_meta.get("row_index") is not None and structural_layout_meta.get("col_index") is not None:
            has_verified_grid = True
        elif "cell_coords" in raw_unit:
            has_verified_grid = True
        elif (
            raw_unit.get("relationship_status") == "VERIFIED_STRUCTURAL"
            and raw_unit.get("table_id")
            and raw_unit.get("row_id") is not None
            and raw_unit.get("column_id") is not None
            and raw_unit.get("structural_source") == "parser_pipe_grid"
        ):
            has_verified_grid = True

        if has_verified_grid and extracted["value"] is not None:
            rel_status = "VERIFIED_STRUCTURAL"
            confidence = 0.95
        else:
            # Without explicit structural layout proof, retain uncertainty!
            rel_status = "RELATION_UNVERIFIED"
            confidence = 0.40 if extracted["value"] is not None else 0.20

        bundle_id = f"BUN_{doc_id}_P{page_num:04d}_{region_id}"
        provenance = f"{doc_id}:p.{page_num}:{region_id}"
        doc_hash = str(raw_unit.get("doc_hash") or raw_unit.get("document_hash") or doc_id)
        content_type = "table" if ("table" in unit_type.lower() or "TAB_" in region_id) else "text"
        
        effective_meta = structural_layout_meta or {
            key: raw_unit.get(key)
            for key in ("table_id", "row_id", "column_id", "cell_ref", "structural_source")
            if raw_unit.get(key) is not None
        }
        table_id = effective_meta.get("table_id")
        row_id = effective_meta.get("row_id")
        col_id = effective_meta.get("column_id")

        return EvidenceBundle(
            bundle_id=bundle_id,
            doc_id=doc_id,
            page_number=page_num,
            region_id=region_id,
            page_id=str(raw_unit.get("page_id") or f"PAGE_{doc_id}_{page_num:04d}"),
            unit_type=unit_type,
            raw_source_text=raw_text, # Guaranteed immutable
            document_hash=doc_hash,
            source_locator=provenance,
            content_type=content_type,
            table_id=table_id,
            row_id=row_id,
            column_id=col_id,
            extracted_entity=extracted["entity"],
            extracted_parameter=extracted["parameter"],
            extracted_value=extracted["value"],
            extracted_unit=extracted["unit"],
            condition=extracted["condition"],
            relationship_status=rel_status,
            confidence=confidence,
            source_provenance=provenance,
            structural_metadata=effective_meta,
        )

    def bundle_all(
        self,
        retrieved_units: list[dict[str, Any]],
        table_layout_map: Optional[dict[str, Any]] = None,
    ) -> list[EvidenceBundle]:
        bundles = []
        for u in retrieved_units:
            reg_id = str(u.get("evidence_id") or u.get("region_id"))
            layout_meta = table_layout_map.get(reg_id) if table_layout_map else None
            bundles.append(self.bundle_evidence_unit(u, layout_meta))
        return bundles

    def create_evidence_set(
        self,
        bundles: list[EvidenceBundle],
        query_id: str = "query",
    ) -> EvidenceSet:
        """Creates an official Stage 2 EvidenceSet from EvidenceBundle list."""
        items = [b.to_evidence_item() for b in bundles]
        return EvidenceSet(
            query_id=query_id,
            evidence_items=items,
            evidence_relations=[],
        )
