"""Required V4.2 mutations. Test 13 is fully self-contained."""
from __future__ import annotations
import copy
import json
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent; PARENT=HERE.parent
sys.path.insert(0,str(PARENT))
from QA_VALIDATOR_V4_2 import Registry, near_duplicates, validate, validate_fixture_assertion


def main() -> int:
    base=[json.loads(x) for x in (PARENT/"V4_2_QA_DRAFTS.jsonl").read_text(encoding="utf-8").splitlines() if x]
    reg=Registry(PARENT); cases=[]
    def add(name, idx, mutate, expected):
        r=copy.deepcopy(base[idx]); mutate(r); cases.append((name,r,expected))
    add("01_shallow_question",0,lambda r:r.update(question="Tài liệu nói gì về hệ thống?"),"SHALLOW_QUESTION")
    add("02_unknown_evidence",0,lambda r:r.update(evidence_ids=["EV999"]),"UNKNOWN_EVIDENCE")
    add("03_unknown_set",0,lambda r:r.update(evidence_set_id="ES999"),"UNKNOWN_EVIDENCE_SET")
    add("04_blocked_set",0,lambda r:r.update(evidence_set_id="ES010"),"INELIGIBLE_EVIDENCE_SET")
    add("05_evidence_outside_set",0,lambda r:r.update(evidence_ids=["EV013"]),"EVIDENCE_OUTSIDE_SET")
    add("06_duplicate_evidence",0,lambda r:r.update(evidence_ids=["EV001","EV001"]),"DUPLICATE_EVIDENCE_ID")
    add("07_component_unknown_evidence",0,lambda r:r["answer_components"][0].update(supported_by=["EV999"]),"COMPONENT_UNKNOWN_EVIDENCE")
    add("08_wrong_arithmetic",2,lambda r:r["operations"][0].update(result=1),"ARITHMETIC_MISMATCH")
    add("09_fake_comparison",0,lambda r:r.update(competency="QUANTITATIVE_COMPARISON"),"FAKE_COMPARISON")
    add("10_fake_multi_evidence",0,lambda r:r.update(evidence_pattern="CROSS_DOCUMENT"),"FAKE_MULTI_EVIDENCE")
    add("11_non_ground_up",0,lambda r:r.update(origin_type="LEGACY"),"ORIGIN_NOT_GROUND_UP")
    add("12_wrong_generation_order",0,lambda r:r["lineage"].update(generation_order=["QA_DRAFT","EVIDENCE_SET"]),"WRONG_GENERATION_ORDER")
    add("15_invalid_human_acceptance",0,lambda r:r["review"].update(status="HUMAN_ACCEPTED"),"INVALID_HUMAN_ACCEPTANCE")
    add("16_candidate_leakage",0,lambda r:r["lineage"].update(candidate_test_accessed=True),"CANDIDATE_LEAKAGE")
    results=[]
    for name,r,expected in cases:
        got=validate(r,reg,False); codes=[x["code"] for x in got["issues"]]
        results.append({"name":name,"kind":"MUTATION","expected_code":expected,"observed_codes":codes,
                        "caught":expected in codes,"non_default":bool(codes)})
    fixture=json.loads((HERE/"fixtures"/"SOURCE_FIXTURE_FACT_VALUE.json").read_text(encoding="utf-8"))
    codes=[x["code"] for x in validate_fixture_assertion(fixture,99999)]
    results.append({"name":"13_locator_right_fact_wrong","kind":"SOURCE_FIXTURE_MUTATION","expected_code":"FACT_VALUE_NOT_FOUND",
                    "forbidden_code":"SOURCE_UNREADABLE","observed_codes":codes,
                    "caught":"FACT_VALUE_NOT_FOUND" in codes and "SOURCE_UNREADABLE" not in codes,"non_default":bool(codes)})
    dup=copy.deepcopy(base[0]); dup["qa_id"]="V42-QA-999"; dup["question"]=base[0]["question"]+"?"
    codes=[x["code"] for x in near_duplicates([base[0],dup])]
    results.append({"name":"14_paraphrase_duplicate","kind":"MUTATION","expected_code":"NEAR_DUPLICATE","observed_codes":codes,
                    "caught":"NEAR_DUPLICATE" in codes,"non_default":bool(codes)})
    results.sort(key=lambda x:x["name"])
    summary={"total":len(results),"caught":sum(x["caught"] for x in results),"non_default":sum(x["non_default"] for x in results),
             "all_pass":all(x["caught"] and x["non_default"] for x in results),
             "test13_source_unreadable_absent":next(x for x in results if x["name"].startswith("13"))["caught"],"results":results}
    (HERE/"TEST_RESULTS.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:summary[k] for k in ("total","caught","non_default","all_pass","test13_source_unreadable_absent")}))
    return 0 if summary["all_pass"] else 1


if __name__=="__main__": raise SystemExit(main())
