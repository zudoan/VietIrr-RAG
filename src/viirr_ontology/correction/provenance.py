"""Provenance and Structural Relationship Verification for Stage 3.

Provides:
- ProvenanceValidationStatus: Enum distinguishing SYNTACTIC_VALID, INDEX_VERIFIED, and UNVERIFIED.
- DocumentIdentityRegistry: Strict exact document identity matching and verified alias mapping.
  Never uses substring or loose fuzzy matching. Rejects contradictory doc_id vs document_number.
  Enforces required version presence.
- TrustedSourceStructureRegistry: Authoritative source-controlled registry of document structures
  (tables, blocks, parent-child hierarchies, parser relations) keyed by document/page/evidence identity.
- StructuralRelationVerifier: Validates that complementary evidence regions possess a genuine
  source-backed structural relationship before any EvidenceRelation can be marked verified=True.
  Rejects self-declared or unverified metadata. Rejects mismatched relation types (e.g. table_id
  cannot certify clause_to_condition or evidence_to_version).
- EvidenceProvenanceValidator: Multi-tier provenance validation enforcing syntactic validity,
  exact document scope, version constraints, and optional source-index identity verification.
"""

from __future__ import annotations

from enum import Enum
import json
from pathlib import Path
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional, Union

from viirr_ontology.schema.evidence import EvidenceItem, EvidenceRelation


class ProvenanceValidationStatus(str, Enum):
    """Explicit multi-tier provenance validation statuses."""

    SYNTACTIC_VALID = "SYNTACTIC_VALID"
    INDEX_VERIFIED = "INDEX_VERIFIED"
    CONTENT_VERIFIED = "CONTENT_VERIFIED"
    UNVERIFIED = "UNVERIFIED"


def normalize_doc_identifier(val: str) -> str:
    """Normalize document identifier standardizing case, unicode, and stripping whitespace."""
    if not val:
        return ""
    norm = unicodedata.normalize("NFKC", str(val)).strip()
    return norm.upper()


def normalize_evidence_text(val: Optional[str]) -> str:
    """Safely normalize evidence text without modifying numbers, units, negations, or technical terms.

    Preserves:
    - All digits and numeric values (117, 1.7, 1,7, 70391, etc.)
    - All units (m, ha, %, ‰, m3/s, etc.)
    - All legal/technical negations and qualifiers (không, chưa, cấm, không được, ngoài đê, trong đê)

    Only standardizes:
    - Unicode normalization (NFKC)
    - Whitespace collapsing and trimming
    """
    if not val:
        return ""
    norm = unicodedata.normalize("NFKC", str(val))
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm


