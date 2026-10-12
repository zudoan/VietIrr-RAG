import json
from pathlib import Path

ROOT = Path("d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag")
STATS_PATH = ROOT / "reports/v2_4/dataset_stats.json"
READINESS_PATH = ROOT / "reports/v2_4/10_v2_4_readiness.json"
FINAL_QA_PATH = ROOT / "data/qa/v2_4_freeze/pilot_qa_v2_4_final.jsonl"
REJECTED_QA_PATH = ROOT / "data/qa/v2_4_freeze/rejected_qa_v2_4.jsonl"
UNCERTAIN_QA_PATH = ROOT / "data/qa/v2_4_freeze/uncertain_qa_v2_4.jsonl"
FINAL_NEG_PATH = ROOT / "data/negatives/v2_4_freeze/negative_sets_v2_4_final.jsonl"
NONMIN_NEG_PATH = ROOT / "data/negatives/v2_4_freeze/nonminimal_negatives_v2_4.jsonl"
REJ_NEG_PATH = ROOT / "data/negatives/v2_4_freeze/rejected_negatives_v2_4.jsonl"

def count_lines(path):
    if not path.exists():
        return 0
    return sum(1 for line in open(path, encoding="utf-8") if line.strip())

def check_consistency():
    print("Checking V2.4 report consistency against canonical stats...")
    with open(STATS_PATH, "r", encoding="utf-8") as f:
        stats = json.load(f)

    with open(READINESS_PATH, "r", encoding="utf-8") as f:
        readiness = json.load(f)

    n_final_qa = count_lines(FINAL_QA_PATH)
    n_rej_qa = count_lines(REJECTED_QA_PATH)
    n_unc_qa = count_lines(UNCERTAIN_QA_PATH)

    n_final_neg = count_lines(FINAL_NEG_PATH)
    n_nonmin_neg = count_lines(NONMIN_NEG_PATH)
    n_rej_neg = count_lines(REJ_NEG_PATH)

    errors = []

    # Check QA counts
    if n_final_qa != stats["qa"]["qa_final"]:
        errors.append(f"QA final count mismatch: file={n_final_qa}, stats={stats['qa']['qa_final']}")
    if n_final_qa != readiness["QA_FINAL"]:
        errors.append(f"QA final count mismatch with readiness: file={n_final_qa}, readiness={readiness['QA_FINAL']}")

    if n_rej_qa != stats["qa"]["qa_rejected"]:
        errors.append(f"QA rejected count mismatch: file={n_rej_qa}, stats={stats['qa']['qa_rejected']}")
    if n_rej_qa != readiness["QA_REJECTED"]:
        errors.append(f"QA rejected count mismatch with readiness: file={n_rej_qa}, readiness={readiness['QA_REJECTED']}")

    if n_unc_qa != stats["qa"]["qa_uncertain"]:
        errors.append(f"QA uncertain count mismatch: file={n_unc_qa}, stats={stats['qa']['qa_uncertain']}")
    if n_unc_qa != readiness["QA_UNCERTAIN"]:
        errors.append(f"QA uncertain count mismatch with readiness: file={n_unc_qa}, readiness={readiness['QA_UNCERTAIN']}")

    # Check Negatives counts
    if n_final_neg != stats["negatives"]["final_core_negatives"]:
        errors.append(f"Negatives final count mismatch: file={n_final_neg}, stats={stats['negatives']['final_core_negatives']}")
    if n_nonmin_neg != stats["negatives"]["nonminimal_negatives"]:
        errors.append(f"Negatives non-minimal count mismatch: file={n_nonmin_neg}, stats={stats['negatives']['nonminimal_negatives']}")
    if n_rej_neg != stats["negatives"]["rejected_negatives"]:
        errors.append(f"Negatives rejected count mismatch: file={n_rej_neg}, stats={stats['negatives']['rejected_negatives']}")

    total_valid_negs = sum(readiness[k] for k in ["VALID_WRONG_ENTITY", "VALID_WRONG_METRIC", "VALID_WRONG_PERIOD", "VALID_WRONG_UNIT", "VALID_MINIMAL_PROVENANCE_CONFLICT"])
    if total_valid_negs != n_final_neg:
        errors.append(f"Total valid negatives in readiness ({total_valid_negs}) != file count ({n_final_neg})")

    # Check that NO QA in final core has critical warnings
    with open(FINAL_QA_PATH, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            q = json.loads(line)
            if q.get("critical_validation_status") != "PASS":
                errors.append(f"QA {q.get('qa_id')} in final core does not have critical_validation_status=PASS")
            if q.get("v2_4_decision") != "PASS":
                errors.append(f"QA {q.get('qa_id')} in final core does not have v2_4_decision=PASS")

    if errors:
        print("REPORT CONSISTENCY CHECK: FAIL")
        for err in errors:
            print("  ERROR:", err)
        return False
    else:
        print("REPORT CONSISTENCY CHECK: PASS")
        print(f"All {n_final_qa} final QA and {n_final_neg} final negatives match canonical numbers perfectly.")
        return True

if __name__ == "__main__":
    check_consistency()
