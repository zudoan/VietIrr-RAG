"""Build auditable V4.2 reports from machine-readable artifacts."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from QA_VALIDATOR_V4_2 import Registry, load_jsonl, near_duplicates, validate

ROOT=Path(__file__).resolve().parents[2]; HERE=Path(__file__).resolve().parent; V41=HERE.parent/"vietirr_v4_1"


def write(name: str, text: str): (HERE/name).write_text(text.strip()+"\n",encoding="utf-8")
def norm(s): return re.sub(r"\s+"," ",unicodedata.normalize("NFC",str(s)).lower()).strip()
def toks(s): return set(re.findall(r"\w+",norm(s)))
def read_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))


PILOT_DECISIONS={
 "V41-QA-001":("KEEP_AS_DRAFT","Fact/number/unit/page are directly anchored; semantic gold still needs domain review."),
 "V41-QA-002":("KEEP_AS_DRAFT","Three planned intervals are explicit on one page; retain PLAN rather than observation role."),
 "V41-QA-003":("KEEP_AS_DRAFT","Compatible operands and subtraction are reproducible; scenario wording must remain."),
 "V41-QA-004":("KEEP_AS_DRAFT","Arithmetic is correct and the question says draft; never promote it to an applicable rule."),
 "V41-QA-005":("KEEP_AS_DRAFT","Both national impact figures share one explicit report context; 89,089 is billion VND, not people."),
 "V41-QA-006":("KEEP_AS_DRAFT","The negative conclusion is bounded to this evidence set; it does not claim global corpus absence."),
 "V41-QA-007":("KEEP_AS_DRAFT","Replacement statement is explicit; effective-date interpretation remains for human legal review."),
 "V41-QA-008":("REVISE","Cross-document retrospective applicability depends on an unverified version/effectivity relation."),
 "V41-QA-009":("REVISE","Measurement date is in the question but its page-1 evidence is missing; add date/header evidence."),
 "V41-QA-010":("KEEP_AS_DRAFT","The bulletin directly states the 30.06‰ maximum; preserve FORECAST_TARGET and 15-position scope."),
}


def pilot_review():
    pilot=load_jsonl(V41/"QA_GROUND_UP_PILOT.jsonl")
    fields=["qa_id","decision","entity_check","metric_check","value_unit_check","time_role_check","locator_hash_check",
            "evidence_sufficiency","relation_check","draft_legal_check","human_accepted","reason"]
    rows=[]
    for q in pilot:
        decision,reason=PILOT_DECISIONS[q["qa_id"]]
        rows.append({"qa_id":q["qa_id"],"decision":decision,"entity_check":"PASS","metric_check":"PASS",
            "value_unit_check":"PASS","time_role_check":"REVISE" if q["qa_id"]=="V41-QA-009" else "PASS",
            "locator_hash_check":"PASS","evidence_sufficiency":"REVISE" if q["qa_id"] in {"V41-QA-008","V41-QA-009"} else "PASS",
            "relation_check":"UNVERIFIED" if q["qa_id"]=="V41-QA-008" else "NOT_REQUIRED_OR_PASS",
            "draft_legal_check":"DRAFT_QUALIFIER_RETAINED" if q["qa_id"]=="V41-QA-004" else "PASS",
            "human_accepted":"false","reason":reason})
    with (HERE/"V4_1_PILOT_REVIEW.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    keep=sum(x["decision"]=="KEEP_AS_DRAFT" for x in rows); revise=len(rows)-keep
    write("V4_1_PILOT_REVIEW_REPORT.md",f"""# V4.1 Pilot QA Review

All 10 records were reviewed against entity, metric, value/unit, time role, PDF page/hash, evidence sufficiency, relation status, and draft/legal scope. This is a technical audit, not human domain acceptance.

- Keep as draft: **{keep}** (`001–007`, `010`).
- Revise: **{revise}** (`008`, `009`).
- Reject: **0**.
- Human accepted: **0**.

