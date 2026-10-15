from __future__ import annotations
import csv,hashlib,json
from collections import Counter
from pathlib import Path
from QA_HARDENING_VALIDATOR import load_jsonl,registry,validate_repaired

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;V42=HERE.parent/"vietirr_v4_2";V41=HERE.parent/"vietirr_v4_1"
def rows(name):
    with (HERE/name).open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def write(name,text):(HERE/name).write_text(text.strip()+"\n",encoding="utf-8")

audit=rows("QA_38_FULL_AUDIT.csv");minimal=rows("QA_MINIMALITY_AUDIT.csv");labels=rows("QA_LABEL_AUDIT.csv")
repaired=load_jsonl(HERE/"QA_EVIDENCE_REPAIR.jsonl");tests=json.loads((HERE/"QA_GENERATOR_TESTS/TEST_RESULTS.json").read_text(encoding="utf-8"));demos=load_jsonl(HERE/"QA_GENERALIZATION_DEMO.jsonl")
dec=Counter(x["status"] for x in audit); validation=[{"qa_id":q["qa_id"],"codes":validate_repaired(q)} for q in repaired]
bad=[x for x in validation if x["codes"]]

demo_lines=[]
for d in demos:
    demo_lines.append(f"- `{d['request_id']}`: `{','.join(x['evidence_id'] for x in d['evidence_set'])}`; input `{d['input_sha256']}`; output `{d['output_sha256']}`.")
write("QA_GENERATOR_CAPABILITY_REPORT.md",f"""# QA Generator V3 Capability Report

## Demonstrated architecture

`Coverage Cell → Evidence Search/Selection → Typed Fact Validation → Reasoning Plan → QA Draft → Validation State → Human Review Queue`

The generator contains no concrete question, answer, numeric value or evidence ID. Its input requests contain coverage, selectors, competency, operation and constraints. It currently supports deterministic `SINGLE_FACT_LOOKUP`, `MULTI_FACT_LOOKUP`, `QUANTITATIVE_COMPARISON` and `VERIFIABLE_COMPUTATION`.

## Generalization demo

Two drafts were generated from evidence never used by the original hardcoded 38-QA list: EV021/EV022 and EV042. The second request was substituted without modifying generator code.

{chr(10).join(demo_lines)}

Generator tests: **{tests['passed']}/{tests['total']}**, including {tests['positive_cases']} positive and {tests['negative_cases']} negative cases. Missing operands, unit/time mismatch, unverified cross-document relations, no source, conflicts, incomplete extrema domain, unsupported cells/competencies, and missing provenance fail closed.

## Limits

This demonstrates a bounded deterministic generator, not a universal QA author. It does not automatically establish semantic correctness, legal applicability, cross-document relations, causal reasoning, or human gold. LLM wording is not required or used.
""")

write("QA_VALIDATION_REPORT.md",f"""# QA Validation Report

## Existing suites rerun

- V4.1 adversarial: **16/16**.
- V4.2 adversarial: **16/16**; test 13 has no `SOURCE_UNREADABLE`.
- V4.2 independent audit: **50/50**.

## Hardening suite

- New hardening/generator tests: **{tests['passed']}/{tests['total']}**.
- Positive cases: **{tests['positive_cases']}**; negative cases: **{tests['negative_cases']}**.
- Repaired records checked: **{len(repaired)}**; deterministic repair errors: **{len(bad)}**.
- Minimality: **{sum(x['minimality_status']=='PASS_STRUCTURAL_PENDING_SEMANTIC_HUMAN' for x in minimal)}** structural passes pending human, **{sum(x['minimality_status']=='NOT_APPLICABLE_REJECTED' for x in minimal)}** rejected records.

Technical PASS covers schema/IDs, provenance fields, evidence membership, label constraints, arithmetic and fail-closed behavior. It does not certify semantic sufficiency or gold status.
""")

write("V4_2_HARDENING_EXECUTIVE_REPORT.md",f"""# VietIrr-RAG V4.2 Quality Hardening — Executive Report

## Outcome

All 38 V4.2 drafts were audited without modifying the frozen raw file. Decisions: **KEEP {dec['KEEP']}**, **REVISE {dec['REVISE']}**, **REJECT {dec['REJECT']}**. Human verified remains **0**.

## Mandatory repairs

- QA-021 and QA-032: false `CROSS_SOURCE_SYNTHESIS` labels replaced by `SINGLE_DOCUMENT_SYNTHESIS`. QA-028 received the same correction.
- QA-026: EV053 added to establish the 15-position domain; direct extrema evidence EV057/EV058 retained. It remains pending human table/source review.
- QA-036: storage EV035–EV038 removed; required evidence is only EV033/EV034. Arithmetic remains approximately `4,000 − 1,500 = 2,500 m³/s`.
- Additional minimality repairs: QA-004, QA-019, QA-025, QA-037 and QA-038.

## Diversity and generator

Twelve fact/reasoning clusters were classified. Five dominated questions were rejected, and QA-035 was rewritten from a repeated reservoir-specific subtraction into a three-reservoir comparison. The new generator produced two reproducible demos from previously unused evidence without code changes.

## Scientific decision

The hardening layer is technically ready for targeted human review. It is not official gold: no QA, relation, alternative set, table interpretation or legal applicability decision has human verification.
""")

readiness={"schema_version":"1.0","decision":"TECHNICALLY_READY_FOR_TARGETED_HUMAN_REVIEW_NOT_GOLD",
 "TECHNICAL_CORRECTNESS":{"status":"READY","basis":{"audited_qa":38,"deterministic_repair_errors":len(bad),"hardening_tests":f"{tests['passed']}/{tests['total']}","existing_tests":"16/16;16/16;50/50"}},
 "SEMANTIC_CORRECTNESS":{"status":"PENDING_HUMAN_REVIEW","human_verified_qa":0,"minimality_semantic_verified":0},
 "BENCHMARK_QUALITY":{"status":"PARTIAL_HARDENED","keep":dec["KEEP"],"revise":dec["REVISE"],"reject":dec["REJECT"],"semantic_clusters":12,"cross_document_qa":0},
 "SCIENTIFIC_INTEGRITY":{"candidate_test":"SEALED_NOT_OPENED_NOT_HASHED","raw_v4_2_mutated":False,"retrieval_baselines_mutated":False,"fabricated_human_approval":False},
 "GENERATOR":{"generalization_demonstrated":True,"demo_drafts":len(demos),"supported_competencies":4,"universal_generator":False},
 "QA_HUMAN_GOLD_READY":False,"BENCHMARK_RELEASE_READY":False,
 "blockers":["0/38 QA human verified","0 evidence relations human verified","table extrema/header semantics pending review","legal/rule applicability pending domain review","no validated cross-document evidence relation","domain depth remains limited in D02/D04"]}
(HERE/"V4_2_HARDENING_READINESS.json").write_text(json.dumps(readiness,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

# Dependency file for a PDF-free independent bundle.
deps=json.loads((V42/"SOURCE_DEPENDENCIES.json").read_text(encoding="utf-8"))
(HERE/"SOURCE_DEPENDENCIES.json").write_text(json.dumps(deps,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print({"keep":dec["KEEP"],"revise":dec["REVISE"],"reject":dec["REJECT"],"repair_errors":len(bad),"reports":"built"})
