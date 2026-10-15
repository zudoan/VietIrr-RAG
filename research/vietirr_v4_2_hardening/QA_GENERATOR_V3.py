"""Generalizable evidence-first QA generator.

The code contains competency-level linguistic structures only. It never stores
a concrete question, answer, value, or evidence ID. Facts are selected at run
time from the evidence bank using a generation request.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, re
from pathlib import Path
from typing import Any

HERE=Path(__file__).resolve().parent; V42=HERE.parent/"vietirr_v4_2"
SUPPORTED={"SINGLE_FACT_LOOKUP","MULTI_FACT_LOOKUP","QUANTITATIVE_COMPARISON","VERIFIABLE_COMPUTATION"}

def load_jsonl(path:Path):return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
def load_bank(path:Path|None=None):return load_jsonl(path or V42/"EVIDENCE_BANK.jsonl")
def load_coverage(path:Path|None=None):
    with (path or V42/"QA_COVERAGE_MATRIX.csv").open(encoding="utf-8-sig",newline="") as f:return {x["coverage_cell_id"]:x for x in csv.DictReader(f)}
def sha(obj:Any):return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def select(bank:list[dict],selectors:list[dict])->list[dict]:
    out={}
    for s in selectors:
        for e in bank:
            if s.get("doc_id") and e["doc_id"]!=s["doc_id"]:continue
            if s.get("entity_regex") and not re.search(s["entity_regex"],e["entity"],re.I):continue
            if s.get("metric_regex") and not re.search(s["metric_regex"],e["metric"],re.I):continue
            if s.get("time_role") and e["time_role"]!=s["time_role"]:continue
            if "unit" in s and e["unit"]!=s["unit"]:continue
            out[e["evidence_id"]]=e
    return [out[k] for k in sorted(out)]

def block(req,code,message,state="BLOCKED"):
    return {"request_id":req.get("request_id"),"generation_state":state,"issue_code":code,"message":message,
            "question":None,"proposed_answer":None,"required_facts":[],"reasoning_trace":[],"evidence_set":[],
            "validation_state":state,"human_review_status":"PENDING"}

def generate(req:dict,bank:list[dict]|None=None,coverage:dict|None=None)->dict:
    bank=bank or load_bank();coverage=coverage or load_coverage();cell=coverage.get(req.get("coverage_cell_id"))
    if not cell:return block(req,"UNSUPPORTED_COVERAGE_CELL","Coverage cell does not exist")
    if cell["gap_status"]!="READY_FOR_QA":return block(req,"COVERAGE_NOT_ELIGIBLE",cell["gap_status"])
    if req.get("competency") not in SUPPORTED:return block(req,"UNSUPPORTED_COMPETENCY",str(req.get("competency")))
    evidence=select(bank,req.get("selectors",[])); c=req.get("constraints",{}); lo=c.get("min_evidence",1);hi=c.get("max_evidence",999)
    if not evidence:return block(req,"NO_ELIGIBLE_EVIDENCE","No evidence matches selectors")
    if not lo<=len(evidence)<=hi:return block(req,"OPERAND_COUNT",f"selected={len(evidence)}, expected={lo}..{hi}")
    if any(not e.get("pdf_sha256") or not e.get("page_sha256") for e in evidence):return block(req,"PROVENANCE_MISSING","Evidence lacks source checksum")
    units={e["unit"] for e in evidence};times={str(e["time_value"]) for e in evidence}
    if c.get("require_same_unit") and len(units)>1:return block(req,"UNIT_MISMATCH",str(sorted(map(str,units))))
    if c.get("require_same_time") and len(times)>1:return block(req,"TEMPORAL_MISALIGNMENT",str(sorted(times)))
    docs={e["doc_id"] for e in evidence}
    if len(docs)>1:return block(req,"UNVERIFIED_CROSS_DOCUMENT_RELATION","No human-verified relation supplied","REVIEW")
    keys={}
    for e in evidence:
        key=(e["entity"],e["metric"],str(e["time_value"]),e["unit"]);keys.setdefault(key,set()).add(str(e["value"]))
    if any(len(v)>1 for v in keys.values()):return block(req,"CONFLICTING_VALUES","Same typed fact has multiple values","REVIEW")
    domain_count=c.get("aggregation_domain_count")
    if domain_count and not c.get("source_direct_aggregation") and len(evidence)<domain_count:
        return block(req,"INCOMPLETE_AGGREGATION_DOMAIN",f"selected={len(evidence)} of domain={domain_count}","REVIEW")
    op=req["operation"]
    if op in {"ADD","SUBTRACT"}:
        if not all(isinstance(e["value"],(int,float)) for e in evidence):return block(req,"NON_NUMERIC_OPERAND","Arithmetic needs numeric facts")
        if op=="SUBTRACT" and len(evidence)!=2:return block(req,"OPERAND_COUNT","SUBTRACT requires exactly two operands")
        result=sum(float(e["value"]) for e in evidence) if op=="ADD" else float(evidence[0]["value"])-float(evidence[1]["value"])
        if math.isclose(result,round(result),abs_tol=1e-12):result=int(round(result))
        question=f"Theo {evidence[0]['publication_or_version']}, {op.lower()} các giá trị {', '.join(e['metric'] for e in evidence)} cho kết quả bao nhiêu?"
        answer=f"{result}{(' '+str(evidence[0]['unit'])) if evidence[0]['unit'] else ''}."
        trace=[{"operation":op,"inputs":[e["evidence_id"] for e in evidence],"result":result}]
    elif op=="COMPARE":
        if len(evidence)<2 or not all(isinstance(e["value"],(int,float)) for e in evidence):return block(req,"OPERAND_COUNT","COMPARE requires at least two numeric operands")
        winner=max(evidence,key=lambda x:x["value"])
        question=f"Trong các bằng chứng cùng đơn vị và kỳ, đối tượng nào có {winner['metric']} lớn nhất?"
        answer=f"{winner['entity']}: {winner['value']}{(' '+str(winner['unit'])) if winner['unit'] else ''}."
        trace=[{"operation":"ARGMAX","inputs":[e["evidence_id"] for e in evidence],"result":winner["evidence_id"]}]
    elif op=="MULTI_LOOKUP":
        entity=evidence[0]["entity"]
        if len(times)==1:
            question=f"Theo {evidence[0]['publication_or_version']}, các giá trị được nêu cho {entity} trong {evidence[0]['time_value']} là gì?"
        else:
            question=f"Theo {evidence[0]['publication_or_version']}, các giá trị theo từng thời điểm được nêu cho {entity} là gì?"
        answer="; ".join(f"{e['metric']} ({e['time_value']}): {e['value']}{(' '+str(e['unit'])) if e['unit'] else ''}" for e in evidence)+"."
        trace=[{"operation":"MULTI_LOOKUP","inputs":[e["evidence_id"] for e in evidence]}]
    else:
        if len(evidence)!=1:return block(req,"OPERAND_COUNT","LOOKUP requires exactly one evidence unit")
        e=evidence[0];question=f"Theo {e['publication_or_version']}, {e['metric']} của {e['entity']} trong {e['time_value']} là bao nhiêu?"
        answer=f"{e['value']}{(' '+str(e['unit'])) if e['unit'] else ''}.";trace=[{"operation":"LOOKUP","inputs":[e["evidence_id"]]}]
    facts=[{"evidence_id":e["evidence_id"],"entity":e["entity"],"metric":e["metric"],"value":e["value"],"unit":e["unit"],"time_role":e["time_role"],"time_value":e["time_value"]} for e in evidence]
    out={"request_id":req["request_id"],"coverage_cell_id":req["coverage_cell_id"],"competency":req["competency"],
         "generation_state":"DRAFT_CREATED","question":question,"proposed_answer":answer,"required_facts":facts,
         "reasoning_trace":trace,"evidence_set":[{"evidence_id":e["evidence_id"],"doc_id":e["doc_id"],"page":e["page"],"pdf_sha256":e["pdf_sha256"],"page_sha256":e["page_sha256"]} for e in evidence],
         "validation_state":"TECHNICAL_PASS_SEMANTIC_REVIEW_REQUIRED","human_review_status":"PENDING",
         "generation_method":"COVERAGE_TO_EVIDENCE_SELECTION_TO_TYPED_FACTS_TO_REASONING_TO_DRAFT",
         "input_sha256":sha(req)}
    out["output_sha256"]=sha(out);return out

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("request");ap.add_argument("--output");a=ap.parse_args();req=json.loads(Path(a.request).read_text(encoding="utf-8"));out=generate(req)
    text=json.dumps(out,ensure_ascii=False,indent=2)+"\n";print(text)
    if a.output:Path(a.output).write_text(text,encoding="utf-8")
