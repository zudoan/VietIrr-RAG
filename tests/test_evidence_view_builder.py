from viirr_retrieval.evidence_view_builder import build_evidence_views


def test_query_selects_matching_parameter_and_keeps_provenance():
    units = [
        {"evidence_id": "P0", "raw_text": "Hồ A dung tích thiết kế 30 triệu m3"},
        {"evidence_id": "P1", "raw_text": "Hồ B mực nước hiện tại 12 m"},
    ]
    view = build_evidence_views(page={"page_id": "d_1", "doc_id": "d"}, units=units,
                                unit_indices=[0, 1], query="Dung tích thiết kế Hồ A là bao nhiêu?",
                                header="Doc d page 1")[0]
    assert view["evidence_ids"] == ["P0", "P1"]
    assert view["provenance_status"] == "EXTRACTED"
    assert view["content_hash"]


def test_table_view_retains_renderer_header_and_row():
    unit = {"evidence_id": "TAB_1", "unit_type": "TABLE_REGION", "raw_text": "bad"}
    view = build_evidence_views(page={"page_id": "d_2", "doc_id": "d"}, units=[unit], unit_indices=[0],
                                query="Hồ A dung tích", header="Doc", table_renderer=lambda _: "Header | dung tích\nHồ A | 12") [0]
    assert "Header | dung tích" in view["content"]
    assert view["evidence_ids"] == ["TAB_1"]
