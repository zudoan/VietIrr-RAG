import json
import glob
from pathlib import Path
from datetime import datetime
from collections import Counter

ROOT = Path("d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag")
QA_FINAL = ROOT / "data/qa/v2_4_freeze/pilot_qa_v2_4_final.jsonl"
QA_REJ = ROOT / "data/qa/v2_4_freeze/rejected_qa_v2_4.jsonl"
QA_UNC = ROOT / "data/qa/v2_4_freeze/uncertain_qa_v2_4.jsonl"

NEG_FINAL = ROOT / "data/negatives/v2_4_freeze/negative_sets_v2_4_final.jsonl"
NEG_NONMIN = ROOT / "data/negatives/v2_4_freeze/nonminimal_negatives_v2_4.jsonl"
NEG_REJ = ROOT / "data/negatives/v2_4_freeze/rejected_negatives_v2_4.jsonl"

OUT_STATS = ROOT / "reports/v2_4/dataset_stats.json"

def load_jsonl(path):
    items = []
    if not path.exists():
        return items
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items

def compute_stats():
    print("Computing canonical statistics for V2.4...")
    # Corpus stats
    doc_files = list(glob.glob(str(ROOT / "data/parsed/*.json")))
    total_docs = len(doc_files)
    total_pages = 0
    for df in doc_files:
        with open(df, "r", encoding="utf-8") as f:
            d = json.load(f)
            total_pages += len(d.get("pages", []))

    total_regions = sum(sum(1 for _ in open(f, encoding="utf-8")) for f in glob.glob(str(ROOT / "data/regions/*.jsonl")))
    total_tables = sum(sum(1 for _ in open(f, encoding="utf-8")) for f in glob.glob(str(ROOT / "data/tables/*.jsonl")))

    # QA stats
    qa_final_items = load_jsonl(QA_FINAL)
    qa_rej_items = load_jsonl(QA_REJ)
    qa_unc_items = load_jsonl(QA_UNC)

    q_final_count = len(qa_final_items)
    q_rej_count = len(qa_rej_items)
    q_unc_count = len(qa_unc_items)
    total_input = q_final_count + q_rej_count + q_unc_count

    ec_counts = Counter(len(q.get("gold_evidence", [])) for q in qa_final_items)
    single_c = ec_counts[1]
    two_c = ec_counts[2]
    three_c = ec_counts[3]
    four_plus_c = sum(v for k, v in ec_counts.items() if k >= 4)

    cross_page_c = sum(1 for q in qa_final_items if q.get("cross_page", False))
    same_page_c = q_final_count - cross_page_c

    # Modality
    table_only_c = 0
    text_only_c = 0
    text_table_c = 0
    table_table_c = 0

    for q in qa_final_items:
        r_types = [e.get("region_type") for e in q.get("gold_evidence", [])]
        has_tab = any(t == "table" for t in r_types)
        has_txt = any(t in ("paragraph", "list", "header") for t in r_types)
        tab_count = sum(1 for t in r_types if t == "table")

        if tab_count >= 2:
            table_table_c += 1
        elif has_tab and has_txt:
            text_table_c += 1
        elif has_tab:
            table_only_c += 1
        else:
            text_only_c += 1

    core_long_c = sum(1 for q in qa_final_items if "core_long" in q.get("question_type", []))
    temporal_c = q_final_count - core_long_c

    table_qa_c = sum(1 for q in qa_final_items if any(e.get("region_type") == "table" for e in q.get("gold_evidence", [])))
    ocr_derived_c = sum(1 for q in qa_final_items if q.get("qa_id", "").startswith("QA_IRR_V22_03"))

    # Negatives stats
    neg_final_items = load_jsonl(NEG_FINAL)
    neg_nonmin_items = load_jsonl(NEG_NONMIN)
    neg_rej_items = load_jsonl(NEG_REJ)

    total_negs = len(neg_final_items) + len(neg_nonmin_items) + len(neg_rej_items)

    all_neg_types = Counter()
    for n in neg_final_items + neg_nonmin_items + neg_rej_items:
        all_neg_types[n.get("negative_type", "")] += 1

    final_neg_types = Counter(n.get("negative_type", "") for n in neg_final_items)

    stats = {
        "version": "V2.4_FREEZE",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "corpus": {
            "documents": total_docs,
            "pages": total_pages,
            "regions": total_regions,
            "tables": total_tables
        },
        "qa": {
            "total_input": total_input,
            "qa_final": q_final_count,
            "qa_rejected": q_rej_count,
            "qa_uncertain": q_unc_count,
            "evidence_distribution": {
                "single": single_c,
                "two": two_c,
                "three": three_c,
                "four_plus": four_plus_c
            },
            "spatial_distribution": {
                "cross_page": cross_page_c,
                "same_page": same_page_c
            },
            "modality_distribution": {
                "table_only": table_only_c,
                "text_only": text_only_c,
                "text_table": text_table_c,
                "table_table": table_table_c
            },
            "track_distribution": {
                "core_long_qa": core_long_c,
                "temporal_qa": temporal_c
            },
            "table_qa_count": table_qa_c,
            "ocr_derived_qa_count": ocr_derived_c
        },
        "negatives": {
            "total_input": total_negs,
            "final_core_negatives": len(neg_final_items),
            "nonminimal_negatives": len(neg_nonmin_items),
            "rejected_negatives": len(neg_rej_items),
            "negative_counts_by_type": dict(all_neg_types),
            "valid_minimal_counts": {
                "WRONG_ENTITY": final_neg_types.get("WRONG_ENTITY", 0),
                "WRONG_METRIC": final_neg_types.get("WRONG_METRIC", 0),
                "WRONG_PERIOD": final_neg_types.get("WRONG_PERIOD", 0),
                "WRONG_UNIT": final_neg_types.get("WRONG_UNIT", 0),
                "PROVENANCE_CONFLICT": final_neg_types.get("PROVENANCE_CONFLICT", 0)
            }
        }
    }

    OUT_STATS.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_STATS, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"Saved canonical statistics to {OUT_STATS}")
    return stats

if __name__ == "__main__":
    compute_stats()
