"""Source-faithful table fact extraction and query-time evidence resolution.

Only parser-emitted pipe-delimited ``TABLE_REGION`` records are interpreted.
No value, row, column, or header is inferred from benchmark answers.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from viirr_retrieval.ontology_query_guide import OntologyQueryGuide, QueryIntent, normalize_vietnamese


_NUMBER_RE = re.compile(r"^[+-]?\d+(?:[.,]\d+)*$")
_UNIT_RE = re.compile(r"\((mm|cm|m|m3/s|m³/s|triệu\s*m3|mg/l|g/l|ha|km2|%|‰)\)", re.IGNORECASE)


def is_table_unit(unit: dict[str, Any]) -> bool:
    unit_type = str(unit.get("unit_type") or "").upper()
    evidence_id = str(unit.get("evidence_id") or unit.get("region_id") or "")
    return "TABLE" in unit_type or evidence_id.startswith("TAB_")


def _cells(line: str) -> list[str]:
    return [re.sub(r"\s+", " ", cell).strip() for cell in line.split("|")]


def _parse_number(raw: str) -> float | None:
    value = raw.strip().replace(" ", "")
    if not _NUMBER_RE.fullmatch(value):
        return None
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    elif value.count(".") > 1:
        value = value.replace(".", "")
    try:
        return float(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class TableFact:
    entity: str
    parameter: str
    raw_value: str
    numeric_value: float | None
    unit: str | None
    condition: str | None
    document_id: str
    page_number: int
    region_id: str
    table_id: str
    row_id: str
    column_id: str
    page_id: str
    source_sha256: str
    header_text: str
    row_text: str
    original_raw_text: str

    @property
    def evidence_id(self) -> str:
        return f"{self.table_id}_{self.row_id}_{self.column_id}"

    def evidence_text(self) -> str:
        unit = f" {self.unit}" if self.unit and self.unit.lower() not in self.raw_value.lower() else ""
        condition = f"; điều kiện/cột: {self.condition}" if self.condition else ""
        clean_header = " | ".join(" ".join(col.split()) for col in self.header_text.split("|") if col.strip() and col.strip().lower() != "none")
        clean_row = " | ".join(" ".join(cell.split()) for cell in self.row_text.split("|") if cell.strip() and cell.strip().lower() != "none")
        header_part = f"\n[TIÊU ĐỀ BẢNG] {clean_header}" if clean_header else ""
        row_part = f"\n[HÀNG NGUỒN] {clean_row}" if clean_row else ""
        return (
            f"[Ô BẢNG NGUỒN] Thực thể: {self.entity}; Thông số: {self.parameter}; "
            f"Giá trị: {self.raw_value}{unit}{condition}.{header_part}{row_part}"
        )

    def to_evidence_dict(self, score: float, page_rank: int) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "region_id": self.evidence_id,
            "doc_id": self.document_id,
            "document_id": self.document_id,
            "page_id": self.page_id,
            "page_number": self.page_number,
            "unit_type": "TABLE_CELL",
            "content_type": "table",
            "text": self.evidence_text(),
            "raw_text": self.evidence_text(),
            "original_raw_text": self.original_raw_text,
            "source_sha256": self.source_sha256,
            "table_id": self.table_id,
            "row_id": self.row_id,
            "column_id": self.column_id,
            "cell_ref": {"row_index": int(self.row_id[1:]), "column_index": int(self.column_id[1:])},
            "entity": self.entity,
            "parameter": self.parameter,
            "raw_value": self.raw_value,
            "numeric_value": self.numeric_value,
            "unit": self.unit,
            "condition": self.condition,
            "relationship_status": "VERIFIED_STRUCTURAL",
            "structural_source": "parser_pipe_grid",
            "allocated_score": float(score),
            "page_rank": int(page_rank),
        }


class TableAwareEvidenceResolver:
    """Build a small in-memory fact index from authentic table-region records."""

    def __init__(self, units: Iterable[dict[str, Any]], query_guide: OntologyQueryGuide | None = None) -> None:
        self.query_guide = query_guide or OntologyQueryGuide()
        self.facts: list[TableFact] = []
        self.facts_by_page: dict[str, list[TableFact]] = {}
        self.facts_by_table: dict[str, list[TableFact]] = {}
        self.facts_by_id: dict[str, TableFact] = {}
        for unit in units:
            if not is_table_unit(unit):
                continue
            for fact in self.parse_table_unit(unit):
                self.facts.append(fact)
                self.facts_by_page.setdefault(fact.page_id, []).append(fact)
                self.facts_by_table.setdefault(fact.table_id, []).append(fact)
                self.facts_by_id[fact.evidence_id] = fact

    def validate_cell(
        self,
        cell_dict: dict[str, Any],
        parent_unit: dict[str, Any] | None = None,
    ) -> tuple[bool, str, TableFact | None]:
        """Validate a TABLE_CELL against source lineage across 4 verification levels:
        1. IDENTITY_VALID: evidence_id exists in authentic parsed table facts.
        2. LOCATION_VALID: document_id, page_number, page_id, table_id strictly match parent.
        3. CONTENT_VALID: raw_value and entity exist in underlying table row text.
        4. RELATION_VALID: authentic entity, parameter, and numeric value are present.
        Returns (is_valid, validation_status, verified_fact).
        """
        evidence_id = str(cell_dict.get("evidence_id") or "")
        fact = self.facts_by_id.get(evidence_id)
        if fact is None:
            return False, "IDENTITY_INVALID: Unknown table cell ID", None

        if parent_unit is None:
            return False, "LOCATION_INVALID: Parent table unit missing from verified index", None

        parent_table_id = str(parent_unit.get("evidence_id") or parent_unit.get("table_id") or parent_unit.get("region_id") or "")
        if fact.table_id != parent_table_id:
            return False, "LOCATION_INVALID: Parent table ID mismatch", None

        cell_doc = str(cell_dict.get("doc_id") or cell_dict.get("document_id") or "")
        parent_doc = str(parent_unit.get("doc_id") or parent_unit.get("document_id") or "")
        if fact.document_id != cell_doc or fact.document_id != parent_doc:
            return False, "LOCATION_INVALID: Document ID mismatch", None

        cell_page_num = int(cell_dict.get("page_number") or 0)
        parent_page_num = int(parent_unit.get("page_number") or 0)
        if fact.page_number != cell_page_num or fact.page_number != parent_page_num:
            return False, "LOCATION_INVALID: Page number mismatch", None

        cell_page_id = str(cell_dict.get("page_id") or "")
        parent_page_id = str(parent_unit.get("page_id") or "")
        if fact.page_id != cell_page_id or fact.page_id != parent_page_id:
            return False, "LOCATION_INVALID: Page ID mismatch", None

        # Content validation: raw_value must be in the row text of the authentic fact
        if fact.raw_value not in fact.row_text or fact.entity not in fact.row_text:
            return False, "CONTENT_INVALID: Cell raw value or entity missing from source row", None

        # Relation validation: entity, parameter, and numeric value must be authentic
        if not fact.entity or not fact.parameter or fact.numeric_value is None:
            return False, "RELATION_INVALID: Incomplete entity, parameter, or numeric value", None

        return True, "RELATION_VALID", fact

    @staticmethod
    def parse_table_unit(unit: dict[str, Any]) -> list[TableFact]:
        index_text = str(unit.get("index_text") or unit.get("raw_text") or "").strip()
        lines = [line.strip() for line in index_text.splitlines() if "|" in line]
        if len(lines) < 2:
            return []
        headers = _cells(lines[0])
        if len(headers) < 2:
            return []

        table_id = str(unit.get("table_id") or unit.get("evidence_id") or unit.get("region_id") or "")
        raw_source = str(unit.get("raw_text") or index_text)
        facts: list[TableFact] = []
        for row_index, line in enumerate(lines[1:]):
            row = _cells(line)
            if len(row) < len(headers):
                row.extend([""] * (len(headers) - len(row)))
            elif len(row) > len(headers):
                row = row[: len(headers) - 1] + [" | ".join(row[len(headers) - 1 :])]

            entity_col = 0
            while entity_col < len(row) and (not row[entity_col] or _NUMBER_RE.fullmatch(row[entity_col])):
                entity_col += 1
            if entity_col >= len(row):
                continue
            entity = row[entity_col]
            if normalize_vietnamese(entity) in {"tong", "trung binh", "none"}:
                continue

            for column_index, raw_value in enumerate(row):
                if column_index == entity_col or not raw_value or raw_value.lower() == "none":
                    continue
                numeric_value = _parse_number(raw_value)
                if numeric_value is None:
                    continue
                parameter = headers[column_index] if column_index < len(headers) else f"cột {column_index}"
                parameter = parameter.strip(" —-")
                unit_match = _UNIT_RE.search(parameter)
                unit_name = unit_match.group(1) if unit_match else None
                condition = parameter if "—" in headers[column_index] or any(
                    cue in normalize_vietnamese(parameter) for cue in ("du bao", "hien tai", "thiet ke", "nam ", "tuan")
                ) else None
                facts.append(TableFact(
                    entity=entity,
                    parameter=parameter,
                    raw_value=raw_value,
                    numeric_value=numeric_value,
                    unit=unit_name,
                    condition=condition,
                    document_id=str(unit.get("doc_id") or unit.get("document_id") or ""),
                    page_number=int(unit.get("page_number") or 0),
                    region_id=str(unit.get("evidence_id") or unit.get("region_id") or table_id),
                    table_id=table_id,
                    row_id=f"R{row_index:03d}",
                    column_id=f"C{column_index:03d}",
                    page_id=str(unit.get("page_id") or ""),
                    source_sha256=str(unit.get("source_sha256") or ""),
                    header_text=lines[0],
                    row_text=line,
                    original_raw_text=raw_source,
                ))
        return facts

    def _score(self, fact: TableFact, intent: QueryIntent, question: str, page_rank: int) -> float:
        nq = normalize_vietnamese(question)
        entity = normalize_vietnamese(fact.entity)
        parameter = normalize_vietnamese(fact.parameter)
        score = 1.0 / max(1, page_rank)
        if entity and entity in nq:
            score += 12.0
        elif intent.entity and normalize_vietnamese(intent.entity) in entity:
            score += 9.0
        # Reward all explicitly requested entities for multi-entity table questions.
        entity_tokens = [t for t in entity.split() if len(t) > 2]
        if entity_tokens and all(t in nq for t in entity_tokens):
            score += 5.0
        parameter_cues = [intent.parameter, *intent.aliases] if intent.parameter else []
        if any(normalize_vietnamese(cue) in parameter for cue in parameter_cues if cue):
            score += 10.0
        # A full source header quoted in the question is stronger than a broad
        # ontology alias such as "lượng mưa" or "diện tích".
        if parameter and parameter in nq:
            score += 8.0
        q_tokens = {t for t in nq.split() if len(t) > 2}
        score += min(6.0, 0.8 * len(q_tokens.intersection(parameter.split())))
        if fact.unit and any(normalize_vietnamese(fact.unit) == normalize_vietnamese(u) for u in intent.expected_units):
            score += 2.0
        if intent.temporal_scope and normalize_vietnamese(intent.temporal_scope) in normalize_vietnamese(fact.header_text):
            score += 2.0
        return score

    def resolve(
        self,
        question: str,
        ranked_pages: Iterable[dict[str, Any]],
        max_facts: int = 3,
        min_score: float = 6.0,
    ) -> list[dict[str, Any]]:
        intent = self.query_guide.understand(question)
        if not intent.numeric_or_table:
            return []
        candidates: list[tuple[float, int, TableFact]] = []
        for page_rank, page in enumerate(list(ranked_pages)[:5], 1):
            for fact in self.facts_by_page.get(str(page.get("page_id")), []):
                score = self._score(fact, intent, question, page_rank)
                if score >= min_score:
                    candidates.append((score, page_rank, fact))
        candidates.sort(key=lambda item: (-item[0], item[1], item[2].evidence_id))

        selected: list[dict[str, Any]] = []
        seen_cells: set[str] = set()
        for score, page_rank, fact in candidates:
            if fact.evidence_id in seen_cells:
                continue
            selected.append(fact.to_evidence_dict(score, page_rank))
            seen_cells.add(fact.evidence_id)
            if len(selected) >= max_facts:
                break
        return selected

    def build_table_window(self, unit: dict[str, Any], question: str, max_rows: int = 4) -> str:
        table_id = str(unit.get("evidence_id") or unit.get("region_id") or "")
        intent = self.query_guide.understand(question)
        facts = self.facts_by_table.get(table_id, [])
        if not facts:
            return str(unit.get("index_text") or unit.get("raw_text") or "")
        scored = sorted(
            ((self._score(fact, intent, question, 1), fact) for fact in facts),
            key=lambda item: (-item[0], item[1].evidence_id),
        )
        rows: list[str] = []
        for _, fact in scored:
            if fact.row_text not in rows:
                rows.append(fact.row_text)
            if len(rows) >= max_rows:
                break
        return f"[TIÊU ĐỀ BẢNG] {facts[0].header_text}\n" + "\n".join(f"[HÀNG] {row}" for row in rows)

    def stats(self) -> dict[str, int]:
        return {"tables": len(self.facts_by_table), "facts": len(self.facts), "pages": len(self.facts_by_page)}
