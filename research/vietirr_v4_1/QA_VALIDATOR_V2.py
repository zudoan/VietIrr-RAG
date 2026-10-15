"""Three-layer validator for V4.1 ground-up QA.

Layer 2 proves only deterministic properties.  It deliberately returns
UNKNOWN/REVIEW for judgments that need a domain reviewer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "V4_CORPUS_MANIFEST.jsonl"
SCHEMA = HERE / "QA_SCHEMA_V2.json"

REQUIRED = ["qa_id", "origin_type", "lineage", "domain", "use_case", "competency", "question", "answer",
            "answer_components", "evidence", "required_relations", "allowed_operations", "minimal_sufficient_evidence_sets",
            "unsupported_conditions", "review"]
ALLOWED_DOMAINS = {"D01", "D02", "D03", "D04", "D05", "D06", "ANY"}
NEW_DOC_DOMAINS = {
    "V4_CTTL_2025_77c60f84": {"D01", "D02", "D04"},
    "V4_IWRP_2021_3031564c": {"D03", "D04", "D06"},
    "V4_CTTL_2024_dda51c21": {"D01", "D02", "D04", "D05"},
    "V4_BNNMT_2025_594e7382": {"D02", "D06"},
    "IRR_CTL_2025_c3d033a0": {"D05"}, "IRR_CTL_2025_57989573": {"D05"},
}
DOC_SYSTEMS = {
    "V4_CTTL_2025_77c60f84": "BAC_NAM_HA", "V4_IWRP_2021_3031564c": "BAC_NAM_HA",
    "V4_CTTL_2024_dda51c21": "CAI_LON_CAI_BE", "IRR_CTL_2025_c3d033a0": "CAI_LON_CAI_BE",
    "IRR_CTL_2025_57989573": "CAI_LON_CAI_BE",
}


def norm(value: Any) -> str:
    s = unicodedata.normalize("NFC", str(value)).lower()
    return re.sub(r"\s+", " ", s).strip()


def page_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SourceStore:
    def __init__(self) -> None:
        self.manifest = {}
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            row = json.loads(line); self.manifest[row["doc_id"]] = row
        self._pdf_cache: dict[str, list[str]] = {}

    def pages(self, doc_id: str) -> list[str]:
        row = self.manifest[doc_id]
        if "parsed_path" in row:
            data = json.loads((ROOT / row["parsed_path"]).read_text(encoding="utf-8"))
            return [p["text"] for p in data["pages"]]
        if doc_id not in self._pdf_cache:
            reader = PdfReader(str(ROOT / row["local_path"]))
            self._pdf_cache[doc_id] = [p.extract_text() or "" for p in reader.pages]
        return self._pdf_cache[doc_id]


def issue(code: str, message: str, layer: int, severity: str = "ERROR") -> dict:
    return {"code": code, "message": message, "layer": layer, "severity": severity}


def structural(record: dict, store: SourceStore) -> list[dict]:
    out = []
    for k in REQUIRED:
        if k not in record: out.append(issue("SCHEMA_REQUIRED", f"Missing {k}", 1))
    if out: return out
    if not re.fullmatch(r"V41-QA-\d{3}", str(record["qa_id"])): out.append(issue("BAD_QA_ID", "Invalid QA ID", 1))
    if record["origin_type"] != "GROUND_UP" or record["lineage"].get("legacy_qa_used") is not False:
        out.append(issue("ORIGIN_NOT_GROUND_UP", "Ground-up lineage not established", 1))
    serialized = norm(json.dumps(record, ensure_ascii=False))
    if "candidate_test" in serialized or "candidate gold" in serialized:
        out.append(issue("CANDIDATE_LEAKAGE", "Candidate Test reference forbidden", 1))
    if not set(record["domain"]).issubset(ALLOWED_DOMAINS): out.append(issue("BAD_DOMAIN", "Unknown domain", 1))
    evidence_ids = [e.get("evidence_id") for e in record["evidence"]]
    if len(evidence_ids) != len(set(evidence_ids)): out.append(issue("DUPLICATE_EVIDENCE_ID", "Duplicate evidence IDs", 1))
    component_ids = [c.get("component_id") for c in record["answer_components"]]
    if len(component_ids) != len(set(component_ids)): out.append(issue("DUPLICATE_COMPONENT_ID", "Duplicate component IDs", 1))
    for e in record["evidence"]:
        if e.get("doc_id") not in store.manifest:
            out.append(issue("SOURCE_NOT_IN_CORPUS", f"Unknown source {e.get('doc_id')}", 1)); continue
        page = e.get("locator", {}).get("page")
        try: count = len(store.pages(e["doc_id"]))
        except Exception as exc:
            out.append(issue("SOURCE_UNREADABLE", str(exc), 1)); continue
        if not isinstance(page, int) or page < 1 or page > count: out.append(issue("LOCATOR_OUT_OF_RANGE", f"Page {page}/{count}", 1))
    return out


def _value_tokens(value: Any) -> list[str]:
    if isinstance(value, bool) or value is None: return []
    if isinstance(value, (int, float)):
        base = f"{value:g}"
        return list({base, base.replace(".", ","), f"{value:,.0f}".replace(",", ".")})
    return [norm(value)]


def deterministic(record: dict, store: SourceStore) -> list[dict]:
    out = []
    question = norm(record["question"])
    if re.search(r"tài liệu (nói|đề cập).{0,20}(gì|như thế nào)", question):
        out.append(issue("SHALLOW_QUESTION", "Vague document-summary intent", 2))

    evidence_by_id = {e["evidence_id"]: e for e in record["evidence"]}
    facts = {}
    for e in record["evidence"]:
        pages = store.pages(e["doc_id"]); text = pages[e["locator"]["page"] - 1]; ntext = norm(text)
        if page_hash(text) != e["page_sha256"]: out.append(issue("PAGE_HASH_MISMATCH", e["evidence_id"], 2))
        if norm(e["anchor"]) not in ntext: out.append(issue("ANCHOR_NOT_FOUND", e["evidence_id"], 2))
        mapped = NEW_DOC_DOMAINS.get(e["doc_id"])
        if mapped and not (set(record["domain"]) & mapped or "ANY" in record["domain"]):
            out.append(issue("DOMAIN_SOURCE_MISMATCH", f"{record['domain']} vs {mapped}", 2))
        for f in e["facts"]:
            if f["fact_id"] in facts: out.append(issue("DUPLICATE_FACT_ID", f["fact_id"], 2))
            facts[f["fact_id"]] = f
            signature = [f.get("entity"), f.get("metric"), f.get("unit"), f.get("time")]
            for token in [norm(x) for x in signature if x not in (None, "", "NONE")]:
                if token not in ntext:
                    out.append(issue("FACT_CONTEXT_NOT_FOUND", f"{f['fact_id']}:{token}", 2)); break
            vt = _value_tokens(f.get("value"))
            if vt and not any(norm(t) in ntext for t in vt): out.append(issue("FACT_VALUE_NOT_FOUND", f["fact_id"], 2))
            if f["source_role"] == "DRAFT_RULE" and record["competency"] in {"RULE_CONDITION_INTERPRETATION", "RULE_OBSERVATION_ALIGNMENT"}:
                out.append(issue("DRAFT_RULE_NOT_APPLICABLE", f["fact_id"], 2))

    component_ids = {c["component_id"] for c in record["answer_components"]}
    for c in record["answer_components"]:
        if not set(c["supported_by"]).issubset(facts): out.append(issue("COMPONENT_UNKNOWN_FACT", c["component_id"], 2))
        if c["kind"] == "NUMBER" and c.get("unit") is None:
            supported_metrics = {norm(facts[x]["metric"]) for x in c["supported_by"] if x in facts}
            if not supported_metrics or not all("wqi" in x or "index" in x or "chỉ số" in x for x in supported_metrics):
                out.append(issue("NUMBER_WITHOUT_UNIT", c["component_id"], 2))
    for e in record["evidence"]:
        if not set(e["supports_components"]).issubset(component_ids): out.append(issue("EVIDENCE_UNKNOWN_COMPONENT", e["evidence_id"], 2))

    declared_sets = record["minimal_sufficient_evidence_sets"]
    for s in declared_sets:
        if not set(s).issubset(evidence_by_id): out.append(issue("MINSET_UNKNOWN_EVIDENCE", str(s), 2)); continue
        covered = set().union(*(set(evidence_by_id[x]["supports_components"]) for x in s))
        if covered != component_ids: out.append(issue("INSUFFICIENT_EVIDENCE_SET", str(s), 2))
        for x in s:
            remaining = set().union(*(set(evidence_by_id[y]["supports_components"]) for y in s if y != x)) if len(s) > 1 else set()
            if remaining == component_ids: out.append(issue("NON_MINIMAL_EVIDENCE_SET", f"{x} is redundant", 2))

    comp = record["competency"]
    all_fact_list = list(facts.values())
    if comp in {"QUANTITATIVE_COMPARISON", "TEMPORAL_COMPARISON", "VERIFIABLE_COMPUTATION"}:
        if len(all_fact_list) < 2: out.append(issue("FAKE_COMPARISON", "Fewer than two typed operands", 2))
        metrics = {f["metric"] for f in all_fact_list}; units = {f["unit"] for f in all_fact_list}
        if comp != "VERIFIABLE_COMPUTATION" and (len(metrics) != 1 or len(units) != 1): out.append(issue("INCOMPATIBLE_OPERANDS", "Metric/unit mismatch", 2))
    if record.get("evidence_pattern") == "CROSS_DOCUMENT":
        if len({e["doc_id"] for e in record["evidence"]}) < 2: out.append(issue("FAKE_MULTI_EVIDENCE", "Cross-document label without two sources", 2))
        if not record["required_relations"]: out.append(issue("MISSING_SOURCE_RELATION", "No source relation", 2))
        elif any(r["status"] != "VERIFIED" for r in record["required_relations"]):
            out.append(issue("RELATION_REVIEW_REQUIRED", "Relation is not human verified", 2, "REVIEW"))
        systems = {DOC_SYSTEMS.get(e["doc_id"]) for e in record["evidence"] if DOC_SYSTEMS.get(e["doc_id"])}
        if len(systems) > 1 and not any(r["status"] == "VERIFIED" for r in record["required_relations"]):
            out.append(issue("MIXED_FACILITY_EVIDENCE", f"Unverified cross-system join: {sorted(systems)}", 2))

    traces = record.get("operation_trace", [])
    for trace in traces:
        if trace["operation"] not in record["allowed_operations"]: out.append(issue("OPERATION_NOT_ALLOWED", trace["operation"], 2)); continue
        vals = []
        for fid in trace["inputs"]:
            if fid not in facts or not isinstance(facts[fid]["value"], (int, float)):
                out.append(issue("BAD_OPERATION_INPUT", fid, 2)); vals = []; break
            vals.append(float(facts[fid]["value"]))
        if not vals: continue
        expected = vals[0] - vals[1] if trace["operation"] == "SUBTRACT" and len(vals) == 2 else sum(vals) if trace["operation"] == "ADD" else None
        if expected is not None and not math.isclose(float(trace.get("result")), expected, rel_tol=1e-9, abs_tol=1e-9):
            out.append(issue("ARITHMETIC_MISMATCH", f"Expected {expected}", 2))
        target = next((c for c in record["answer_components"] if c["component_id"] == trace["output_component"]), None)
        if expected is not None and (target is None or not math.isclose(float(target["value"]), expected, rel_tol=1e-9, abs_tol=1e-9)):
            out.append(issue("GOLD_OPERATION_MISMATCH", trace["output_component"], 2))

    if comp == "RULE_CONDITION_INTERPRETATION":
        metrics = {norm(f["metric"]) for f in all_fact_list}
        if not any("condition" in x or "điều kiện" in x for x in metrics): out.append(issue("GOLD_MISSING_CONDITION", "Rule condition absent", 2))
    return out


def human_layer(record: dict) -> list[dict]:
    r = record["review"]
    out = []
    if r["status"] == "HUMAN_ACCEPTED":
        if not r.get("reviewer_id") or any(r.get(k) != "PASS" for k in ("business_realism", "evidence_sufficiency", "semantic_correctness")):
            out.append(issue("INVALID_HUMAN_ACCEPTANCE", "Named reviewer and all three PASS decisions required", 3))
    else:
        out.append(issue("HUMAN_REVIEW_PENDING", "No human/domain semantic acceptance", 3, "REVIEW"))
    return out


def validate(record: dict, store: SourceStore | None = None) -> dict:
    store = store or SourceStore()
    l1 = structural(record, store)
    l2 = [] if any(x["severity"] == "ERROR" for x in l1) else deterministic(record, store)
    l3 = [] if any(x["severity"] == "ERROR" for x in l1 + l2) else human_layer(record)
    def state(xs: list[dict]) -> str:
        return "FAIL" if any(x["severity"] == "ERROR" for x in xs) else "REVIEW" if xs else "PASS"
    states = {"layer1": state(l1), "layer2": state(l2), "layer3": state(l3)}
    semantic_pass = all(v == "PASS" for v in states.values())
    return {"qa_id": record.get("qa_id"), "layers": states, "semantic_pass": semantic_pass,
            "release_state": "SEMANTIC_PASS" if semantic_pass else "REJECTED" if "FAIL" in states.values() else "READY_FOR_HUMAN_REVIEW",
            "issues": l1 + l2 + l3}


def near_duplicates(records: list[dict]) -> list[dict]:
    def toks(s: str) -> set[str]: return set(re.findall(r"\w+", norm(s)))
    out = []
    for i, a in enumerate(records):
        ta = toks(a["question"])
        for b in records[i + 1:]:
            tb = toks(b["question"]); score = len(ta & tb) / max(1, len(ta | tb))
            if score >= 0.82: out.append({"a": a["qa_id"], "b": b["qa_id"], "jaccard": round(score, 4), "code": "NEAR_DUPLICATE"})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("input"); ap.add_argument("--output")
    args = ap.parse_args(); path = Path(args.input)
    records = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    store = SourceStore(); result = {"records": [validate(x, store) for x in records], "near_duplicates": near_duplicates(records)}
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output: Path(args.output).write_text(text, encoding="utf-8")
    print(text)