class DocumentIdentityRegistry:
    """Strict document identity validator with explicit, verified canonical alias mapping.

    Rules:
    - Never uses substring matching (e.g. 'DOC_A' vs 'DOC_A_EVIL' will NEVER match).
    - Canonical exact match: normalize(claim_scope) == normalize(item_doc_id).
    - Verified aliases: Aliases are only accepted if explicitly registered in the verified alias map.
    - Preserves separation between document ID, document number, publication date, and version.
    - When an explicit version is required, missing version must NOT count as a verified match.
    - Rejects contradictory canonical document ID and document number metadata.
    """

    def __init__(self, verified_aliases: Optional[dict[str, set[str]]] = None):
        # Maps canonical_id -> set of verified alias strings (e.g. "DOC_740" -> {"740/QĐ-TTG", "740/QD-TTG"})
        self._canonical_to_aliases: dict[str, set[str]] = {}
        self._alias_to_canonical: dict[str, str] = {}

        # Default authoritative repository aliases
        default_aliases = {
            "DOC_740": {"740/QĐ-TTG", "740/QD-TTG", "DOC_740", "QUYẾT ĐỊNH SỐ 740/QĐ-TTG", "QUYET DINH 740/QD-TTG"},
            "DOC_922": {"922/QĐ-TTG", "922/QD-TTG", "DOC_922", "QUYẾT ĐỊNH SỐ 922/QĐ-TTG"},
        }
        if verified_aliases:
            default_aliases.update(verified_aliases)

        for canonical, aliases in default_aliases.items():
            self.register_document(canonical, aliases)

    def register_document(self, canonical_id: str, aliases: Optional[set[str]] = None) -> None:
        """Register a canonical document ID and its verified aliases."""
        c_norm = normalize_doc_identifier(canonical_id)
        if not c_norm:
            return
        alias_set = {normalize_doc_identifier(a) for a in (aliases or set()) if a}
        alias_set.add(c_norm)

        self._canonical_to_aliases[c_norm] = alias_set
        for a in alias_set:
            self._alias_to_canonical[a] = c_norm

    def get_canonical_id(self, doc_identifier: str) -> Optional[str]:
        """Resolve a document identifier or verified alias to its canonical ID."""
        norm = normalize_doc_identifier(doc_identifier)
        if not norm:
            return None
        return self._alias_to_canonical.get(norm, norm)

    def is_scope_matching(
        self,
        claim_scope: Optional[str],
        item_doc_id: str,
        item_doc_number: Optional[str] = None,
        item_doc_version: Optional[str] = None,
        claim_version: Optional[str] = None,
    ) -> bool:
        """Strictly determine whether an item satisfies the claim's document scope.

        Exact matching only. Substrings, prefixes, and suffixes are strictly rejected.
        Enforces version presence when claim_version is specified.
        Rejects contradictory item_doc_id vs item_doc_number.
        """
        # 1. Version enforcement: When an explicit version is required, missing version must NOT match
        if claim_version and str(claim_version).strip():
            if not item_doc_version or not str(item_doc_version).strip():
                return False
            if normalize_doc_identifier(claim_version) != normalize_doc_identifier(item_doc_version):
                return False

        item_doc_norm = normalize_doc_identifier(item_doc_id)
        item_num_norm = normalize_doc_identifier(item_doc_number or "")

        # 2. Reject contradictory canonical document ID and document number metadata
        if item_num_norm and item_num_norm != item_doc_norm:
            canon_id = self.get_canonical_id(item_doc_norm)
            canon_num = self.get_canonical_id(item_num_norm)
            # If not verified aliases of each other, this metadata is contradictory
            if not (canon_id and canon_num and canon_id == canon_num):
                return False

        if not claim_scope or not claim_scope.strip():
            return True  # No claim scope restriction specified

        claim_norm = normalize_doc_identifier(claim_scope)

        # 3. Exact canonical equality
        if claim_norm == item_doc_norm:
            return True

        # 4. Verified alias lookup for item_doc_id
        claim_canonical = self.get_canonical_id(claim_norm)
        item_canonical = self.get_canonical_id(item_doc_norm)
        if claim_canonical and item_canonical and claim_canonical == item_canonical:
            return True

        # 5. Verified alias lookup for item_doc_number (only if consistent with item_doc_id)
        if item_num_norm:
            num_canonical = self.get_canonical_id(item_num_norm)
            if item_canonical and num_canonical and item_canonical == num_canonical:
                if claim_canonical and claim_canonical == num_canonical:
                    return True

        # Substrings, prefix collisions (e.g. DOC_A vs DOC_A_EVIL) are strictly rejected!
        return False


