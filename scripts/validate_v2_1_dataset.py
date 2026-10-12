import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
import json
import csv
from pathlib import Path

def load_jsonl(path):
    records = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f, 1):
                if line.strip():
                    try:
                        records.append((line_idx, json.loads(line)))
                    except Exception as e:
                        print(f"Error parsing line {line_idx} in {path}: {e}")
    return records

def validate_dataset():
    print("Running comprehensive V2.1 dataset consistency validator...")
    errors = []
    warnings = []
    
    # 1. Load canonical QA
    qa_records = load_jsonl("data/qa/pilot_qa.jsonl")
    if not qa_records:
        errors.append("pilot_qa.jsonl is empty or missing")
        
    # Load parsed docs, regions, tables to check ID resolution
    parsed_docs = {}
    for p in Path("data/parsed").glob("*.json"):
        with open(p, "r", encoding="utf-8") as fp:
            d = json.load(fp)
            parsed_docs[d["doc_id"]] = d
            
    all_table_ids = set()
    for p in Path("data/tables").glob("*_tables.jsonl"):
        with open(p, "r", encoding="utf-8") as fp:
            for line in fp:
                if line.strip():
                    all_table_ids.add(json.loads(line).get("table_id"))
                    
    all_region_ids = set()
    for p in Path("data/regions").glob("*_regions.jsonl"):
        with open(p, "r", encoding="utf-8") as fp:
            for line in fp:
                if line.strip():
                    all_region_ids.add(json.loads(line).get("region_id"))

    # Track duplicate IDs
    qa_ids = set()
    suspicious_patterns = ["''", '""', "của ''", "của \"\"", "là .", "là ,", "->", "None", "null", "N/A"]

    for line_idx, q in qa_records:
        qid = q.get("qa_id")
        if not qid:
            errors.append(f"Line {line_idx}: Missing qa_id")
        elif qid in qa_ids:
            errors.append(f"Line {line_idx}: Duplicate qa_id {qid}")
        else:
            qa_ids.add(qid)
            
        q_text = q.get("question", "")
        a_text = q.get("answer", "")
        
        # Check empty text
        if not q_text.strip():
            errors.append(f"{qid}: Empty question")
        if not a_text.strip():
            errors.append(f"{qid}: Empty answer")
            
        # Check placeholders
        for pat in suspicious_patterns:
            if pat in q_text:
                errors.append(f"{qid}: Question contains suspicious pattern '{pat}'")
            if pat in a_text:
                errors.append(f"{qid}: Answer contains suspicious pattern '{pat}'")
                
        # Check doc_id
        doc_id = q.get("doc_id")
        if doc_id not in parsed_docs:
            errors.append(f"{qid}: doc_id '{doc_id}' not found in parsed docs")
            
        # Check gold evidence
        ev_list = q.get("gold_evidence", [])
        if not ev_list:
            errors.append(f"{qid}: Empty gold_evidence list")
            
        gold_pages = q.get("gold_pages", [])
        unique_pages = sorted(list(set(gold_pages)))
        
        # Section 26-28: Page Metadata Consistency
        expected_cross = len(unique_pages) > 1
        expected_same = len(unique_pages) == 1
        expected_span = max(unique_pages) - min(unique_pages) if unique_pages else 0
        
        if q.get("cross_page") != expected_cross:
            errors.append(f"{qid}: cross_page flag mismatch: got {q.get('cross_page')}, expected {expected_cross}")
        if q.get("same_page") != expected_same:
            errors.append(f"{qid}: same_page flag mismatch: got {q.get('same_page')}, expected {expected_same}")
        if q.get("gold_page_count") != len(unique_pages):
            errors.append(f"{qid}: gold_page_count mismatch: got {q.get('gold_page_count')}, expected {len(unique_pages)}")
        if q.get("gold_page_span") != expected_span:
            errors.append(f"{qid}: gold_page_span mismatch: got {q.get('gold_page_span')}, expected {expected_span}")
            
        # Evidence resolution
        for ev in ev_list:
            ev_doc = ev.get("doc_id")
            if ev_doc not in parsed_docs:
                errors.append(f"{qid}: Evidence doc_id '{ev_doc}' not found")
            p_num = ev.get("page_number")
            if p_num not in unique_pages:
                errors.append(f"{qid}: Evidence page {p_num} not listed in gold_pages")
            if ev.get("region_type") == "table":
                t_id = ev.get("table_id")
                if t_id and t_id not in all_table_ids:
                    errors.append(f"{qid}: table_id '{t_id}' not resolvable")
            elif ev.get("region_type") in ["paragraph", "list"]:
                r_id = ev.get("region_id")
                if r_id and r_id not in all_region_ids:
                    errors.append(f"{qid}: region_id '{r_id}' not resolvable")
                    
        # Multi-evidence necessity check
        if len(ev_list) > 1:
            nec = q.get("necessity_test_result")
            if not nec or nec.get("pass") is not True:
                errors.append(f"{qid}: Multi-evidence item without passing necessity_test_result")

    # 2. Validate Hard Negatives
    neg_records = load_jsonl("data/negatives/hard_negatives.jsonl")
    neg_ids = set()
    for line_idx, neg in neg_records:
        nid = neg.get("negative_set_id")
        if not nid:
            errors.append(f"Negative line {line_idx}: Missing negative_set_id")
        elif nid in neg_ids:
            errors.append(f"Negative line {line_idx}: Duplicate negative_set_id {nid}")
        else:
            neg_ids.add(nid)
            
        if neg.get("validation_status") != "VALIDATED":
            errors.append(f"{nid}: validation_status is '{neg.get('validation_status')}', expected 'VALIDATED'")
        if neg.get("minimal_corruption_verified") is not True:
            errors.append(f"{nid}: minimal_corruption_verified is False")
        if neg.get("source_grounded") is not True:
            errors.append(f"{nid}: source_grounded is False")
            
        # Check target vs negative signature mismatch
        t_sig = neg.get("target_signature", {})
        n_sig = neg.get("negative_signature", {})
        factor = neg.get("corrupted_factor")
        
        if factor == "ENTITY":
            if t_sig.get("entity") == n_sig.get("entity"):
                errors.append(f"{nid}: Corrupted factor is ENTITY but entity is identical: {t_sig.get('entity')}")
        elif factor == "METRIC":
            if t_sig.get("metric") == n_sig.get("metric"):
                errors.append(f"{nid}: Corrupted factor is METRIC but metric is identical: {t_sig.get('metric')}")
        elif factor == "PERIOD":
            if t_sig.get("period") == n_sig.get("period"):
                errors.append(f"{nid}: Corrupted factor is PERIOD but period is identical: {t_sig.get('period')}")

    # 3. Validate Statistics Consistency
    stats_file = Path("reports/v2_2/dataset_stats.json")
    if not stats_file.exists():
        stats_file = Path("reports/v2_1/dataset_stats.json")
    if not stats_file.exists():
        errors.append("dataset_stats.json does not exist")
    else:
        with open(stats_file, "r", encoding="utf-8") as f:
            stats = json.load(f)
        if stats["qa_dataset"]["total_qa"] != len(qa_records):
            errors.append(f"Stats QA count mismatch: stats says {stats['qa_dataset']['total_qa']}, actual is {len(qa_records)}")
        if stats["hard_negatives"]["total_negative_sets"] != len(neg_records):
            errors.append(f"Stats hard negative count mismatch: stats says {stats['hard_negatives']['total_negative_sets']}, actual is {len(neg_records)}")

    # Summary
    print("\n--- VALIDATION SUMMARY ---")
    print(f"Total QA evaluated: {len(qa_records)}")
    print(f"Total Hard Negatives evaluated: {len(neg_records)}")
    print(f"Total Errors detected: {len(errors)}")
    print(f"Total Warnings detected: {len(warnings)}")
    
    if errors:
        print("\nERRORS ENCOUNTERED:")
        for err in errors[:25]:
            print(f"  [ERROR] {err}")
        if len(errors) > 25:
            print(f"  ... and {len(errors) - 25} more errors.")
        return False
    else:
        print("\n>>> ALL VALIDATION GATES PASSED (100% CLEAN). <<<")
        return True

if __name__ == "__main__":
    success = validate_dataset()
    if not success:
        sys.exit(1)
    sys.exit(0)
