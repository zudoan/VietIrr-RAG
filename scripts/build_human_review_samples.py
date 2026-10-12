import sys
sys.stdout.reconfigure(encoding='utf-8')
import json
from pathlib import Path

def main():
    qa_file = Path("data/qa/pilot_qa.jsonl")
    neg_file = Path("data/negatives/hard_negatives.jsonl")
    out_dir = Path("reports/human_review_sample")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    qa_list = []
    with open(qa_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                qa_list.append(json.loads(line))
                
    neg_list = []
    with open(neg_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                neg_list.append(json.loads(line))
                
    # 1. Stratified samples
    samples = {
        "text_only": [q for q in qa_list if q["modalities"] == ["text"]][:10],
        "table_only": [q for q in qa_list if q["modalities"] == ["table"]][:10],
        "mixed_text_table": [q for q in qa_list if "table" in q["modalities"] and "text" in q["modalities"]][:10],
        "cross_page": [q for q in qa_list if q["cross_page"] is True][:10],
        "three_plus_evidence": [q for q in qa_list if q["evidence_count"] >= 3][:10],
        "numeric": [q for q in qa_list if "numerical" in q["question_type"]][:10],
        "operational_rule": [q for q in qa_list if any("operation" in str(x).lower() for x in q.get("application_tags", []))][:10],
        "hard_negatives": neg_list[:15]
    }
    
    for stratum, items in samples.items():
        s_file = out_dir / f"{stratum}_sample.jsonl"
        with open(s_file, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        print(f"Saved {len(items)} items to {s_file}")
        
    # Create Markdown summary of review package
    with open(out_dir / "README.md", "w", encoding="utf-8") as f:
        f.write("# VietIrrDocBench — Human Review Stratified Audit Package\n\n")
        f.write("**Status**: PREPARED FOR HUMAN AUDIT (`HUMAN_VALIDATED = false`)\n\n")
        f.write("This directory contains stratified sample slices for expert inspection:\n")
        f.write("- `text_only_sample.jsonl`: Single & multi-paragraph reasoning\n")
        f.write("- `table_only_sample.jsonl`: Direct tabular parameter extraction\n")
        f.write("- `mixed_text_table_sample.jsonl`: Heterogeneous cross-modal retrieval\n")
        f.write("- `cross_page_sample.jsonl`: Multi-page evidence sets testing page-localization\n")
        f.write("- `three_plus_evidence_sample.jsonl`: Higher-order evidence aggregations (3-4 items)\n")
        f.write("- `numeric_sample.jsonl`: Precise hydrological quantities\n")
        f.write("- `operational_rule_sample.jsonl`: Operating curves & directives\n")
        f.write("- `hard_negatives_sample.jsonl`: Minimal counterfactual and provenance-conflict distractors\n")

if __name__ == "__main__":
    main()