class TrustedSourceStructureRegistry:
    """Authoritative source-controlled registry of document structures and parser relations.

    Prevents forged or self-declared metadata from being promoted to verified links.
    Stores verified tables, blocks, and parent-child hierarchies keyed by document/page/evidence identity.
    """

    def __init__(
        self,
        trusted_tables: Optional[dict[tuple[str, int, str], str]] = None,
        trusted_blocks: Optional[dict[tuple[str, int, str], str]] = None,
        trusted_parents: Optional[dict[tuple[str, int, str], str]] = None,
        trusted_relations: Optional[dict[tuple[str, str], str]] = None,
    ):
        self._trusted_tables: dict[tuple[str, int, str], str] = dict(trusted_tables or {})
        self._trusted_blocks: dict[tuple[str, int, str], str] = dict(trusted_blocks or {})
        self._trusted_parents: dict[tuple[str, int, str], str] = dict(trusted_parents or {})
        self._trusted_relations: dict[tuple[str, str], str] = dict(trusted_relations or {})

    def register_table_unit(self, doc_id: str, page_number: int, evidence_id: str, table_id: str) -> None:
        """Register an authoritative table identifier for a document page evidence item."""
        norm_doc = normalize_doc_identifier(doc_id)
        self._trusted_tables[(norm_doc, int(page_number), str(evidence_id))] = str(table_id).strip()

    def register_block_unit(self, doc_id: str, page_number: int, evidence_id: str, block_id: str) -> None:
        """Register an authoritative block identifier for a document page evidence item."""
        norm_doc = normalize_doc_identifier(doc_id)
        self._trusted_blocks[(norm_doc, int(page_number), str(evidence_id))] = str(block_id).strip()

    def register_parent_unit(self, doc_id: str, page_number: int, evidence_id: str, parent_id: str) -> None:
        """Register an authoritative parent hierarchy identifier for an evidence item."""
        norm_doc = normalize_doc_identifier(doc_id)
        self._trusted_parents[(norm_doc, int(page_number), str(evidence_id))] = str(parent_id).strip()

    def register_relation(self, source_id: str, target_id: str, relation_type: str) -> None:
        """Register an explicit authoritative parser relationship between two evidence IDs."""
        self._trusted_relations[(str(source_id), str(target_id))] = str(relation_type)

    def register_evidence_item(
        self,
        item: EvidenceItem,
        table_id: Optional[str] = None,
        block_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> None:
        """Convenience helper to register an EvidenceItem into authoritative records."""
        if table_id:
            self.register_table_unit(item.doc_id, item.page_number, item.evidence_id, table_id)
        if block_id:
            self.register_block_unit(item.doc_id, item.page_number, item.evidence_id, block_id)
        if parent_id:
            self.register_parent_unit(item.doc_id, item.page_number, item.evidence_id, parent_id)

    def get_table_id(self, doc_id: str, page_number: int, evidence_id: str) -> Optional[str]:
        norm_doc = normalize_doc_identifier(doc_id)
        return self._trusted_tables.get((norm_doc, int(page_number), str(evidence_id)))

    def get_block_id(self, doc_id: str, page_number: int, evidence_id: str) -> Optional[str]:
        norm_doc = normalize_doc_identifier(doc_id)
        return self._trusted_blocks.get((norm_doc, int(page_number), str(evidence_id)))

    def get_parent_id(self, doc_id: str, page_number: int, evidence_id: str) -> Optional[str]:
        norm_doc = normalize_doc_identifier(doc_id)
        return self._trusted_parents.get((norm_doc, int(page_number), str(evidence_id)))

    def get_relation_type(self, source_id: str, target_id: str) -> Optional[str]:
        rel = self._trusted_relations.get((str(source_id), str(target_id)))
        if rel is None:
            rel = self._trusted_relations.get((str(target_id), str(source_id)))
        return rel

    def load_from_evidence_units(self, file_path: Union[str, Path]) -> int:
        """Extract authoritative structural relations from read-only parser records."""
        p = Path(file_path)
        if not p.exists():
            return 0
        count = 0
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    doc_id = data.get("doc_id")
                    page_num = data.get("page_number")
                    ev_id = data.get("evidence_id")
                    table_id = data.get("table_id") or (data.get("provenance", {}).get("table_id") if isinstance(data.get("provenance"), dict) else None)
                    block_id = data.get("block_id") or (data.get("provenance", {}).get("block_id") if isinstance(data.get("provenance"), dict) else None)
                    parent_id = data.get("parent_id") or (data.get("provenance", {}).get("parent_id") if isinstance(data.get("provenance"), dict) else None)
                    if doc_id and page_num is not None and ev_id:
                        if table_id:
                            self.register_table_unit(doc_id, int(page_num), ev_id, str(table_id).strip())
                            count += 1
                        if block_id:
                            self.register_block_unit(doc_id, int(page_num), ev_id, str(block_id).strip())
                            count += 1
                        if parent_id:
                            self.register_parent_unit(doc_id, int(page_num), ev_id, str(parent_id).strip())
                            count += 1
                except Exception:
                    continue
        return count


VALID_TABLE_RELATION_TYPES = {
    "table_row_to_header",
    "table_to_caption",
    "table_to_note",
}


class StructuralRelationVerifier:
    """Verifies that two candidate evidence items possess a genuine structural connection.

    Never manufactures verified links from keywords, same document alone, or missing-slot categories.
    Never equates metadata presence with trusted parser verification.
    Validates structural relationships against source-controlled records in TrustedSourceStructureRegistry.
    """

    def __init__(
        self,
        trusted_structure_registry: Optional[TrustedSourceStructureRegistry] = None,
        trusted_parser_relations: Optional[set[tuple[str, str]]] = None,
        identity_registry: Optional[DocumentIdentityRegistry] = None,
    ):
        self.trusted_registry = trusted_structure_registry or TrustedSourceStructureRegistry()
        self._identity_registry = identity_registry or DocumentIdentityRegistry()
        if trusted_parser_relations:
            for src, tgt in trusted_parser_relations:
                self.trusted_registry.register_relation(src, tgt, "pdf_layout_parser_structure")

    def verify_relation(
        self,
        source_item: EvidenceItem,
        target_item: EvidenceItem,
        candidate_relation_type: str,
    ) -> tuple[bool, str]:
        """Check whether a relationship between two items is genuinely verified by structure.

        Returns:
            (is_verified: bool, provenance_source: str)
        """
        # Rule 1: Must belong to the exact same canonical document
        if not self._identity_registry.is_scope_matching(source_item.doc_id, target_item.doc_id):
            return False, "document_mismatch"

        # Rule 2: Check explicit trusted parser relation mapping in registry
        reg_type = self.trusted_registry.get_relation_type(source_item.evidence_id, target_item.evidence_id)
        if reg_type is not None:
            if reg_type == candidate_relation_type or reg_type == "pdf_layout_parser_structure":
                return True, f"trusted_parser_relation:{reg_type}"
            else:
                return False, f"mismatched_relation_type:registered_{reg_type}_vs_candidate_{candidate_relation_type}"

        # Rule 3: Check trusted source table structure in TrustedSourceStructureRegistry
        s_table = self.trusted_registry.get_table_id(source_item.doc_id, source_item.page_number, source_item.evidence_id)
        t_table = self.trusted_registry.get_table_id(target_item.doc_id, target_item.page_number, target_item.evidence_id)

        # Detect self-declared or unverified metadata
        s_self_table = (source_item.provenance_metadata or {}).get("table_id")
        t_self_table = (target_item.provenance_metadata or {}).get("table_id")
        if (s_self_table or t_self_table) and (s_table is None or t_table is None):
            # Self-declared unverified metadata! Do not equate metadata presence with trusted parser verification!
            return False, "untrusted_self_declared_metadata"

        if s_table and t_table and s_table == t_table:
            # Table ID cannot certify evidence_to_version or clause_to_condition!
            if candidate_relation_type not in VALID_TABLE_RELATION_TYPES:
                return False, f"mismatched_relation_type:table_id_cannot_certify_{candidate_relation_type}"

            page_diff = abs(source_item.page_number - target_item.page_number)
            if page_diff <= 1:
                return True, f"trusted_parser_table_structure:{s_table}"
            else:
                # Distant pages sharing a table ID is suspicious / unverified
                return False, f"table_page_disparity:page_{source_item.page_number}_vs_{target_item.page_number}"

        # Rule 4: Check trusted block / parent-child hierarchy
        s_parent = self.trusted_registry.get_parent_id(source_item.doc_id, source_item.page_number, source_item.evidence_id)
        t_parent = self.trusted_registry.get_parent_id(target_item.doc_id, target_item.page_number, target_item.evidence_id)
        s_block = self.trusted_registry.get_block_id(source_item.doc_id, source_item.page_number, source_item.evidence_id)
        t_block = self.trusted_registry.get_block_id(target_item.doc_id, target_item.page_number, target_item.evidence_id)

        if candidate_relation_type == "parent_to_child":
            if s_parent and s_parent == target_item.evidence_id:
                return True, "trusted_parent_child_hierarchy"
            if t_parent and t_parent == source_item.evidence_id:
                return True, "trusted_parent_child_hierarchy"
            if s_block and t_block and s_block == t_block and source_item.page_number == target_item.page_number:
                return True, f"trusted_block_structure:{s_block}"

        # Missing trusted parser metadata must result in an unverified relation!
        # Keyword coincidence, same page alone, or unverified self-declared metadata is NOT verification.
        return False, "unverified_candidate_metadata"


class EvidenceProvenanceValidator:
    """Validates evidence item metadata and provenance against claim scope and trusted sources."""

    def __init__(
        self,
        identity_registry: Optional[DocumentIdentityRegistry] = None,
        trusted_index_evidence_ids: Optional[set[tuple[str, int, str]]] = None,
        trusted_evidence_content: Optional[dict[tuple[str, int, str], str]] = None,
    ):
        self.identity_registry = identity_registry or DocumentIdentityRegistry()
        self.trusted_index = set(trusted_index_evidence_ids) if trusted_index_evidence_ids else set()
        self.trusted_content: dict[tuple[str, int, str], str] = (
            dict(trusted_evidence_content) if trusted_evidence_content else {}
        )

    def register_verified_index_evidence(
        self, doc_id: str, page_number: int, evidence_id: str, content: Optional[str] = None
    ) -> None:
        """Register a verified document/page/evidence key in the trusted source index with optional canonical content."""
        norm_doc = normalize_doc_identifier(doc_id)
        key = (norm_doc, int(page_number), str(evidence_id).strip())
        self.trusted_index.add(key)
        if content is not None:
            self.trusted_content[key] = str(content)

    def load_trusted_index_from_file(self, file_path: Union[str, Path], load_content: bool = True) -> int:
        """Load authoritative (doc_id, page_number, evidence_id) citations and content from a JSONL index file."""
        p = Path(file_path)
        if not p.exists():
            return 0
        count = 0
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    doc_id = data.get("doc_id")
                    page_num = data.get("page_number")
                    ev_id = data.get("evidence_id") or data.get("region_id")
                    raw_content = (
                        data.get("raw_text")
                        or data.get("index_text")
                        or data.get("text")
                        or data.get("normalized_text")
                    )
                    if doc_id and page_num is not None and ev_id:
                        self.register_verified_index_evidence(
                            str(doc_id).strip(),
                            int(page_num),
                            str(ev_id).strip(),
                            content=str(raw_content) if (load_content and raw_content is not None) else None,
                        )
                        count += 1
                except Exception:
                    continue
        return count

    def validate_provenance(
        self,
        item: EvidenceItem,
        required_document_scope: Optional[str] = None,
        required_version: Optional[str] = None,
        require_index_verification: bool = False,
        require_content_verification: bool = False,
    ) -> tuple[ProvenanceValidationStatus, str]:
        """Validate an evidence item's provenance and content authenticity.

        Returns:
            (status: ProvenanceValidationStatus, detail_reason: str)
        """
        # 1. Syntactic validity
        if not item.doc_id or not item.doc_id.strip():
            return ProvenanceValidationStatus.UNVERIFIED, "EMPTY_DOC_ID"
        if not item.evidence_id or not item.evidence_id.strip():
            return ProvenanceValidationStatus.UNVERIFIED, "EMPTY_EVIDENCE_ID"
        if item.page_number < 1:
            return ProvenanceValidationStatus.UNVERIFIED, "INVALID_PAGE_NUMBER"
        if item.bbox is not None:
            if len(item.bbox) != 4 or item.bbox[2] < item.bbox[0] or item.bbox[3] < item.bbox[1]:
                return ProvenanceValidationStatus.UNVERIFIED, "MALFORMED_BBOX"

        # 2. Version requirement enforcement (Independent of document scope - Phase A3)
        if required_version and str(required_version).strip():
            if not item.document_version or not str(item.document_version).strip():
                return (
                    ProvenanceValidationStatus.UNVERIFIED,
                    f"DOCUMENT_VERSION_MISSING:requested_version_{required_version}_item_has_no_version",
                )
            if normalize_doc_identifier(required_version) != normalize_doc_identifier(item.document_version):
                return (
                    ProvenanceValidationStatus.UNVERIFIED,
                    f"DOCUMENT_VERSION_MISMATCH:requested_version_{required_version}_got_{item.document_version}",
                )

        # 3. Document scope matching (Exact matching, no prefixes or substrings)
        if required_document_scope and str(required_document_scope).strip():
            if not self.identity_registry.is_scope_matching(
                claim_scope=required_document_scope,
                item_doc_id=item.doc_id,
                item_doc_number=item.document_number,
                item_doc_version=item.document_version,
                claim_version=required_version,
            ):
                return (
                    ProvenanceValidationStatus.UNVERIFIED,
                    f"DOCUMENT_SCOPE_MISMATCH:requested_{required_document_scope}_got_{item.doc_id}",
                )

        # 4. Source index & content verification check (Strict Provenance Gate)
        norm_doc = normalize_doc_identifier(item.doc_id)
        norm_ev_id = str(item.evidence_id).strip()
        citation_key = (norm_doc, int(item.page_number), norm_ev_id)
        is_index_verified = bool(self.trusted_index and citation_key in self.trusted_index)

        # Enforce index identity in strict mode: trusted content ALONE cannot bypass the index check
        if require_index_verification:
            if not self.trusted_index:
                # Fail closed if the trusted source index is required but unavailable
                return ProvenanceValidationStatus.UNVERIFIED, "TRUSTED_SOURCE_INDEX_UNAVAILABLE"
            if not is_index_verified:
                return ProvenanceValidationStatus.UNVERIFIED, f"UNTRUSTED_SOURCE_IDENTITY:{citation_key}"

        # Content verification: check consistency against canonical content
        canonical_content = self.trusted_content.get(citation_key)
        if canonical_content is not None:
            norm_item_text = normalize_evidence_text(item.text)
            norm_canon_text = normalize_evidence_text(canonical_content)
            if norm_item_text != norm_canon_text:
                # Content mismatch: valid ID but altered/corrupted text! Reject!
                return (
                    ProvenanceValidationStatus.UNVERIFIED,
                    f"CONTENT_MISMATCH:item_text_differs_from_trusted_source_for_{citation_key}",
                )
            # CONTENT_VERIFIED strictly requires a verified index citation identity
            if is_index_verified:
                return ProvenanceValidationStatus.CONTENT_VERIFIED, "PROVENANCE_CONTENT_VERIFIED"
            # If content matches but index identity was not verified in trusted_index:
            return ProvenanceValidationStatus.SYNTACTIC_VALID, f"CONTENT_MATCH_BUT_INDEX_UNVERIFIED:{citation_key}"

        if require_content_verification and canonical_content is None:
            if not self.trusted_content:
                return ProvenanceValidationStatus.UNVERIFIED, "TRUSTED_SOURCE_CONTENT_UNAVAILABLE"
            return ProvenanceValidationStatus.UNVERIFIED, f"UNTRUSTED_SOURCE_CONTENT_MISSING:{citation_key}"

        if is_index_verified:
            return ProvenanceValidationStatus.INDEX_VERIFIED, "PROVENANCE_INDEX_VERIFIED"

        return ProvenanceValidationStatus.SYNTACTIC_VALID, "PROVENANCE_SYNTACTIC_VALID"

    def validate_item(
        self,
        item: EvidenceItem,
        required_document_scope: Optional[str] = None,
        required_version: Optional[str] = None,
        require_index_verification: bool = False,
        require_content_verification: bool = False,
    ) -> tuple[bool, str]:
        """Convenience boolean validator for backwards compatibility."""
        status, reason = self.validate_provenance(
            item=item,
            required_document_scope=required_document_scope,
            required_version=required_version,
            require_index_verification=require_index_verification,
            require_content_verification=require_content_verification,
        )
        return (status != ProvenanceValidationStatus.UNVERIFIED, reason)
