"""Independent, fail-closed audit of V4.2 deliverables."""
from __future__ import annotations
import csv
import hashlib
import json
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]; HERE=Path(__file__).resolve().parent
checks=[]
def check(name,ok,detail=""): checks.append({"check":name,"pass":bool(ok),"detail":detail})
def jsonl(name): return [json.loads(x) for x in (HERE/name).read_text(encoding="utf-8").splitlines() if x]
def csvrows(name):
    with (HERE/name).open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

required=["DOMAIN_USE_CASE_COVERAGE.csv","QA_COVERAGE_MATRIX.csv","COVERAGE_GAP_REPORT.md","EVIDENCE_BANK.jsonl",
 "EVIDENCE_RELATIONS.jsonl","EVIDENCE_SET_CANDIDATES.jsonl","EVIDENCE_BANK_AUDIT.md","V4_1_PILOT_REVIEW.csv",
 "V4_1_PILOT_REVIEW_REPORT.md","QA_GENERATION_PROTOCOL.md","QA_GENERATION_PIPELINE.py","V4_2_QA_DRAFTS.jsonl",
 "V4_2_QA_AUDIT.csv","QA_DUPLICATE_REPORT.md","QA_VALIDATOR_PATCH.py","QA_ADVERSARIAL_TESTS/TEST_RESULTS.json",
 "QA_MUTATION_TEST_REPORT.md","QA_REPRODUCIBILITY_REPORT.md","V4_2_DATASET_QUALITY_REPORT.md","V4_2_BENCHMARK_READINESS.json"]
for x in required: check(f"required:{x}",(HERE/x).exists())

freeze=json.loads((HERE/"V4_2_INPUT_FREEZE.json").read_text(encoding="utf-8")); bad=[]
for item in freeze["readable_inputs"]:
    p=ROOT/item["path"]
    if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=item["sha256"]: bad.append(item["path"])
check("v4_1_and_frozen_inputs_unchanged",not bad,str(bad))
check("candidate_policy_sealed",freeze["candidate_test"]["policy"]=="SEALED_NOT_OPENED_NOT_HASHED")
check("candidate_has_no_hash",freeze["candidate_test"].get("sha256") == "INTENTIONALLY_NOT_COMPUTED")

cov=csvrows("QA_COVERAGE_MATRIX.csv"); check("coverage_26_cells",len(cov)==26); check("eligible_cells_18",sum(x["gap_status"]=="READY_FOR_QA" for x in cov)==18)
check("coverage_gaps_disclosed",all(x["gap_status"] in {"READY_FOR_QA","RELATION_UNVERIFIED","SOURCE_MISSING","PENDING_REVIEW"} for x in cov))
bank=jsonl("EVIDENCE_BANK.jsonl"); rel=jsonl("EVIDENCE_RELATIONS.jsonl"); sets=jsonl("EVIDENCE_SET_CANDIDATES.jsonl")
check("evidence_units_59",len(bank)==59); check("evidence_eight_documents",len({x["doc_id"] for x in bank})==8)
check("evidence_provenance_complete",all(x.get("pdf_sha256") and x.get("page_sha256") and x.get("page") for x in bank))
check("relations_21",len(rel)==21); check("no_fake_verified_relations",all(x["verification_status"]!="VERIFIED" for x in rel))
check("no_gold_eligible_sets",not any(x["gold_eligible"] for x in sets))

pilot=csvrows("V4_1_PILOT_REVIEW.csv"); check("pilot_all_10_reviewed",len(pilot)==10 and len({x["qa_id"] for x in pilot})==10)
check("pilot_decisions_honest",sum(x["decision"]=="KEEP_AS_DRAFT" for x in pilot)==8 and sum(x["decision"]=="REVISE" for x in pilot)==2)
qa=jsonl("V4_2_QA_DRAFTS.jsonl"); qa_audit=csvrows("V4_2_QA_AUDIT.csv")
check("new_drafts_38",len(qa)==38); check("ground_up_lineage",all(x["origin_type"]=="GROUND_UP" and x["lineage"]["legacy_qa_used"] is False for x in qa))
check("generation_order",all(x["lineage"]["generation_order"]==["USE_CASE","EVIDENCE_SET","REASONING_PLAN","QA_DRAFT"] for x in qa))
check("all_eligible_cells_filled",len({x["coverage_cell_id"] for x in qa})==18)
check("no_human_gold",all(x["review"]["status"]!="HUMAN_ACCEPTED" for x in qa) and all(x["human_accepted"]=="false" for x in qa_audit))
check("validator_l1_l2_pass",all(x["layer1"]=="PASS" and x["layer2"]=="PASS" for x in qa_audit))
check("human_layer_review",all(x["layer3"]=="REVIEW" for x in qa_audit))
dup=json.loads((HERE/"DUPLICATE_LEAKAGE_AUDIT.json").read_text(encoding="utf-8")); check("duplicate_audit_pass",dup["pass"])
check("duplicate_audit_excludes_candidate",dup["candidate_test_policy"]=="SEALED_NOT_OPENED_NOT_HASHED" and not any("candidate" in x.lower() for x in dup["files_read"]))
tests=json.loads((HERE/"QA_ADVERSARIAL_TESTS/TEST_RESULTS.json").read_text(encoding="utf-8")); check("mutations_16_of_16",tests["all_pass"] and tests["caught"]==16)
check("test13_reproduced",tests["test13_source_unreadable_absent"])
readiness=json.loads((HERE/"V4_2_BENCHMARK_READINESS.json").read_text(encoding="utf-8")); check("readiness_not_overclaimed",readiness["QA_PIPELINE_TECHNICALLY_READY"] and not readiness["QA_HUMAN_GOLD_READY"] and not readiness["BENCHMARK_RELEASE_READY"])

zpath=HERE/"V4_2_REVIEW_BUNDLE.zip"
if zpath.exists():
    with zipfile.ZipFile(zpath) as z:
        names=set(z.namelist()); bm=json.loads(z.read("V4_2_BUNDLE_MANIFEST.json")); badzip=[]
        for name,sha in bm["files"].items():
            if name not in names or hashlib.sha256(z.read(name)).hexdigest()!=sha: badzip.append(name)
        check("bundle_checksums",not badzip,str(badzip)); check("bundle_has_source_fixture","QA_ADVERSARIAL_TESTS/fixtures/SOURCE_FIXTURE_FACT_VALUE.json" in names)
        check("bundle_excludes_candidate",not any("candidate_test" in x.lower() or "candidate_gold" in x.lower() for x in names))
        check("bundle_excludes_pdfs",not any(x.lower().endswith(".pdf") for x in names))
else: check("bundle_exists",False)

result={"total":len(checks),"passed":sum(x["pass"] for x in checks),"failed":sum(not x["pass"] for x in checks),
        "all_pass":all(x["pass"] for x in checks),"checks":checks}
(HERE/"V4_2_INDEPENDENT_AUDIT.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({k:result[k] for k in ("total","passed","failed","all_pass")}))
raise SystemExit(0 if result["all_pass"] else 1)
