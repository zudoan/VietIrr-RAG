from __future__ import annotations

import json
from decimal import Decimal
import pytest
from viirr_rag.pipeline import (
    Evidence,
    _EvidenceScope,
    _FactRelation,
    _NumericMention,
    _relation_fact_verdict,
    _temporal_relation,
    _temporal_verdict,
    build_context,
    enforce_citation_grounding,
    parse_generation,
)


def _cell_evidence(
    ev_id: str,
    entity: str,
    param: str,
    val_str: str,
    time_str: str | None = None,
    doc_id: str = "DOC_01",
    page: int = 1,
) -> Evidence:
    t_part = f"Thời gian: {time_str}; " if time_str else ""
    text = (
        f"[Ô BẢNG NGUỒN] Thực thể: {entity}; Thông số: {param}; {t_part}Giá trị: {val_str}; "
        f"điều kiện/cột: {param}."
    )
    return Evidence(
        rank=1,
        evidence_id=ev_id,
        doc_id=doc_id,
        page_id=f"PAGE_{doc_id}_{page:04d}",
        page_number=page,
        unit_type="TABLE_CELL",
        score=1.0,
        text=text,
        source="synthetic_test",
    )


def test_matrix_same_date_same_value():
    # Case 1: Same date, same value, same entity, same param -> SUPPORTED
    ev = _cell_evidence("ev1", "An Long", "Mực nước lớn nhất thực đo (m) — 02/10", "2,94 m")
    scope = _EvidenceScope(text=ev.text, evidence_ids=(ev.evidence_id,), kind="table_cell")
    claim = "Mực nước lớn nhất thực đo ngày 02/10/2026 của An Long là 2,94 m."
    verdict = _relation_fact_verdict(claim, [scope])
    assert verdict is not None
    assert verdict["status"] == "SUPPORTED"
    assert verdict["evidence_ids"] == ["ev1"]


def test_matrix_different_date_different_value_is_insufficient():
    # Case 2: Evidence is for 02/10 (2.02 m). Claim asks for 03/10 (2.00 m).
    # Different dates with different values must NOT be CONTRADICTED; they are INSUFFICIENT.
    ev = _cell_evidence("ev1", "Tri Tôn", "Mực nước lớn nhất thực đo (m) — 02/10", "2,02 m")
    scope = _EvidenceScope(text=ev.text, evidence_ids=(ev.evidence_id,), kind="table_cell")
    claim = "Mực nước lớn nhất thực đo ngày 03/10/2026 của Tri Tôn là 2,00 m."
    verdict = _relation_fact_verdict(claim, [scope])
    assert verdict is not None
    assert verdict["status"] == "INSUFFICIENT"
    assert verdict["reason"] == "FACT_RELATION_NOT_ESTABLISHED"


def test_matrix_same_date_conflicting_value_is_contradicted():
    # Case 3: Same date (02/10), but claim asserts 3.50 m while evidence asserts 2.94 m -> CONTRADICTED
    ev = _cell_evidence("ev1", "An Long", "Mực nước lớn nhất thực đo (m) — 02/10", "2,94 m")
    scope = _EvidenceScope(text=ev.text, evidence_ids=(ev.evidence_id,), kind="table_cell")
    claim = "Mực nước lớn nhất thực đo ngày 02/10/2026 của An Long là 3,50 m."
    verdict = _relation_fact_verdict(claim, [scope])
    assert verdict is not None
    assert verdict["status"] == "CONTRADICTED"
    assert "ev1" in verdict["evidence_ids"]


def test_matrix_different_date_same_value_is_insufficient():
    # Case 4: Evidence asserts 4.93 mg/L in 2024. Claim states 4.93 mg/L in 2025.
    # Evidence for 2024 does not prove or disprove 2025. Must evaluate to INSUFFICIENT, not CONTRADICTED.
    ev = _cell_evidence("ev1", "BHH10", "DO", "4,93 mg/l", time_str="2024")
    scope = _EvidenceScope(text=ev.text, evidence_ids=(ev.evidence_id,), kind="table_cell")
    claim = "Năm 2025, DO tại trạm BHH10 là 4,93 mg/l."
    verdict = _relation_fact_verdict(claim, [scope])
    assert verdict is not None
    assert verdict["status"] == "INSUFFICIENT"
    assert verdict["reason"] == "FACT_RELATION_NOT_ESTABLISHED"


def test_matrix_same_value_different_entity_is_insufficient():
    # Case 5: 2.94 m belonging to An Long does NOT support or contradict Tân Hồng
    ev = _cell_evidence("ev1", "An Long", "Mực nước lớn nhất thực đo (m) — 02/10", "2,94 m")
    scope = _EvidenceScope(text=ev.text, evidence_ids=(ev.evidence_id,), kind="table_cell")
    claim = "Mực nước lớn nhất thực đo ngày 02/10/2026 của Tân Hồng là 2,94 m."
    verdict = _relation_fact_verdict(claim, [scope])
    assert verdict is not None
    assert verdict["status"] == "INSUFFICIENT"


def test_matrix_negative_elevation_normalization():
    # Case 6: Negative number (-3 m) in table cell matching claim
    ev = _cell_evidence("ev1", "Trà Vinh", "Cao trình đáy (m)", "-3 m")
    scope = _EvidenceScope(text=ev.text, evidence_ids=(ev.evidence_id,), kind="table_cell")
    claim = "Cao trình đáy của Trà Vinh là -3 m."
    verdict = _relation_fact_verdict(claim, [scope])
    assert verdict is not None
    assert verdict["status"] == "SUPPORTED"
    assert verdict["evidence_ids"] == ["ev1"]


def test_matrix_decimal_comma_normalization():
    # Case 7: 2,73 m in evidence matches 2.73 m in claim
    ev = _cell_evidence("ev1", "An Long", "Mực nước lớn nhất dự báo (m) — 04/10", "2,73 m")
    scope = _EvidenceScope(text=ev.text, evidence_ids=(ev.evidence_id,), kind="table_cell")
    claim = "Mực nước lớn nhất dự báo ngày 04/10/2026 của An Long là 2.73 m."
    verdict = _relation_fact_verdict(claim, [scope])
    assert verdict is not None
    assert verdict["status"] == "SUPPORTED"


def test_matrix_unit_mismatch_is_contradicted():
    # Case 8: 4.93 m vs 4.93 cm -> CONTRADICTED
    ev = _cell_evidence("ev1", "BHH10", "Mực nước", "4,93 m")
    scope = _EvidenceScope(text=ev.text, evidence_ids=(ev.evidence_id,), kind="table_cell")
    claim = "Mực nước tại trạm BHH10 là 4,93 cm."
    verdict = _relation_fact_verdict(claim, [scope])
    assert verdict is not None
    assert verdict["status"] == "CONTRADICTED"
