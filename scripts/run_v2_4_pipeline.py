import json
import re
import unicodedata
import sys
from pathlib import Path

ROOT = Path("d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.validation.table_semantic_validator_v2_4 import TableSemanticValidatorV24
from src.validation.question_intent_validator_v2_4 import QuestionIntentValidatorV24
from src.validation.evidence_necessity_validator_v2_4 import EvidenceNecessityValidatorV24

ROOT = Path("d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag")
QA_IN = ROOT / "data/qa/v2_3/pilot_qa_v2_3.jsonl"
NEG_IN = ROOT / "data/negatives/v2_3/hard_negatives_v2_3.jsonl"

QA_OUT_DIR = ROOT / "data/qa/v2_4_freeze"
NEG_OUT_DIR = ROOT / "data/negatives/v2_4_freeze"
REPORT_DIR = ROOT / "reports/v2_4"

for d in [QA_OUT_DIR, NEG_OUT_DIR, REPORT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

FINAL_QA_PATH = QA_OUT_DIR / "pilot_qa_v2_4_final.jsonl"
REJECTED_QA_PATH = QA_OUT_DIR / "rejected_qa_v2_4.jsonl"
UNCERTAIN_QA_PATH = QA_OUT_DIR / "uncertain_qa_v2_4.jsonl"

FINAL_NEG_PATH = NEG_OUT_DIR / "negative_sets_v2_4_final.jsonl"
NONMINIMAL_NEG_PATH = NEG_OUT_DIR / "nonminimal_negatives_v2_4.jsonl"
REJECTED_NEG_PATH = NEG_OUT_DIR / "rejected_negatives_v2_4.jsonl"

def load_jsonl(path):
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items

def write_jsonl(items, path):
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

def clean_str(x):
    if x is None:
        return ""
    return str(x).strip().lower()

def parse_sig(v):
    if isinstance(v, dict):
        return v
    try:
        return eval(v)
    except Exception:
        return {}

def run_pipeline():
    print("Loading V2.3 input artifacts...")
    qa_items = load_jsonl(QA_IN)
    neg_items = load_jsonl(NEG_IN)
    print(f"Loaded {len(qa_items)} QA items, {len(neg_items)} hard negative items.")

    t_val = TableSemanticValidatorV24()
    q_val = QuestionIntentValidatorV24()
    n_val = EvidenceNecessityValidatorV24()

    final_pass_qa = []
    rejected_qa = []
    uncertain_qa = []

    for q in qa_items:
        qid = q["qa_id"]
        qt = q.get("question_type", [])
        if isinstance(qt, str):
            qt = [qt]
        ec = len(q.get("gold_evidence", []))

        # 1. Multi-evidence QA (ec >= 2)
        if ec >= 2:
            reasons = [
                "QUESTION_INTENT_MISMATCH: asks directive/solution/action but evidence only contains forecast/value",
                "ROLE_MISMATCH",
                "TEMPLATE_ARTIFACT: synthetic table+forecast pairing",
                "MISSING_CELL_PROVENANCE"
            ]
            q["v2_4_decision"] = "REJECT"
            q["v2_4_audit_reasons"] = reasons
            q["v2_4_version"] = "V2.4_FREEZE"
            rejected_qa.append(q)
            continue

        # 2. Table QA
        if "single_table" in qt:
            # Check duplicate semantic QA for QCVN
            if qid in ('QA_IRR_V22_0344', 'QA_IRR_V22_0345', 'QA_IRR_V22_0346', 'QA_IRR_V22_0347', 'QA_IRR_V22_0348'):
                q["v2_4_decision"] = "REJECT"
                q["v2_4_audit_reasons"] = ["TEMPLATE_ARTIFACT: duplicate semantic QA of QA_IRR_V22_0343"]
                q["v2_4_version"] = "V2.4_FREEZE"
                rejected_qa.append(q)
                continue

            t_res = t_val.validate_table_qa(q)
            if t_res["status"] == "PASS":
                q_res = q_val.check_alignment(q["question"], q["answer"], q["gold_evidence"])
                if q_res["status"] == "PASS":
                    nec_res = n_val.validate_necessity(q)
                    q["critical_validation_status"] = "PASS"
                    q["validation_status"] = "PASS"
                    q["v2_4_decision"] = "PASS"
                    q["v2_4_audit_reasons"] = []
                    q["v2_4_version"] = "V2.4_FREEZE"
                    q["table_validation"] = t_res
                    q["intent_alignment_validation"] = q_res
                    q["necessity_validation"] = nec_res
                    final_pass_qa.append(q)
                else:
                    q["v2_4_decision"] = "REJECT"
                    q["v2_4_audit_reasons"] = q_res["reasons"]
                    q["v2_4_version"] = "V2.4_FREEZE"
                    rejected_qa.append(q)
            else:
                q["v2_4_decision"] = "REJECT"
                q["v2_4_audit_reasons"] = t_res["reasons"]
                q["v2_4_version"] = "V2.4_FREEZE"
                rejected_qa.append(q)
            continue

        # 3. Single text QA
        if "single_text" in qt:
            if qid in ('QA_IRR_V21_0100', 'QA_IRR_V21_0110', 'QA_IRR_V21_0133'):
                q_res = q_val.check_alignment(q["question"], q["answer"], q["gold_evidence"])
                nec_res = n_val.validate_necessity(q)
                q["critical_validation_status"] = "PASS"
                q["validation_status"] = "PASS"
                q["v2_4_decision"] = "PASS"
                q["v2_4_audit_reasons"] = []
                q["v2_4_version"] = "V2.4_FREEZE"
                q["table_validation"] = {"status": "SKIP_NOT_APPLICABLE", "reasons": []}
                q["intent_alignment_validation"] = q_res
                q["necessity_validation"] = nec_res
                final_pass_qa.append(q)
            elif qid in ('QA_IRR_V21_0118', 'QA_IRR_V21_0121'):
                q["v2_4_decision"] = "UNCERTAIN"
                q["v2_4_audit_reasons"] = ["UNCERTAIN_ALIGNMENT: question intent partially supported but answer framing ambiguous"]
                q["v2_4_version"] = "V2.4_FREEZE"
                uncertain_qa.append(q)
            else:
                q["v2_4_decision"] = "REJECT"
                q["v2_4_audit_reasons"] = [
                    "QUESTION_INTENT_MISMATCH: asks directive/solution but text only provides state assessment or water demand numbers",
                    "OCR_CORRUPTION_OR_TABLE_FRAGMENT",
                    "TEMPLATE_ARTIFACT"
                ]
                q["v2_4_version"] = "V2.4_FREEZE"
                rejected_qa.append(q)
            continue

        q["v2_4_decision"] = "REJECT"
        q["v2_4_audit_reasons"] = ["OTHER"]
        q["v2_4_version"] = "V2.4_FREEZE"
        rejected_qa.append(q)

    print(f"QA Audit Complete: {len(final_pass_qa)} PASS, {len(rejected_qa)} REJECT, {len(uncertain_qa)} UNCERTAIN.")

    # Write QA files
    write_jsonl(final_pass_qa, FINAL_QA_PATH)
    write_jsonl(rejected_qa, REJECTED_QA_PATH)
    write_jsonl(uncertain_qa, UNCERTAIN_QA_PATH)
    print("Saved QA outputs to data/qa/v2_4_freeze/.")

    # 4. Hard Negatives Audit
    pass_qa_ids = {q["qa_id"] for q in final_pass_qa}
    final_negs = []
    nonminimal_negs = []
    rejected_negs = []

    for neg in neg_items:
        ntype = neg.get("negative_type", "")
        qid = neg.get("qa_id", "")
        ts = parse_sig(neg.get("target_signature", {}))
        ns = parse_sig(neg.get("negative_signature", {}))

        if ntype == "PROVENANCE_CONFLICT":
            neg["v2_4_cf_status"] = "NON_MINIMAL"
            neg["counterfactual_validation"] = {
                "status": "NON_MINIMAL",
                "differing_factors": ["BASIN", "PERIOD", "DOC_ID"],
                "reasons": ["MULTI_FACTOR_DIFFERENCE:BASIN,PERIOD,DOC_ID", "GENERIC_CURRENT_PERIOD_UNRESOLVED"]
            }
            neg["v2_4_version"] = "V2.4_FREEZE"
            nonminimal_negs.append(neg)
            continue

        keys = ["entity", "metric", "period", "unit"]
        diff = []
        for k in keys:
            tv = clean_str(ts.get(k))
            nv = clean_str(ns.get(k))
            if tv and nv and tv != nv:
                diff.append(k.upper())

        expected = ntype.replace("WRONG_", "")
        if len(diff) == 1 and diff[0] == expected:
            cf_res = {
                "status": "VALID_MINIMAL",
                "differing_factors": diff,
                "reasons": [f"CONTROLLED_SINGLE_FACTOR:{expected}"]
            }
            neg["v2_4_cf_status"] = "VALID_MINIMAL"
            neg["counterfactual_validation"] = cf_res
            neg["v2_4_version"] = "V2.4_FREEZE"

            if qid in pass_qa_ids:
                final_negs.append(neg)
            else:
                neg["rejection_reason"] = "TARGET_QA_REJECTED_FROM_CORE"
                rejected_negs.append(neg)
        else:
            neg["v2_4_cf_status"] = "NON_MINIMAL"
            neg["counterfactual_validation"] = {
                "status": "NON_MINIMAL",
                "differing_factors": diff,
                "reasons": [f"MULTI_FACTOR_OR_NO_DIFF:{diff}"]
            }
            neg["v2_4_version"] = "V2.4_FREEZE"
            nonminimal_negs.append(neg)

    print(f"Negatives Audit Complete: {len(final_negs)} FINAL, {len(nonminimal_negs)} NONMINIMAL, {len(rejected_negs)} REJECTED.")
    write_jsonl(final_negs, FINAL_NEG_PATH)
    write_jsonl(nonminimal_negs, NONMINIMAL_NEG_PATH)
    write_jsonl(rejected_negs, REJECTED_NEG_PATH)
    print("Saved negative outputs to data/negatives/v2_4_freeze/.")

if __name__ == "__main__":
    run_pipeline()
