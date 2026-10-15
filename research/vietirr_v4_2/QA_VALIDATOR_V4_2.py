"""Deterministic validation for V4.2 drafts and self-contained source fixtures."""
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


def norm(v: Any) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(v)).lower()).strip()


def issue(code: str, message: str, layer: int, severity: str = "ERROR") -> dict:
    return {"code": code, "message": message, "layer": layer, "severity": severity}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


class Registry:
    def __init__(self, here: Path = HERE):
        self.bank = {x["evidence_id"]: x for x in load_jsonl(here / "EVIDENCE_BANK.jsonl")}
        set_path = here / "EVIDENCE_SET_CANDIDATES.jsonl"
        self.sets = {x["evidence_set_id"]: x for x in load_jsonl(set_path)}
        manifest_path = here.parent / "vietirr_v4_1" / "V4_CORPUS_MANIFEST.jsonl"
        self.manifest = {x["doc_id"]: x for x in load_jsonl(manifest_path)} if manifest_path.exists() else {}
        self._pages: dict[str, list[str]] = {}

    def pages(self, doc_id: str) -> list[str]:
        if doc_id in self._pages: return self._pages[doc_id]
        row = self.manifest[doc_id]
        if row.get("parsed_path"):
            obj = json.loads((ROOT / row["parsed_path"]).read_text(encoding="utf-8")); out = [p["text"] for p in obj["pages"]]
        else: out = [p.extract_text() or "" for p in PdfReader(str(ROOT / row["local_path"])).pages]
        self._pages[doc_id] = out
        return out


REQUIRED = {"qa_id","origin_type","coverage_cell_id","lineage","domain","competency","difficulty","evidence_pattern",
            "question","answer","reasoning_plan","evidence_set_id","evidence_ids","answer_components","operations",
            "unsupported_conditions","source_check","review"}


def validate(record: dict, reg: Registry, check_sources: bool = False) -> dict:
    problems = []
    missing = sorted(REQUIRED - record.keys())
    if missing: problems.append(issue("SCHEMA_REQUIRED", ", ".join(missing), 1))
    if problems: return finish(record, problems)
    if not re.fullmatch(r"V42-QA-\d{3}", record["qa_id"]): problems.append(issue("BAD_QA_ID", record["qa_id"], 1))
    if record["origin_type"] != "GROUND_UP" or record["lineage"].get("legacy_qa_used") is not False:
        problems.append(issue("ORIGIN_NOT_GROUND_UP", "ground-up lineage absent", 1))
    if record["lineage"].get("candidate_test_accessed") is not False:
        problems.append(issue("CANDIDATE_LEAKAGE", "candidate access must be false", 1))
    if record["lineage"].get("generation_order") != ["USE_CASE","EVIDENCE_SET","REASONING_PLAN","QA_DRAFT"]:
        problems.append(issue("WRONG_GENERATION_ORDER", "must start from use case/evidence", 1))
    sid = record["evidence_set_id"]
    if sid not in reg.sets: problems.append(issue("UNKNOWN_EVIDENCE_SET", sid, 1))
    elif reg.sets[sid]["status"] != "DRAFT_ELIGIBLE": problems.append(issue("INELIGIBLE_EVIDENCE_SET", sid, 1))
    ids = record["evidence_ids"]
    if len(ids) != len(set(ids)): problems.append(issue("DUPLICATE_EVIDENCE_ID", record["qa_id"], 1))
    for eid in ids:
        if eid not in reg.bank: problems.append(issue("UNKNOWN_EVIDENCE", eid, 1))
    if sid in reg.sets and not set(ids).issubset(reg.sets[sid]["evidence_ids"]):
        problems.append(issue("EVIDENCE_OUTSIDE_SET", sid, 1))
    if re.search(r"tài liệu (nói|đề cập).{0,20}(gì|như thế nào)", norm(record["question"])):
        problems.append(issue("SHALLOW_QUESTION", "unbounded summary request", 2))
    for comp in record["answer_components"]:
        if not set(comp.get("supported_by", [])).issubset(set(ids)):
            problems.append(issue("COMPONENT_UNKNOWN_EVIDENCE", comp.get("component_id", "?"), 2))
    for op in record["operations"]:
        vals = op["inputs"]
        expected = sum(vals) if op["operation"] == "ADD" else vals[0] - vals[1] if op["operation"] == "SUBTRACT" else None
        if expected is not None and not math.isclose(float(op["result"]), float(expected), abs_tol=1e-8):
            problems.append(issue("ARITHMETIC_MISMATCH", f"{op['result']} != {expected}", 2))
    if record["competency"] in {"QUANTITATIVE_COMPARISON","VERIFIABLE_COMPUTATION"} and len(ids) < 2:
        problems.append(issue("FAKE_COMPARISON", "fewer than two evidence operands", 2))
    if record["evidence_pattern"] == "CROSS_DOCUMENT":
        docs = {reg.bank[x]["doc_id"] for x in ids if x in reg.bank}
        if len(docs) < 2: problems.append(issue("FAKE_MULTI_EVIDENCE", "fewer than two documents", 2))
    if check_sources:
        for eid in ids:
            if eid not in reg.bank: continue
            ev = reg.bank[eid]
            try:
                row = reg.manifest[ev["doc_id"]]; raw = (ROOT / row["local_path"]).read_bytes()
                if hashlib.sha256(raw).hexdigest() != ev["pdf_sha256"]: problems.append(issue("PDF_HASH_MISMATCH", eid, 2))
                text = reg.pages(ev["doc_id"])[ev["page"] - 1]
                if hashlib.sha256(text.encode("utf-8")).hexdigest() != ev["page_sha256"]: problems.append(issue("PAGE_HASH_MISMATCH", eid, 2))
            except Exception as exc: problems.append(issue("SOURCE_UNREADABLE", f"{eid}: {exc}", 2))
    if record["review"]["status"] == "HUMAN_ACCEPTED":
        if not record["review"].get("reviewer_id") or record["review"].get("semantic_correctness") != "PASS":
            problems.append(issue("INVALID_HUMAN_ACCEPTANCE", record["qa_id"], 3))
    else: problems.append(issue("HUMAN_REVIEW_PENDING", "domain review not completed", 3, "REVIEW"))
    return finish(record, problems)