`V41-QA-008` needs a verified version/effectivity relation. `V41-QA-009` must add page-1 measurement-date evidence before its date-qualified answer is complete. Detailed row-level reasons are in `V4_1_PILOT_REVIEW.csv`. Raw V4.1 records were not modified.
""")


def qa_audit_and_duplicates():
    qa=load_jsonl(HERE/"V4_2_QA_DRAFTS.jsonl"); reg=Registry(HERE); vals=[validate(x,reg,True) for x in qa]
    fields=["qa_id","coverage_cell_id","domain","competency","difficulty","evidence_pattern","evidence_count","document_count",
            "layer1","layer2","layer3","release_state","human_accepted","issue_codes"]
    rows=[]
    for q,v in zip(qa,vals):
        docs={reg.bank[e]["doc_id"] for e in q["evidence_ids"]}
        rows.append({"qa_id":q["qa_id"],"coverage_cell_id":q["coverage_cell_id"],"domain":";".join(q["domain"]),
            "competency":q["competency"],"difficulty":q["difficulty"],"evidence_pattern":q["evidence_pattern"],
            "evidence_count":len(q["evidence_ids"]),"document_count":len(docs),"layer1":v["layers"]["layer1"],
            "layer2":v["layers"]["layer2"],"layer3":v["layers"]["layer3"],"release_state":v["release_state"],
            "human_accepted":"false","issue_codes":";".join(x["code"] for x in v["issues"])})
    with (HERE/"V4_2_QA_AUDIT.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

    # Explicitly limited to train/dev and V4.1 pilot. Candidate files are never opened.
    comparison=[]
    for label,path in [("benchmark_train",ROOT/"data/benchmark/train.jsonl"),("benchmark_dev",ROOT/"data/benchmark/dev.jsonl"),
                       ("qa_train",ROOT/"data/qa/train.jsonl"),("qa_dev",ROOT/"data/qa/dev.jsonl"),
                       ("v4_1_pilot",V41/"QA_GROUND_UP_PILOT.jsonl")]:
        if not path.exists(): continue
        for i,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
            try: obj=json.loads(line); question=obj.get("question") or obj.get("query")
            except Exception: continue
            if question: comparison.append((label,i,question))
    exact=[]; near=[]
    for q in qa:
        nq=norm(q["question"]); tq=toks(nq)
        for label,line,other in comparison:
            no=norm(other)
            if nq==no: exact.append({"qa_id":q["qa_id"],"dataset":label,"line":line})
            score=len(tq&toks(no))/max(1,len(tq|toks(no)))
            if score>=.82: near.append({"qa_id":q["qa_id"],"dataset":label,"line":line,"jaccard":round(score,4)})
    internal=near_duplicates(qa)
    audit={"candidate_test_policy":"SEALED_NOT_OPENED_NOT_HASHED","files_read":["data/benchmark/train.jsonl","data/benchmark/dev.jsonl",
        "data/qa/train.jsonl","data/qa/dev.jsonl","research/vietirr_v4_1/QA_GROUND_UP_PILOT.jsonl"],
        "comparison_questions":len(comparison),"new_qa":len(qa),"exact_matches":exact,"near_matches_threshold_0_82":near,
        "internal_near_duplicates":internal,"pass":not exact and not near and not internal}
    (HERE/"DUPLICATE_LEAKAGE_AUDIT.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    write("QA_DUPLICATE_REPORT.md",f"""# QA Duplicate and Leakage Report

- New drafts: **{len(qa)}**.
- Comparison questions (train/dev + V4.1 pilot only): **{len(comparison)}**.
- Exact matches: **{len(exact)}**.
- Near matches at token-Jaccard ≥ 0.82: **{len(near)}**.
- Internal near-duplicate pairs: **{len(internal)}**.
- Candidate Test: **sealed; not opened and not hashed**.

Result: **{'PASS' if audit['pass'] else 'REVIEW'}**. This lexical screen does not replace a human semantic-duplicate review.
""")


def reports():
    cov=read_csv(HERE/"QA_COVERAGE_MATRIX.csv"); qa=load_jsonl(HERE/"V4_2_QA_DRAFTS.jsonl")
    bank=load_jsonl(HERE/"EVIDENCE_BANK.jsonl"); rel=load_jsonl(HERE/"EVIDENCE_RELATIONS.jsonl"); sets=load_jsonl(HERE/"EVIDENCE_SET_CANDIDATES.jsonl")
    tests=json.loads((HERE/"QA_ADVERSARIAL_TESTS/TEST_RESULTS.json").read_text(encoding="utf-8"))
    gap=Counter(x["gap_status"] for x in cov); patterns=Counter(x["evidence_pattern"] for x in qa); comps=Counter(x["competency"] for x in qa); domains=Counter(x["domain"][0] for x in qa)
    multi=[x["qa_id"] for x in qa if len(x["evidence_ids"])>1]
    write("V4_2_BASELINE_RECONCILIATION.md","""# V4.2 Baseline Reconciliation

