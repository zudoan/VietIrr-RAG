from __future__ import annotations

import json
from viirr_rag.pipeline import (
    Evidence,
    _EvidenceScope,
    _relation_fact_verdict,
    build_context,
    enforce_citation_grounding,
    parse_generation,
)


def test_table_cell_relation_fact_verdict_supported():
    cell_text = (
        "[Ô BẢNG NGUỒN] Thực thể: Tri Tôn; Thông số: Mực nước lớn nhất dự báo (m) — 05/10; "
        "Giá trị: 1,94 m; điều kiện/cột: Mực nước lớn nhất dự báo (m) — 05/10."
    )
    scope = _EvidenceScope(text=cell_text, evidence_ids=("ev_tri_ton_1",), kind="table_cell")
    claim = "Mực nước lớn nhất dự báo ngày 05/10/2026 của Tri Tôn là 1,94 m."
    verdict = _relation_fact_verdict(claim, [scope])
    assert verdict is not None
    assert verdict["status"] == "SUPPORTED"
    assert verdict["evidence_ids"] == ["ev_tri_ton_1"]


def test_table_cell_relation_fact_verdict_contradicted_value():
    cell_text = (
        "[Ô BẢNG NGUỒN] Thực thể: Tri Tôn; Thông số: Mực nước lớn nhất dự báo (m) — 05/10; "
        "Giá trị: 1,94 m; điều kiện/cột: Mực nước lớn nhất dự báo (m) — 05/10."
    )
    scope = _EvidenceScope(text=cell_text, evidence_ids=("ev_tri_ton_1",), kind="table_cell")
    claim = "Mực nước lớn nhất dự báo ngày 05/10/2026 của Tri Tôn là 2,50 m."
    verdict = _relation_fact_verdict(claim, [scope])
    assert verdict is not None
    assert verdict["status"] == "CONTRADICTED"
    assert verdict["evidence_ids"] == ["ev_tri_ton_1"]


def test_table_cell_grounding_guard_integration():
    cell_item = Evidence(
        rank=1,
        evidence_id="IRR_DOC_1_P1_R1_C1",
        doc_id="IRR_DOC_1",
        page_id="IRR_DOC_1_P1",
        page_number=1,
        unit_type="TABLE_CELL",
        score=1.0,
        text=(
            "[Ô BẢNG NGUỒN] Thực thể: Vĩnh Điều; Thông số: Mực nước lớn nhất dự báo (m) — 05/10; "
            "Giá trị: 2,15 m; điều kiện/cột: Mực nước lớn nhất dự báo (m) — 05/10."
        ),
        source="table",
    )
    context = build_context([cell_item])
    raw_answer = "Mực nước lớn nhất dự báo ngày 05/10/2026 của Vĩnh Điều là 2,15 m."
    gen = parse_generation(
        json.dumps(
            {
                "answer": raw_answer,
                "citations": [
                    {
                        "doc_id": cell_item.doc_id,
                        "page_number": cell_item.page_number,
                        "evidence_id": cell_item.evidence_id,
                    }
                ],
                "abstained": False,
                "abstention_reason": "",
                "evidence_supported": True,
            },
            ensure_ascii=False,
        )
    )
    guarded_gen, audit = enforce_citation_grounding(gen, context)
    assert not guarded_gen.abstained
    assert guarded_gen.answer == raw_answer
    assert len(guarded_gen.citations) == 1
    assert guarded_gen.citations[0]["evidence_id"] == "IRR_DOC_1_P1_R1_C1"
    assert audit["support_status"] == "SUPPORTED"
