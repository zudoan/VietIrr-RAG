import json
import random
from pathlib import Path

ROOT = Path("d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag")
QA_FINAL = ROOT / "data/qa/v2_4_freeze/pilot_qa_v2_4_final.jsonl"
NEG_FINAL = ROOT / "data/negatives/v2_4_freeze/negative_sets_v2_4_final.jsonl"
SAMPLE_DIR = ROOT / "reports/v2_4/human_review_sample"
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

def load_jsonl(path):
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]

def format_review_entry(q):
    prov = q.get("gold_evidence", [{}])[0].get("table_cell_provenance")
    if isinstance(prov, str):
        try:
            prov = eval(prov)
        except Exception:
            prov = {}

    entry = {
        "qa_id": q.get("qa_id"),
        "question": q.get("question"),
        "answer": q.get("answer"),
        "doc_id": q.get("doc_id"),
        "pages": q.get("gold_pages", [q.get("gold_evidence", [{}])[0].get("page_number")]),
        "exact_evidence": [e.get("exact_content") for e in q.get("gold_evidence", [])],
        "evidence_roles": [e.get("role") for e in q.get("gold_evidence", [])],
        "answer_components": q.get("necessity_validation", {}).get("answer_components", []),
        "necessity_result": q.get("necessity_validation", {}).get("necessity_status", "PASS"),
        "table_traceability": prov if prov else "N/A (text-only)"
    }
    return entry

def build_review_package():
    random.seed(42)
    qa_items = load_jsonl(QA_FINAL)
    neg_items = load_jsonl(NEG_FINAL)

    # 1. 20 single-evidence
    single_ev = [q for q in qa_items if len(q.get("gold_evidence", [])) == 1]
    sample_single = random.sample(single_ev, min(20, len(single_ev)))

    # 2. 20 table QA
    table_qa = [q for q in qa_items if any(e.get("region_type") == "table" for e in q.get("gold_evidence", []))]
    sample_table = random.sample(table_qa, min(20, len(table_qa)))

    # 3. 20 core-long (all available)
    core_long = [q for q in qa_items if "core_long" in q.get("question_type", [])]
    sample_core_long = list(core_long)  # all available (16 items)

    # 4. 20 hard negatives
    sample_negs = random.sample(neg_items, min(20, len(neg_items)))

    # Save JSONL samples
    with open(SAMPLE_DIR / "sample_single_evidence_20.jsonl", "w", encoding="utf-8") as f:
        for q in sample_single:
            f.write(json.dumps(format_review_entry(q), ensure_ascii=False) + "\n")

    with open(SAMPLE_DIR / "sample_table_qa_20.jsonl", "w", encoding="utf-8") as f:
        for q in sample_table:
            f.write(json.dumps(format_review_entry(q), ensure_ascii=False) + "\n")

    with open(SAMPLE_DIR / "sample_core_long_all.jsonl", "w", encoding="utf-8") as f:
        for q in sample_core_long:
            f.write(json.dumps(format_review_entry(q), ensure_ascii=False) + "\n")

    with open(SAMPLE_DIR / "sample_hard_negatives_20.jsonl", "w", encoding="utf-8") as f:
        for n in sample_negs:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")

    # Generate Inspection Markdown
    md_path = SAMPLE_DIR / "README_human_inspection.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# VietIrrDocBench V2.4 - Human Review Package\n\n")
        f.write("Package sampled exclusively from the **FINAL PASS-only frozen dataset** (`pilot_qa_v2_4_final.jsonl`).\n\n")
        f.write(f"- Single-evidence sample: {len(sample_single)} QA\n")
        f.write(f"- Table QA sample: {len(sample_table)} QA\n")
        f.write(f"- Core-long sample: {len(sample_core_long)} QA (all eligible retained)\n")
        f.write(f"- Two-evidence sample: 0 (all 106 V2.3 2-evidence items rejected due to forecast vs directive semantic mismatch)\n")
        f.write(f"- Three-evidence sample: 0 (all 50 V2.3 3-evidence items rejected due to lack of cell provenance and semantic mismatch)\n")
        f.write(f"- Hard negatives sample: {len(sample_negs)} items\n\n")
        f.write("## Sample Inspection (First 5 Single-Evidence QA)\n\n")

        for idx, q in enumerate(sample_single[:5]):
            entry = format_review_entry(q)
            f.write(f"### {idx+1}. QA ID: `{entry['qa_id']}`\n")
            f.write(f"- **Document**: `{entry['doc_id']}` (Page {entry['pages']})\n")
            f.write(f"- **Question**: {entry['question']}\n")
            f.write(f"- **Answer**: {entry['answer']}\n")
            f.write(f"- **Exact Evidence**: `{entry['exact_evidence'][0]}`\n")
            f.write(f"- **Evidence Role**: `{entry['evidence_roles'][0]}`\n")
            f.write(f"- **Traceability**: `{entry['table_traceability']}`\n\n")

    print(f"Generated Human Review Package in {SAMPLE_DIR}")

if __name__ == "__main__":
    build_review_package()
