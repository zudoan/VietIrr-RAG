from viirr_retrieval.edr_packets import UNKNOWN, build_evidence_packets, serialize_packets

def test_packet_preserves_anchor_utf8_and_provenance():
    text = "Hồ A | Dung tích hiện tại | năm 2025 | 12,3 triệu m³"
    u = {"evidence_id":"TAB_1","unit_type":"TABLE_REGION","raw_text":text,"doc_id":"D","source_sha256":"abc"}
    p = build_evidence_packets(page={"page_id":"P","doc_id":"D","page_number":1},units=[u],unit_indices=[0],query="Dung tích Hồ A năm 2025")[0]
    assert p["content"] == text and p["evidence_id"] == "TAB_1" and p["entity"] == UNKNOWN

def test_packets_are_deterministic_and_not_gold_aware():
    units = [{"evidence_id":"A","raw_text":"mực nước Hồ A"},{"evidence_id":"B","raw_text":"dung tích Hồ B"}]
    args = dict(page={"page_id":"P"},units=units,unit_indices=[0,1],query="dung tích Hồ B")
    assert build_evidence_packets(**args) == build_evidence_packets(**args)
    assert "EVIDENCE B" in serialize_packets(build_evidence_packets(**args))
