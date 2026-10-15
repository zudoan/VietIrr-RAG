"""Fail-closed independent audit for V4.2 quality hardening."""
from __future__ import annotations
import csv,hashlib,json,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;V42=HERE.parent/"vietirr_v4_2"
checks=[]
def check(name,ok,detail=""):checks.append({"check":name,"pass":bool(ok),"detail":detail})
def jl(p):return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x]
def cr(p):
    with p.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

required=["V4_2_HARDENING_EXECUTIVE_REPORT.md","QA_38_FULL_AUDIT.csv","QA_EVIDENCE_REPAIR.jsonl","QA_MINIMALITY_AUDIT.csv",
 "ALTERNATIVE_GOLD_SETS.jsonl","EVIDENCE_CHANGELOG.md","QA_LABEL_AUDIT.csv","QA_COMPETENCY_MAPPING.json","QA_LABEL_CHANGELOG.md",
 "QA_SEMANTIC_CLUSTERS.json","QA_DIVERSITY_REPORT.md","QA_KEEP_REVISE_REJECT.csv","QA_GENERATOR_V3.py","QA_GENERATION_SCHEMA.json",
 "QA_GENERATOR_TESTS/run_tests.py","QA_GENERALIZATION_DEMO.jsonl","QA_GENERATOR_CAPABILITY_REPORT.md","QA_HUMAN_REVIEW_SHEET.csv",
 "QA_VALIDATION_REPORT.md","V4_2_HARDENING_READINESS.json","HARDENING_INPUT_FREEZE.json"]
for x in required:check(f"required:{x}",(HERE/x).is_file())

freeze=json.loads((HERE/"HARDENING_INPUT_FREEZE.json").read_text(encoding="utf-8"));bad=[]
for row in freeze["readable_inputs"]:
    p=ROOT/row["path"]
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row["sha256"]:bad.append(row["path"])
check("frozen_files_unchanged",not bad,str(bad));check("candidate_sealed",freeze["candidate_test"]["policy"]=="SEALED_NOT_OPENED_NOT_HASHED")
check("candidate_not_hashed",freeze["candidate_test"]["sha256"]=="INTENTIONALLY_NOT_COMPUTED")

audit=cr(HERE/"QA_38_FULL_AUDIT.csv");check("all_38_audited",len(audit)==38 and len({x["qa_id"] for x in audit})==38)
check("all_have_decision_reason",all(x["status"] in {"KEEP","REVISE","REJECT","BLOCKED_SOURCE","PENDING_HUMAN_REVIEW"} and x["recommended_action"] for x in audit))
counts={k:sum(x["status"]==k for x in audit) for k in ("KEEP","REVISE","REJECT")};check("decision_counts",counts=={"KEEP":22,"REVISE":11,"REJECT":5},str(counts))
qa={x["qa_id"]:x for x in jl(HERE/"QA_EVIDENCE_REPAIR.jsonl")};check("repair_has_38",len(qa)==38)
check("qa036_minimal",qa["V42-QA-036"]["evidence_ids"]==["EV033","EV034"])
check("qa036_arithmetic",qa["V42-QA-036"]["operations"][0]["result"]==2500)
check("qa021_label_fixed",qa["V42-QA-021"]["competency"]=="SINGLE_DOCUMENT_SYNTHESIS")
check("qa032_label_fixed",qa["V42-QA-032"]["competency"]=="SINGLE_DOCUMENT_SYNTHESIS")
check("qa026_domain_evidence",qa["V42-QA-026"]["evidence_ids"]==["EV053","EV057","EV058"])
check("no_cross_document_claims",not any(x["competency"]=="CROSS_DOCUMENT_SYNTHESIS" for x in qa.values()))
check("no_false_human_gold",not any(x.get("human_semantic_status")!="PENDING" or x["review"]["status"]=="HUMAN_ACCEPTED" for x in qa.values()))
mins=cr(HERE/"QA_MINIMALITY_AUDIT.csv");check("minimality_all_accounted",len(mins)==38 and not any(x["minimality_status"]=="FAIL" for x in mins))
clusters=json.loads((HERE/"QA_SEMANTIC_CLUSTERS.json").read_text(encoding="utf-8"));check("clusters_classified",len(clusters["clusters"])==12)
check("cluster_mandatory_ranges",any(c["qa_ids"]==["V42-QA-001","V42-QA-002","V42-QA-003","V42-QA-004"] for c in clusters["clusters"]) and any(c["qa_ids"]==["V42-QA-034","V42-QA-035","V42-QA-036"] for c in clusters["clusters"]))
check("valid_single_fact_not_all_rejected",any(x["competency"]=="SINGLE_FACT_LOOKUP" and x["hardening_decision"]=="KEEP" for x in qa.values()))

