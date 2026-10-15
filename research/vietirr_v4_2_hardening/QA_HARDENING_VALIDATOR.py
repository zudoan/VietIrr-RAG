"""Independent checks for evidence repair, labels and alternative sets."""
from __future__ import annotations
import json
from pathlib import Path
import math
from typing import Any

HERE=Path(__file__).resolve().parent;V42=HERE.parent/"vietirr_v4_2"
def load_jsonl(p:Path):return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x]
def registry():return {x["evidence_id"]:x for x in load_jsonl(V42/"EVIDENCE_BANK.jsonl")}

def validate_repaired(q:dict,bank:dict[str,dict]|None=None)->list[str]:
    bank=bank or registry();codes=[];ids=q.get("evidence_ids",[]);required=q.get("required_evidence_ids",[])
    if not ids:codes.append("NO_EVIDENCE")
    if not set(required).issubset(ids):codes.append("GOLD_MISSING_REQUIRED_FACT")
    if set(ids)-set(required):codes.append("REDUNDANT_REQUIRED_EVIDENCE")
    if any(e not in bank for e in ids):codes.append("UNKNOWN_EVIDENCE")
    expected={x["evidence_id"]:x for x in q.get("required_fact_signatures",[])}
    for eid,sig in expected.items():
        if eid not in bank:continue
        e=bank[eid]
        if e["entity"]!=sig["entity"]:codes.append("WRONG_ENTITY")
        if e["unit"]!=sig["unit"]:codes.append("WRONG_UNIT")
        if e["time_role"]!=sig["time_role"] or e["time_value"]!=sig["time_value"]:codes.append("WRONG_TIMESTAMP")
        if not e.get("pdf_sha256") or not e.get("page_sha256"):codes.append("PROVENANCE_MISSING")
    docs={bank[e]["doc_id"] for e in ids if e in bank}
    comp=q.get("competency")
    if comp=="CROSS_DOCUMENT_SYNTHESIS" and len(docs)<2:codes.append("FAKE_CROSS_DOCUMENT_LABEL")
    if comp=="SINGLE_DOCUMENT_SYNTHESIS" and len(docs)!=1:codes.append("BAD_SINGLE_DOCUMENT_LABEL")
    if comp=="SINGLE_DOCUMENT_SYNTHESIS" and len(ids)<2:codes.append("FAKE_SYNTHESIS_LABEL")
    if comp=="QUANTITATIVE_COMPARISON" and len(ids)<2:codes.append("FAKE_COMPARISON_LABEL")
    if comp=="VERIFIABLE_COMPUTATION" and not q.get("operations"):codes.append("MISSING_COMPUTATION_TRACE")
    for op in q.get("operations",[]):
        vals=op.get("inputs",[]);expected=None
        if op.get("operation")=="ADD":expected=sum(vals)
        elif op.get("operation")=="SUBTRACT" and len(vals)==2:expected=vals[0]-vals[1]
        if expected is not None and not math.isclose(float(expected),float(op.get("result")),abs_tol=1e-8):codes.append("ARITHMETIC_MISMATCH")
    if q.get("multi_hop") and (len(ids)<2 or not q.get("required_relations")):codes.append("FAKE_MULTI_HOP_LABEL")
    if q.get("review",{}).get("status")=="HUMAN_ACCEPTED" and not q.get("review",{}).get("reviewer_id"):codes.append("FALSE_HUMAN_ACCEPTANCE")
    return sorted(set(codes))

def validate_alternative(q:dict,alternative:list[str],bank:dict[str,dict]|None=None)->str:
    bank=bank or registry()
    if not alternative or any(x not in bank for x in alternative):return "ALTERNATIVE_INSUFFICIENT"
    # Exact replacement of all required facts.
    required=q.get("required_evidence_ids",[])
    if set(required).issubset(alternative):return "ALTERNATIVE_CANDIDATE_VALID"
    # Deterministic additive alternative for a single numeric canonical fact.
    if len(required)==1 and required[0] in bank:
        target=bank[required[0]];parts=[bank[x] for x in alternative]
        if all(isinstance(x["value"],(int,float)) for x in parts) and isinstance(target["value"],(int,float)):
            if all(x["entity"]==target["entity"] and x["unit"]==target["unit"] and x["time_value"]==target["time_value"] for x in parts):
                if sum(float(x["value"]) for x in parts)==float(target["value"]):return "ALTERNATIVE_CANDIDATE_VALID"
    return "ALTERNATIVE_INSUFFICIENT"

def pair_semantics(a:dict,b:dict)->str:
    fa=set(a.get("required_evidence_ids",a.get("evidence_ids",[])));fb=set(b.get("required_evidence_ids",b.get("evidence_ids",[])))
    if fa==fb and a.get("competency")==b.get("competency"):return "SAME_FACT_SAME_COMPETENCY"
    if fa==fb:return "SAME_FACT_DIFFERENT_COMPETENCY"
    return "DISTINCT_USE_CASE"
