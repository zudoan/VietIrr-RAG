"""Bounded, source-validated Qwen judge interface for EDR experiments."""
from __future__ import annotations
import json
from typing import Any

VALID = {"DIRECT_SUPPORT", "PARTIAL_SUPPORT", "TOPICAL_ONLY", "ATTRIBUTE_MISMATCH", "INSUFFICIENT_EVIDENCE", "UNKNOWN"}
_SCORE = {"DIRECT_SUPPORT": 4, "PARTIAL_SUPPORT": 3, "TOPICAL_ONLY": 2, "ATTRIBUTE_MISMATCH": 1, "INSUFFICIENT_EVIDENCE": 0, "UNKNOWN": 0}

def judge_prompt(question: str, packets: list[dict[str, Any]]) -> str:
    evidence = "\n\n".join(f"ID={p['evidence_id']}\n{p['content']}" for p in packets)
    return ("You are an evidence judge. Use only supplied source text. Do not answer the question or invent values. "
            "Return strict JSON only: {\"status\": one of DIRECT_SUPPORT,PARTIAL_SUPPORT,TOPICAL_ONLY,ATTRIBUTE_MISMATCH,INSUFFICIENT_EVIDENCE,UNKNOWN, "
            "\"evidence_ids\": [existing IDs], \"reason\": short}. ATTRIBUTE_MISMATCH applies to wrong entity, parameter, period, unit, or condition. "
            f"Question: {question}\nEvidence:\n{evidence}")

def parse_verdict(raw: str, packets: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Reject malformed/model-invented verdicts; callers retain BGE on None."""
    try: row = json.loads(raw)
    except (TypeError, json.JSONDecodeError): return None
    allowed = {str(p["evidence_id"]) for p in packets}
    ids = row.get("evidence_ids")
    if row.get("status") not in VALID or not isinstance(ids, list) or any(str(i) not in allowed for i in ids): return None
    return {"status":row["status"],"evidence_ids":[str(i) for i in ids],"reason":str(row.get("reason") or ""),"edr_score":_SCORE[row["status"]]}

def constrained_rerank(pages: list[dict[str, Any]], verdicts: dict[str, dict[str, Any] | None]) -> list[dict[str, Any]]:
    """Stable stage-2 ordering: answerability band first, original BGE rank tie-break."""
    def key(page: dict[str, Any]) -> tuple[int, int]:
        v = verdicts.get(str(page["page_id"])); return (-(v or {"edr_score":-1})["edr_score"], int(page["bge_rank"]))
    result=sorted((dict(p) for p in pages),key=key)
    for rank,p in enumerate(result,1):
        p["edr_rank"]=rank; p["edr_verdict"]=verdicts.get(str(p["page_id"]))
    return result