gen=(HERE/"QA_GENERATOR_V3.py").read_text(encoding="utf-8");check("generator_not_hardcoded_qa_list","Q = [" not in gen and "V42-QA-" not in gen)
demos=jl(HERE/"QA_GENERALIZATION_DEMO.jsonl");raw_ids={e for q in jl(V42/"V4_2_QA_DRAFTS.jsonl") for e in q["evidence_ids"]};demo_ids={e["evidence_id"] for d in demos for e in d["evidence_set"]}
check("two_demo_drafts",len(demos)==2 and all(x["generation_state"]=="DRAFT_CREATED" for x in demos))
check("demo_uses_unseen_evidence",demo_ids.isdisjoint(raw_ids),str(sorted(demo_ids)))
check("demo_checksums",all(x.get("input_sha256") and x.get("output_sha256") for x in demos))
tests=json.loads((HERE/"QA_GENERATOR_TESTS/TEST_RESULTS.json").read_text(encoding="utf-8"));check("hardening_tests",tests["all_pass"] and tests["passed"]==24)
check("positive_and_negative_tests",tests["positive_cases"]>=5 and tests["negative_cases"]>=16)
sheet=cr(HERE/"QA_HUMAN_REVIEW_SHEET.csv");check("human_sheet_38",len(sheet)==38)
check("review_fields_pending",all(x["reviewer_verdict"]=="PENDING" and not x["reviewer_notes"] and not x["review_timestamp"] for x in sheet))
readiness=json.loads((HERE/"V4_2_HARDENING_READINESS.json").read_text(encoding="utf-8"));check("readiness_separated",all(k in readiness for k in ("TECHNICAL_CORRECTNESS","SEMANTIC_CORRECTNESS","BENCHMARK_QUALITY","SCIENTIFIC_INTEGRITY")))
check("release_not_overclaimed",not readiness["QA_HUMAN_GOLD_READY"] and not readiness["BENCHMARK_RELEASE_READY"])

z=HERE/"V4_2_HARDENING_REVIEW_BUNDLE.zip"
if z.is_file():
    with zipfile.ZipFile(z) as f:
        names=set(f.namelist());bm=json.loads(f.read("HARDENING_BUNDLE_MANIFEST.json"));badzip=[]
        for name,digest in bm["files"].items():
            if name not in names or hashlib.sha256(f.read(name)).hexdigest()!=digest:badzip.append(name)
        check("bundle_checksums",not badzip,str(badzip));check("bundle_no_candidate",not any("candidate_test" in x.lower() or "candidate_gold" in x.lower() for x in names))
        check("bundle_test_dependencies",all(x in names for x in ["research/vietirr_v4_2/EVIDENCE_BANK.jsonl","research/vietirr_v4_2/QA_COVERAGE_MATRIX.csv","research/vietirr_v4_2_hardening/QA_GENERATOR_TESTS/run_tests.py"]))
else:
    mp=HERE/"HARDENING_BUNDLE_MANIFEST.json"
    if not mp.is_file():mp=ROOT/"HARDENING_BUNDLE_MANIFEST.json"
    if mp.is_file():
        bm=json.loads(mp.read_text(encoding="utf-8"));badfiles=[]
        for name,digest in bm["files"].items():
            p=ROOT/name
            if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:badfiles.append(name)
        names=set(bm["files"])
        check("bundle_checksums",not badfiles,str(badfiles));check("bundle_no_candidate",not any("candidate_test" in x.lower() or "candidate_gold" in x.lower() for x in names))
        check("bundle_test_dependencies",all(x in names for x in ["research/vietirr_v4_2/EVIDENCE_BANK.jsonl","research/vietirr_v4_2/QA_COVERAGE_MATRIX.csv","research/vietirr_v4_2_hardening/QA_GENERATOR_TESTS/run_tests.py"]))
    else:check("bundle_exists_or_extracted_manifest",False)

result={"total":len(checks),"passed":sum(x["pass"] for x in checks),"failed":sum(not x["pass"] for x in checks),"all_pass":all(x["pass"] for x in checks),"checks":checks}
(HERE/"V4_2_HARDENING_INDEPENDENT_AUDIT.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({k:result[k] for k in ("total","passed","failed","all_pass")}));raise SystemExit(0 if result["all_pass"] else 1)