def finish(record: dict, problems: list[dict]) -> dict:
    states = {}
    for layer in (1,2,3):
        xs = [x for x in problems if x["layer"] == layer]
        states[f"layer{layer}"] = "FAIL" if any(x["severity"] == "ERROR" for x in xs) else "REVIEW" if xs else "PASS"
    return {"qa_id": record.get("qa_id"), "layers": states,
            "release_state": "REJECTED" if "FAIL" in states.values() else "READY_FOR_HUMAN_REVIEW" if "REVIEW" in states.values() else "SEMANTIC_PASS",
            "issues": problems}


def value_forms(v: Any) -> set[str]:
    if isinstance(v, (int,float)):
        x = f"{v:g}"; return {x, x.replace(".", ","), f"{v:,.0f}".replace(",", ".")}
    return {norm(v)}


def validate_fixture_assertion(fixture: dict, asserted_value: Any) -> list[dict]:
    """Validate a fact against embedded source text; never touches the PDF."""
    raw = fixture["source_text"].encode("utf-8")
    out = []
    if hashlib.sha256(raw).hexdigest() != fixture["source_text_sha256"]:
        out.append(issue("FIXTURE_HASH_MISMATCH", fixture["fixture_id"], 2))
    text = norm(fixture["source_text"])
    if not any(norm(x) in text for x in value_forms(asserted_value)):
        out.append(issue("FACT_VALUE_NOT_FOUND", str(asserted_value), 2))
    return out


def near_duplicates(records: list[dict], threshold: float = .82) -> list[dict]:
    def tokens(s): return set(re.findall(r"\w+", norm(s)))
    out=[]
    for i,a in enumerate(records):
        ta=tokens(a["question"])
        for b in records[i+1:]:
            tb=tokens(b["question"]); score=len(ta & tb)/max(1,len(ta | tb))
            if score >= threshold: out.append({"a":a["qa_id"],"b":b["qa_id"],"jaccard":round(score,4),"code":"NEAR_DUPLICATE"})
    return out


if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("input"); ap.add_argument("--output"); ap.add_argument("--check-sources",action="store_true")
    args=ap.parse_args(); recs=load_jsonl(Path(args.input)); reg=Registry()
    result={"records":[validate(x,reg,args.check_sources) for x in recs],"near_duplicates":near_duplicates(recs)}
    result["summary"]={"total":len(recs),"layer1_fail":sum(x["layers"]["layer1"]=="FAIL" for x in result["records"]),
                       "layer2_fail":sum(x["layers"]["layer2"]=="FAIL" for x in result["records"]),
                       "pending_human":sum(x["layers"]["layer3"]=="REVIEW" for x in result["records"]),
                       "human_accepted":0,"near_duplicates":len(result["near_duplicates"])}
    text=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if args.output: Path(args.output).write_text(text,encoding="utf-8")
    print(json.dumps(result["summary"],ensure_ascii=False))
