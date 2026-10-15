"""Sixteen required adversarial cases using synthetic and real-pilot mutations."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))
from QA_VALIDATOR_V2 import SourceStore, near_duplicates, validate  # noqa: E402


def load() -> list[dict]:
    return [json.loads(x) for x in (PARENT / "QA_GROUND_UP_PILOT.jsonl").read_text(encoding="utf-8").splitlines() if x]


def main() -> int:
    base = load(); store = SourceStore(); cases = []
    def add(name, kind, source, mutate, expected):
        rec = copy.deepcopy(base[source]); mutate(rec)
        cases.append((name, kind, rec, expected))

    add("01_shallow_question", "SYNTHETIC", 0, lambda r: r.update(question="Tài liệu nói gì về hệ thống?"), "SHALLOW_QUESTION")
    add("02_nonexistent_number", "MUTATION", 0, lambda r: r["evidence"][0]["facts"][0].update(value=999999), "FACT_VALUE_NOT_FOUND")
    add("03_wrong_domain", "MUTATION", 0, lambda r: r.update(domain=["D06"]), "DOMAIN_SOURCE_MISMATCH")
    add("04_fake_comparison", "SYNTHETIC", 2, lambda r: r["evidence"][0].update(facts=r["evidence"][0]["facts"][:1]), "FAKE_COMPARISON")
    add("05_fake_multi_evidence", "SYNTHETIC", 7, lambda r: r.update(evidence=r["evidence"][:1]), "FAKE_MULTI_EVIDENCE")
    def redundant(r):
        dup = copy.deepcopy(r["evidence"][0]); dup["evidence_id"] = "E2"; r["evidence"].append(dup); r["minimal_sufficient_evidence_sets"] = [["E1", "E2"]]
    add("06_self_declared_necessary", "SYNTHETIC", 0, redundant, "NON_MINIMAL_EVIDENCE_SET")
    add("07_wrong_entity", "MUTATION", 0, lambda r: r["evidence"][0]["facts"][0].update(entity="Hồ Dầu Tiếng"), "FACT_CONTEXT_NOT_FOUND")
    add("08_wrong_time", "MUTATION", 2, lambda r: r["evidence"][0]["facts"][0].update(time="2099"), "FACT_CONTEXT_NOT_FOUND")
    add("09_wrong_unit", "MUTATION", 2, lambda r: r["evidence"][0]["facts"][0].update(unit="m3/s"), "FACT_CONTEXT_NOT_FOUND")
    add("10_wrong_legal_validity", "MUTATION", 3, lambda r: r.update(competency="RULE_CONDITION_INTERPRETATION"), "DRAFT_RULE_NOT_APPLICABLE")
    add("11_wrong_arithmetic", "MUTATION", 2, lambda r: r["operation_trace"][0].update(result=181), "ARITHMETIC_MISMATCH")
    def mix(r):
        # Keep the mutation deliberately invalid at page level too; the target
        # assertion proves the system/facility join is independently detected.
        r["evidence"][1]["doc_id"] = "V4_CTTL_2024_dda51c21"
    add("12_mixed_facilities", "MUTATION", 7, mix, "MIXED_FACILITY_EVIDENCE")
    add("13_locator_right_fact_wrong", "MUTATION", 9, lambda r: r["evidence"][0]["facts"][0].update(value=99.99), "FACT_VALUE_NOT_FOUND")
    add("15_gold_missing_condition", "MUTATION", 6, lambda r: r.update(competency="RULE_CONDITION_INTERPRETATION"), "GOLD_MISSING_CONDITION")
    add("16_out_of_corpus", "SYNTHETIC", 0, lambda r: r["evidence"][0].update(doc_id="NOT_IN_CORPUS"), "SOURCE_NOT_IN_CORPUS")

    results = []
    fixture_dir = HERE / "fixtures"; fixture_dir.mkdir(exist_ok=True)
    for name, kind, record, expected in cases:
        (fixture_dir / f"{name}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = validate(record, store); codes = [x["code"] for x in result["issues"]]
        results.append({"name": name, "test_type": kind, "expected_code": expected, "observed_codes": codes,
                        "caught": expected in codes, "non_default": bool(codes) and not result["semantic_pass"]})

    dup = copy.deepcopy(base[0]); dup["qa_id"] = "V41-QA-999"; dup["question"] = base[0]["question"] + "?"
    dups = near_duplicates([base[0], dup])
    results.append({"name": "14_paraphrase_duplicate", "test_type": "MUTATION", "expected_code": "NEAR_DUPLICATE",
                    "observed_codes": [x["code"] for x in dups], "caught": bool(dups), "non_default": bool(dups)})

    summary = {"total": len(results), "caught": sum(x["caught"] for x in results),
               "non_default": sum(x["non_default"] for x in results), "all_pass": all(x["caught"] and x["non_default"] for x in results),
               "synthetic": sum(x["test_type"] == "SYNTHETIC" for x in results),
               "real_pilot_mutations": sum(x["test_type"] == "MUTATION" for x in results), "results": results}
    (HERE / "TEST_RESULTS.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("total", "caught", "non_default", "synthetic", "real_pilot_mutations", "all_pass")}))
    return 0 if summary["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