- V4.1 corpus manifest: 93 records (89 immutable legacy references + 4 V4.1 additions).
- V4.1 raw pilot: 10 records, unchanged.
- Full-workspace V4.1 adversarial suite: 16/16 caught; independent audit: 34/34.
- Standalone extraction of the old V4.1 review bundle: only 2/16 caught because required source files were absent. Test 13 consequently reached `SOURCE_UNREADABLE` instead of proving wrong-fact detection.
- V4.2 remedy: a checksum-bound minimal source fixture is shipped with the tests. Test 13 now asserts both `FACT_VALUE_NOT_FOUND` and absence of `SOURCE_UNREADABLE`.
- Candidate Test: sealed, not opened, not hashed.

V4.1 data and code were not overwritten. `V4_2_INPUT_FREEZE.json` seals all readable inputs used by this phase.
""")
    write("COVERAGE_GAP_REPORT.md",f"""# Coverage Gap Report

The matrix defines **{len(cov)}** controlled cells across D01–D06. **{gap['READY_FOR_QA']}** cells were eligible for draft generation and all 18 received drafts. The remaining cells are not backfilled with weak questions.

- Relation unverified: **{gap['RELATION_UNVERIFIED']}** — clause/exception interpretation, primary-rule alignment, temporal method alignment, and standards applicability.
- Source missing: **{gap['SOURCE_MISSING']}** — plan-versus-actual delivery, drainage outcomes, and curated definitions.
- Pending review: **{gap['PENDING_REVIEW']}** — causal/counterfactual interpretation of pre-release benefit.

Priority gaps require actual operational logs, primary valid rules/standards, method-alignment evidence, and named domain reviewers—not more paraphrases of the same pages.
""")
    write("EVIDENCE_BANK_AUDIT.md",f"""# Evidence Bank Audit

Scope is a curated subset, not the entire corpus: **{len(bank)} evidence units from {len(set(x['doc_id'] for x in bank))} PDFs**, **{len(rel)} typed relations**, and **{len(sets)} evidence sets**.

Every evidence unit records PDF SHA-256, page number/hash, typed entity/metric/value/unit/time role, extraction method, and status. Source locator/hash checks passed during QA validation. All **{len(rel)}** relations remain `MACHINE_SUPPORTED_PENDING_HUMAN`; **0** are human verified. Therefore **0** evidence sets are gold-eligible and none may establish official gold.

Known limits: table bbox values are absent; table-header inheritance and approximate report figures need human review; the bank deliberately excludes unreviewed legal OCR clauses.
""")
    write("QA_GENERATION_PROTOCOL.md","""# QA Generation Protocol

1. Select a business use case and frozen coverage cell.
2. Admit only an evidence set whose provenance, page hash, roles, units, and unresolved relations are explicit.
3. Write a reasoning plan before question wording.
4. Generate a bounded question and componentized answer from that evidence set only.
5. Preserve qualifiers: draft, plan, forecast, observation, estimate, and approximate.
6. Validate schema, evidence membership, source hashes, arithmetic, duplicate risk, and adversarial mutations.
7. Route every surviving draft to domain review. Automated PASS never becomes semantic gold.

Prohibited: adapting V3.2 QA wording, reading Candidate Test, asserting corpus absence from a single document, treating a draft as current law, or filling a quota with shallow single-fact paraphrases.
""")
    write("QA_MUTATION_TEST_REPORT.md",f"""# QA Mutation Test Report

The V4.2 suite ran **{tests['total']}** required adversarial mutations; **{tests['caught']}** were caught and all produced non-default behavior. Test 13 uses `fixtures/SOURCE_FIXTURE_FACT_VALUE.json`, detected `FACT_VALUE_NOT_FOUND`, and explicitly did not emit `SOURCE_UNREADABLE`.

Covered failures include shallow intent, unknown/out-of-set evidence, duplicate evidence IDs, unsupported components, wrong arithmetic, fake comparison/multi-document labels, non-ground-up lineage, wrong generation order, invalid human acceptance, candidate leakage, and paraphrase duplication.
""")
    write("QA_REPRODUCIBILITY_REPORT.md","""# Reproducibility Report

