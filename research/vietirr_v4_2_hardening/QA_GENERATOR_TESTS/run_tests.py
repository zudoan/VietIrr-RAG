from __future__ import annotations
import copy,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;PARENT=HERE.parent
sys.path.insert(0,str(PARENT))
from QA_GENERATOR_V3 import generate,load_bank,load_coverage
from QA_HARDENING_VALIDATOR import pair_semantics,registry,validate_alternative,validate_repaired

def main()->int:
    repaired=[json.loads(x) for x in (PARENT/"QA_EVIDENCE_REPAIR.jsonl").read_text(encoding="utf-8").splitlines() if x]
    byid={x["qa_id"]:x for x in repaired};bank=registry();bank_list=list(bank.values());coverage=load_coverage();results=[]
    def add(name,expected,observed,positive=False):results.append({"name":name,"expected":expected,"observed":observed,"positive":positive,"pass":expected in observed})
    # 1 redundant evidence
    raw36=copy.deepcopy(byid["V42-QA-036"]);raw36["evidence_ids"] += ["EV035"]
    add("01_redundant_evidence","REDUNDANT_REQUIRED_EVIDENCE",validate_repaired(raw36,bank))
    # 2 missing required fact
    x=copy.deepcopy(byid["V42-QA-036"]);x["evidence_ids"]=["EV033"]
    add("02_gold_missing_required_fact","GOLD_MISSING_REQUIRED_FACT",validate_repaired(x,bank))
    # 3 wrong entity
    bad=copy.deepcopy(bank);bad["EV033"]=copy.deepcopy(bad["EV033"]);bad["EV033"]["entity"]="Hồ khác"
    add("03_wrong_entity","WRONG_ENTITY",validate_repaired(byid["V42-QA-036"],bad))
    # 4 wrong timestamp
    bad=copy.deepcopy(bank);bad["EV033"]=copy.deepcopy(bad["EV033"]);bad["EV033"]["time_value"]="2099"
    add("04_wrong_timestamp","WRONG_TIMESTAMP",validate_repaired(byid["V42-QA-036"],bad))
    # 5/6 alternative evidence
    add("05_valid_alternative_candidate","ALTERNATIVE_CANDIDATE_VALID",[validate_alternative(byid["V42-QA-001"],["EV002","EV003"],bank)],True)
    add("06_invalid_alternative","ALTERNATIVE_INSUFFICIENT",[validate_alternative(byid["V42-QA-001"],["EV002"],bank)])
    # 7 extrema without domain coverage
    req={"request_id":"T07","coverage_cell_id":"C018","competency":"MULTI_FACT_LOOKUP","selectors":[{"entity_regex":"^15 vị trí dự báo$","metric_regex":"độ mặn dự báo"}],"operation":"MULTI_LOOKUP","constraints":{"min_evidence":2,"max_evidence":3,"require_same_unit":True,"require_same_time":True,"aggregation_domain_count":15,"source_direct_aggregation":False}}
    add("07_extrema_incomplete_domain","INCOMPLETE_AGGREGATION_DOMAIN",[generate(req,bank_list,coverage).get("issue_code")])
    # 8 fake cross-document label
    x=copy.deepcopy(byid["V42-QA-021"]);x["competency"]="CROSS_DOCUMENT_SYNTHESIS"
    add("08_fake_cross_document","FAKE_CROSS_DOCUMENT_LABEL",validate_repaired(x,bank))
    # 9 fake multi-hop
    x=copy.deepcopy(byid["V42-QA-001"]);x["multi_hop"]=True
    add("09_fake_multi_hop","FAKE_MULTI_HOP_LABEL",validate_repaired(x,bank))
    # 10 duplicate same facts/competency
    clone=copy.deepcopy(byid["V42-QA-001"]);clone["question"]="Paraphrase"
    add("10_duplicate_same_facts","SAME_FACT_SAME_COMPETENCY",[pair_semantics(byid["V42-QA-001"],clone)])
    # 11 same facts but genuinely different competency
    a=copy.deepcopy(byid["V42-QA-013"]);b=copy.deepcopy(a);b["competency"]="VERIFIABLE_COMPUTATION"
    add("11_same_facts_different_competency","SAME_FACT_DIFFERENT_COMPETENCY",[pair_semantics(a,b)],True)
    # 12 generator selects evidence never used by raw hardcoded drafts
    reqs=[json.loads(x) for x in (HERE/"demo_requests.jsonl").read_text(encoding="utf-8").splitlines() if x];out=generate(reqs[0],bank_list,coverage)
    raw_ids={e for q in [json.loads(x) for x in (PARENT.parent/"vietirr_v4_2/V4_2_QA_DRAFTS.jsonl").read_text(encoding="utf-8").splitlines()] for e in q["evidence_ids"]}
    unseen=all(e["evidence_id"] not in raw_ids for e in out.get("evidence_set",[]))
    add("12_generator_unseen_evidence","DRAFT_CREATED_UNSEEN",["DRAFT_CREATED_UNSEEN" if out.get("generation_state")=="DRAFT_CREATED" and unseen else "FAIL"],True)
    # 13 no source
    req=copy.deepcopy(reqs[1]);req["request_id"]="T13";req["selectors"]=[{"entity_regex":"DOES_NOT_EXIST"}]
    add("13_generator_missing_source","NO_ELIGIBLE_EVIDENCE",[generate(req,bank_list,coverage).get("issue_code")])
    # 14 unit mismatch
    badlist=copy.deepcopy(bank_list);next(e for e in badlist if e["evidence_id"]=="EV022")["unit"]="cm"
    req=copy.deepcopy(reqs[0]);req["request_id"]="T14";req["constraints"]["require_same_unit"]=True
    add("14_generator_wrong_unit","UNIT_MISMATCH",[generate(req,badlist,coverage).get("issue_code")])
    # 15 temporal alignment
    req=copy.deepcopy(reqs[0]);req["request_id"]="T15";req["constraints"]["require_same_time"]=True
    add("15_generator_temporal_misalignment","TEMPORAL_MISALIGNMENT",[generate(req,bank_list,coverage).get("issue_code")])
    # 16 provenance missing
    badlist=copy.deepcopy(bank_list);next(e for e in badlist if e["evidence_id"]=="EV042")["pdf_sha256"]=""
    add("16_qa_without_provenance","PROVENANCE_MISSING",[generate(reqs[1],badlist,coverage).get("issue_code")])
    # E4 extra negatives: relation, conflict, unsupported cell/competency.
    req={"request_id":"T17","coverage_cell_id":"C001","competency":"MULTI_FACT_LOOKUP","selectors":[{"entity_regex":"Hệ thống Bắc Nam Hà","metric_regex":"diện tích tự nhiên"},{"entity_regex":"Hệ thống Cái Lớn","metric_regex":"diện tích tự nhiên"}],"operation":"MULTI_LOOKUP","constraints":{"min_evidence":2,"max_evidence":2,"require_same_unit":True,"require_same_time":False}}
    add("17_unverified_cross_document_relation","UNVERIFIED_CROSS_DOCUMENT_RELATION",[generate(req,bank_list,coverage).get("issue_code")])
    conflict=copy.deepcopy(bank_list);dup=copy.deepcopy(next(e for e in conflict if e["evidence_id"]=="EV042"));dup["evidence_id"]="EVX42";dup["value"]=999;conflict.append(dup)
    req=copy.deepcopy(reqs[1]);req["request_id"]="T18";req["constraints"]["max_evidence"]=2
    add("18_conflicting_values","CONFLICTING_VALUES",[generate(req,conflict,coverage).get("issue_code")])
    req=copy.deepcopy(reqs[1]);req["request_id"]="T19";req["coverage_cell_id"]="C999"
    add("19_unsupported_coverage","UNSUPPORTED_COVERAGE_CELL",[generate(req,bank_list,coverage).get("issue_code")])
    req=copy.deepcopy(reqs[1]);req["request_id"]="T20";req["competency"]="MAGIC_REASONING"
    add("20_unsupported_competency","UNSUPPORTED_COMPETENCY",[generate(req,bank_list,coverage).get("issue_code")])
    add("21_positive_minimal_repair","NO_ISSUES",validate_repaired(byid["V42-QA-036"],bank) or ["NO_ISSUES"],True)
    out=generate(reqs[1],bank_list,coverage)
    add("22_positive_single_fact_generation","DRAFT_CREATED",[out.get("generation_state")],True)
    add("23_positive_exact_alternative","ALTERNATIVE_CANDIDATE_VALID",[validate_alternative(byid["V42-QA-036"],["EV033","EV034"],bank)],True)
    add("24_positive_distinct_use_case","DISTINCT_USE_CASE",[pair_semantics(byid["V42-QA-001"],byid["V42-QA-009"])],True)
    summary={"total":len(results),"passed":sum(x["pass"] for x in results),"positive_cases":sum(x["positive"] for x in results),
             "negative_cases":sum(not x["positive"] for x in results),"all_pass":all(x["pass"] for x in results),"results":results}
    (HERE/"TEST_RESULTS.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:summary[k] for k in ("total","passed","positive_cases","negative_cases","all_pass")}))
    return 0 if summary["all_pass"] else 1
if __name__=="__main__":raise SystemExit(main())
