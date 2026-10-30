import json
from viirr_retrieval.edr_discriminator import constrained_rerank, parse_verdict

def test_rejects_invented_evidence_id_and_malformed_json():
    p=[{"evidence_id":"E1","content":"source"}]
    assert parse_verdict("not json",p) is None
    assert parse_verdict(json.dumps({"status":"DIRECT_SUPPORT","evidence_ids":["fake"]}),p) is None

def test_stable_bge_tiebreak_and_distinct_pages():
    rows=[{"page_id":"a","bge_rank":2},{"page_id":"b","bge_rank":1}]
    out=constrained_rerank(rows,{"a":{"edr_score":4},"b":{"edr_score":4}})
    assert [x["page_id"] for x in out]==["b","a"]