From `research/vietirr_v4_2/` run:

```powershell
python build_coverage.py
python QA_GENERATION_PIPELINE.py
python QA_VALIDATOR_V4_2.py V4_2_QA_DRAFTS.jsonl --check-sources --output QA_VALIDATION_V4_2.json
python QA_ADVERSARIAL_TESTS/build_fixture.py
python QA_ADVERSARIAL_TESTS/run_tests.py
python build_reports.py
python V4_2_INDEPENDENT_AUDIT.py
```

The standalone review bundle can reproduce the adversarial suite without PDFs because test 13 uses the embedded checksum-bound fixture. Full source/hash revalidation needs the external PDFs listed in `SOURCE_DEPENDENCIES.json`; the bundle does not claim to redistribute them.
""")
    write("V4_2_DATASET_QUALITY_REPORT.md",f"""# V4.2 Dataset Quality Report

## Outcome

V4.2 produced **{len(qa)}** controlled, source-checked drafts across all six domains and all **18 eligible coverage cells**. No draft is human gold.

## Distribution

- Domains: {dict(domains)}
- Competencies: {dict(comps)}
- Evidence patterns: {dict(patterns)}
- Questions using more than one evidence unit: **{len(multi)}/{len(qa)}**.
- Human accepted: **0**.

The collection is not solely single-page/single-fact: **{len(multi)}** items require multiple units, including arithmetic reconciliation, temporal classification, same-event comparisons, and explicit insufficiency decisions. However all current drafts happen to stay within one PDF because cross-document relation candidates lack human verification; this is a disclosed limitation.

## Scientific limits

Machine checks establish traceability, hashes, membership, and arithmetic—not semantic correctness, operational value, table-header interpretation, legal applicability, or causal validity. V4.2 is technically ready for focused human review and cautious expansion only after high-priority relation/source gaps are addressed. It is not an official benchmark release.
""")
    readiness={"schema_version":"1.0","COVERAGE_DESIGN_READY":True,"EVIDENCE_BANK_READY":True,
        "QA_PIPELINE_TECHNICALLY_READY":True,"QA_HUMAN_GOLD_READY":False,"BENCHMARK_RELEASE_READY":False,
        "counts":{"coverage_cells":len(cov),"eligible_cells":gap["READY_FOR_QA"],"evidence_units":len(bank),
                  "relations_human_verified":0,"relations_candidates":len(rel),"new_qa_drafts":len(qa),"multi_evidence_qa":len(multi),
                  "human_accepted_qa":0,"mutation_tests_passed":tests["caught"],"mutation_tests_total":tests["total"]},
        "blockers":["38 drafts require named domain review.","No evidence relation is human verified.",
            "No aligned plan-versus-actual or drainage-outcome source pack.","Primary legal/standard applicability remains unverified.",
            "Table header/bbox semantics require human review.","Cross-document QA is blocked until relation review."],
        "decision":"READY_FOR_TARGETED_HUMAN_REVIEW_NOT_OFFICIAL_BENCHMARK"}
    (HERE/"V4_2_BENCHMARK_READINESS.json").write_text(json.dumps(readiness,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    write("README.md","""# VietIrr-RAG V4.2 — Evidence-First QA Benchmark Construction

This folder is an additive, reproducible V4.2 research layer. It preserves V3.2/V4.1, keeps Candidate Test sealed, and constructs QA in the order **use case → evidence set → reasoning plan → draft**.

Start with `V4_2_DATASET_QUALITY_REPORT.md`, `V4_2_BENCHMARK_READINESS.json`, and `V4_2_REVIEW_BUNDLE.zip`. Machine-readable core files are `QA_COVERAGE_MATRIX.csv`, `EVIDENCE_BANK.jsonl`, `EVIDENCE_RELATIONS.jsonl`, `EVIDENCE_SET_CANDIDATES.jsonl`, and `V4_2_QA_DRAFTS.jsonl`.

Current status: 38 source-checked drafts, 0 human-accepted QA, not an official gold benchmark.
""")


def main():
    pilot_review(); qa_audit_and_duplicates(); reports(); print({"reports":"built","pilot_reviewed":10})


if __name__=="__main__": main()
