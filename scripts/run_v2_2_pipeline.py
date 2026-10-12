import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import json
import re
import csv
from pathlib import Path
from collections import Counter, defaultdict

# Import independent validators
from src.validation.evidence_necessity_validator import EvidenceNecessityValidator
from src.validation.table_semantic_validator import TableSemanticValidator
from src.validation.counterfactual_validator import CounterfactualValidator

INVALID_PLACEHOLDERS = {"", "-", "--", "---", "N/A", "n/a", "null", "None", "TT", "STT", "TBNN", "Tổng", "Cộng", "Trung bình"}

def clean_str(s):
    if s is None:
        return ""
    s = str(s).replace('\xa0', ' ').replace('\u200b', '')
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n+', ' ', s)
    return s.strip()

def get_doc_period(doc_meta):
    title = doc_meta.get("title", "")
    m_range = re.search(r'từ\s+(\d{1,2}/\d{1,2})\s+đến\s+(\d{1,2}/\d{1,2}/\d{4})', title, re.I)
    if m_range:
        return f"{m_range.group(1)} - {m_range.group(2)}"
    m_week = re.search(r'(tuần\s*\d+(?:[\s/]+tháng\s*\d+)?\s*(?:năm\s*)?\d{4})', title, re.I)
    if m_week:
        return clean_str(m_week.group(1))
    doc_id = doc_meta.get("doc_id", "")
    m_yr = re.search(r'IRR_CTL_(\d{4})_', doc_id)
    if m_yr:
        return m_yr.group(1)
    return "UNKNOWN_PERIOD"

def load_corpus():
    docs = {}
    for f in Path("data/parsed").glob("*.json"):
        with open(f, "r", encoding="utf-8") as fp:
            d = json.load(fp)
            docs[d["doc_id"]] = d
            
    tables = defaultdict(list)
    for f in Path("data/tables").glob("*_tables.jsonl"):
        doc_id = f.stem.replace("_tables", "")
        with open(f, "r", encoding="utf-8") as fp:
            for line in fp:
                if line.strip():
                    tables[doc_id].append(json.loads(line))
                    
    regions = defaultdict(list)
    for f in Path("data/regions").glob("*_regions.jsonl"):
        doc_id = f.stem.replace("_regions", "")
        with open(f, "r", encoding="utf-8") as fp:
            for line in fp:
                if line.strip():
                    regions[doc_id].append(json.loads(line))
                    
    return docs, tables, regions

def extract_valid_cells(tab, tab_val):
    headers = [clean_str(h) for h in tab.get("header", [])]
    rows = tab.get("rows", [])
    if len(headers) < 2 or len(rows) < 1:
        return []
        
    entity_col = 0
    if len(headers) > 1 and headers[0].lower() in ["tt", "stt", ""]:
        entity_col = 1
        
    start_row = 0
    if len(rows) > 1 and not any(ch.isdigit() for ch in "".join([str(c) for c in rows[0]])):
        start_row = 1
        
    valid_cells = []
    for r_idx in range(start_row, len(rows)):
        row = rows[r_idx]
        if len(row) <= entity_col:
            continue
        ent = clean_str(row[entity_col])
        if tab_val.is_generic_entity(ent):
            if entity_col == 1 and not tab_val.is_generic_entity(clean_str(row[0])):
                ent = clean_str(row[0])
            else:
                continue
                
        for c_idx in range(len(headers)):
            if c_idx == entity_col:
                continue
            col_name = headers[c_idx]
            if tab_val.is_date_like(col_name) or col_name.lower() in ["tt", "stt", ""]:
                continue
            if c_idx >= len(row):
                continue
            val = clean_str(row[c_idx])
            if not val or val in INVALID_PLACEHOLDERS:
                continue
            if not any(ch.isdigit() for ch in val) and val.lower() not in ["đảm bảo", "giảm", "tăng", "bình thường", "xu thế giảm", "xu thế tăng"]:
                continue
                
            valid_cells.append({
                "row_index": r_idx,
                "column_index": c_idx,
                "row_label": ent,
                "column_label": col_name,
                "raw_cell": val,
                "table_id": tab["table_id"],
                "page_number": tab["page_number"]
            })
    return valid_cells

def run_v2_2_pipeline():
    print("=== STARTING VIETIRRDOCBENCH V2.2 PIPELINE ===")
    
    docs, doc_tables, doc_regions = load_corpus()
    nec_val = EvidenceNecessityValidator()
    tab_val = TableSemanticValidator()
    neg_val = CounterfactualValidator()
    
    # -------------------------------------------------------------
    # 1. AUDIT & FILTER V2.1 QA
    # -------------------------------------------------------------
    v2_1_qa_path = Path("data/qa/v2_1_snapshot/pilot_qa_v2_1.jsonl")
    v2_1_qas = []
    with open(v2_1_qa_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                v2_1_qas.append(json.loads(line))
                
    print(f"Auditing {len(v2_1_qas)} QA items from V2.1 snapshot...")
    
    qa_audit_results = []
    kept_qas = []
    repaired_qas = []
    rejected_qas = []
    
    for q in v2_1_qas:
        qid = q["qa_id"]
        ev_count = q["evidence_count"]
        mods = q["modalities"]
        
        # Validator checks
        t_res = tab_val.validate_qa_table_alignment(q)
        n_res = nec_val.validate_necessity(q)
        
        has_arbitrary_4ev = (ev_count >= 4 and q.get("generation_method") == "V21_EVIDENCE_FIRST_QUAD")
        
        # Check forecast mislabeled as directive/action
        has_forecast_mismatch = False
        for ev in q.get("gold_evidence", []):
            c = (ev.get("exact_content") or "").lower()
            r = ev.get("role", "")
            if "dự báo" in c and r in ["OPERATIONAL_DIRECTIVE", "CONTROL_ACTION", "OPERATIONAL_ACTION"]:
                has_forecast_mismatch = True
                
        status = "KEEP"
        reasons = []
        
        if t_res["status"] == "FAIL":
            if any("DATE_AS_METRIC" in r for r in t_res["reasons"]):
                status = "REJECT"
                reasons.append("METRIC_ERROR: DATE_AS_METRIC")
            elif any("GENERIC" in r for r in t_res["reasons"]):
                status = "REJECT"
                reasons.append("ENTITY_ERROR: GENERIC_ENTITY")
            else:
                status = "REPAIRABLE"
                reasons.append("TABLE_ALIGNMENT_ERROR")
                
        if has_arbitrary_4ev:
            status = "REJECT"
            reasons.append("ARBITRARY_EVIDENCE_ATTACHMENT: POSITIONAL_4_EVIDENCE")
            
        elif has_forecast_mismatch:
            if status != "REJECT":
                status = "REPAIRABLE"
                reasons.append("ROLE_MISMATCH: FORECAST_LABELED_AS_DIRECTIVE")
                
        if n_res["necessity_status"] == "FAIL":
            if status != "REJECT":
                if n_res["recommended_action"] in ["DOWNGRADE", "DOWNGRADE_TO_SINGLE"]:
                    status = "REPAIRABLE"
                    reasons.append("UNNECESSARY_EVIDENCE: CAN_DOWNGRADE")
                else:
                    status = "REJECT"
                    reasons.append("UNNECESSARY_EVIDENCE: REDUNDANT")
                    
        # Apply repairs or keep/reject
        if status == "KEEP":
            # Reclassify generic roles to V2.2 explicit roles
            for ev in q["gold_evidence"]:
                if ev.get("role") == "QUANTITATIVE_LOOKUP":
                    ev["role"] = "VALUE"
                elif ev.get("role") == "QUANTITATIVE_STATE":
                    ev["role"] = "VALUE"
                elif ev.get("role") == "OPERATIONAL_EXPLANATION":
                    ev["role"] = "EXPLANATION"
                elif ev.get("role") == "FIRST_MEASUREMENT" or ev.get("role") == "SECOND_MEASUREMENT":
                    ev["role"] = "VALUE"
            q["necessity_validation"] = n_res
            q["table_validation"] = t_res
            kept_qas.append(q)
            
        elif status == "REPAIRABLE":
            repaired_q = json.loads(json.dumps(q))
            # Repair forecast mismatch in evidence roles and text
            for ev in repaired_q["gold_evidence"]:
                c = (ev.get("exact_content") or "").lower()
                r = ev.get("role", "")
                if "dự báo" in c and r in ["OPERATIONAL_DIRECTIVE", "CONTROL_ACTION", "OPERATIONAL_ACTION"]:
                    ev["role"] = "FORECAST"
                    ev["role_basis"] = "EXPLICIT_FORECAST_TEXT"
                elif r == "QUANTITATIVE_LOOKUP" or r == "QUANTITATIVE_STATE" or r in ["FIRST_MEASUREMENT", "SECOND_MEASUREMENT"]:
                    ev["role"] = "VALUE"
                elif r == "OPERATIONAL_EXPLANATION":
                    ev["role"] = "EXPLANATION"
                    
            # Update question phrasing if it specifically asked for directive instead of forecast
            if "nội dung chỉ đạo tại trang" in repaired_q["question"]:
                repaired_q["question"] = repaired_q["question"].replace("nội dung chỉ đạo tại trang", "nội dung dự báo/nhận định tại trang")
                repaired_q["normalized_question_pattern"] = repaired_q["normalized_question_pattern"].replace("nội dung chỉ đạo tại trang", "nội dung dự báo/nhận định tại trang")
            if "yêu cầu điều gì" in repaired_q["question"]:
                repaired_q["question"] = repaired_q["question"].replace("yêu cầu điều gì", "được xác định như thế nào")
                repaired_q["normalized_question_pattern"] = repaired_q["normalized_question_pattern"].replace("yêu cầu điều gì", "được xác định như thế nào")
            if "Chỉ đạo yêu cầu:" in repaired_q["answer"]:
                repaired_q["answer"] = repaired_q["answer"].replace("Chỉ đạo yêu cầu:", "Nội dung dự báo/nhận định:")
                
            repaired_q["necessity_validation"] = nec_val.validate_necessity(repaired_q)
            repaired_q["table_validation"] = tab_val.validate_qa_table_alignment(repaired_q)
            repaired_qas.append(repaired_q)
            
        else:
            rejected_qas.append({"qa_id": qid, "reasons": reasons, "original_qa": q})
            
        qa_audit_results.append({
            "qa_id": qid,
            "status": status,
            "reasons": reasons,
            "evidence_count": ev_count,
            "modalities": mods
        })

    print(f"Audit Summary: Kept = {len(kept_qas)}, Repaired = {len(repaired_qas)}, Rejected = {len(rejected_qas)}")

    # -------------------------------------------------------------
    # 2. GENERATE TARGETED CORE-LONG HIGH-QUALITY QA
    # -------------------------------------------------------------
    print("Generating targeted Core-Long QA from long reports and operational procedures...")
    core_long_docs = [
        "IRR_CTL_2025_dee3c4a4", "IRR_CTL_2026_bd225888", "IRR_CTL_2026_002274e8",
        "IRR_CTL_2025_c049b8bb", "IRR_CTL_2025_b70ea2f6", "IRR_CTL_2025_409e3de1",
        "IRR_CTL_2025_b0541877", "IRR_CTL_2025_fc49f05e"
    ]
    
    new_core_qas = []
    qa_id_counter = len(kept_qas) + len(repaired_qas) + 1
    
    for did in core_long_docs:
        dmeta = docs[did]
        dtitle = clean_str(dmeta["title"])
        t_list = doc_tables.get(did, [])
        r_list = doc_regions.get(did, [])
        basin_name = dmeta["basin"][0] if dmeta.get("basin") else "lưu vực"
        period = get_doc_period(dmeta)
        
        # 1. Generate clean Core-Long Single-Table QA
        for tab in t_list:
            if len([q for q in new_core_qas if q["doc_id"] == did]) >= 6:
                break
            cells = extract_valid_cells(tab, tab_val)
            for c in cells:
                p_num = c["page_number"]
                ent = c["row_label"]
                met = c["column_label"]
                val = c["raw_cell"]
                
                q_text = f"Căn cứ báo cáo dài hạn '{dtitle}', tại bảng trang {p_num}, thông số {met} của đối tượng {ent} được ghi nhận là bao nhiêu?"
                a_text = f"Theo bảng số liệu tại trang {p_num} tài liệu '{dtitle}', thông số {met} của {ent} đạt giá trị {val}."
                norm_pat = "căn cứ báo cáo dài hạn [DOC], tại bảng trang [P], thông số [METRIC] của đối tượng [ENT] được ghi nhận là bao nhiêu?"
                
                ev = {
                    "evidence_id": f"EVD_V22_{qa_id_counter:04d}_1",
                    "doc_id": did,
                    "page_number": p_num,
                    "region_id": f"REG_{did}_P{p_num}_TAB",
                    "region_type": "table",
                    "table_id": c["table_id"],
                    "table_cell_provenance": {
                        "row_index": c["row_index"],
                        "column_index": c["column_index"],
                        "row_label": ent,
                        "column_label": met,
                        "raw_cell": val
                    },
                    "exact_content": f"Bảng trang {p_num} | Đối tượng: {ent} | Chỉ tiêu: {met} | Giá trị: {val}",
                    "role": "VALUE",
                    "role_basis": "TABLE_CELL",
                    "role_confidence": 1.0
                }
                
                qa_rec = {
                    "qa_id": f"QA_IRR_V22_{qa_id_counter:04d}",
                    "question": q_text,
                    "answer": a_text,
                    "doc_id": did,
                    "gold_evidence": [ev],
                    "evidence_count": 1,
                    "gold_pages": [p_num],
                    "gold_page_count": 1,
                    "gold_page_span": 0,
                    "same_page": True,
                    "cross_page": False,
                    "same_section": True,
                    "cross_section": False,
                    "question_type": ["single_table", "numerical", "core_long"],
                    "reasoning_type": ["numerical_lookup"],
                    "modalities": ["table"],
                    "basin": dmeta.get("basin", []),
                    "reservoirs": [ent] if "hồ" in ent.lower() else dmeta.get("reservoirs", []),
                    "entities": [ent],
                    "metrics": [met],
                    "periods": [period],
                    "units": ["theo bảng nguồn"],
                    "research_tags": ["single_evidence", "table_retrieval", "core_long"],
                    "application_tags": ["water_resource_status" if "chất lượng" not in met.lower() else "water_quality"],
                    "application_tag_details": [{"tag": "water_resource_status", "basis": "TABLE_METRIC"}],
                    "normalized_question_pattern": norm_pat,
                    "generation_method": "V22_CORE_LONG_TABLE",
                    "validation_status": "VALIDATED"
                }
                
                if tab_val.validate_qa_table_alignment(qa_rec)["status"] == "PASS":
                    new_core_qas.append(qa_rec)
                    qa_id_counter += 1
                    break
                    
        # 2. Generate Core-Long Two-Evidence (Table + Planning/Regulation Text)
        for tab in t_list:
            if len([q for q in new_core_qas if q["doc_id"] == did]) >= 6:
                break
            cells = extract_valid_cells(tab, tab_val)
            if not cells:
                continue
            c = cells[0]
            t_page = c["page_number"]
            ent = c["row_label"]
            met = c["column_label"]
            val = c["raw_cell"]
            
            # Find planning / operational text region
            for reg in r_list:
                r_text = clean_str(reg.get("normalized_text", ""))
                if len(r_text) > 90 and any(k in r_text.lower() for k in ["kế hoạch", "quy định", "giải pháp", "khuyến cáo", "chỉ đạo", "yêu cầu"]):
                    r_page = reg["page_number"]
                    unique_pages = sorted(list(set([t_page, r_page])))
                    is_cross = len(unique_pages) > 1
                    span = max(unique_pages) - min(unique_pages)
                    
                    m_snip = re.search(r'(?:kế hoạch|quy định|giải pháp|khuyến cáo|chỉ đạo|yêu cầu)[^.]+?\.', r_text, re.I)
                    snip = clean_str(m_snip.group(0)) if m_snip else r_text[:120] + "."
                    
                    q_text = f"Dựa vào báo cáo quy hoạch/điều hành '{dtitle}': (1) Bảng thống kê trang {t_page} công bố {met} của {ent} là bao nhiêu? và (2) Định hướng kế hoạch/giải pháp tương ứng tại trang {r_page} được xác định như thế nào?"
                    a_text = f"(1) Theo bảng trang {t_page}, thông số {met} của {ent} là {val}. (2) Tại trang {r_page}, kế hoạch/giải pháp được xác định: \"{snip}\""
                    norm_pat = "dựa vào báo cáo quy hoạch/điều hành [DOC]: (1) bảng thống kê trang [P1] công bố [METRIC] của [ENT] là bao nhiêu? và (2) định hướng kế hoạch/giải pháp tương ứng tại trang [P2] được xác định như thế nào?"
                    
                    ev1 = {
                        "evidence_id": f"EVD_V22_{qa_id_counter:04d}_1",
                        "doc_id": did,
                        "page_number": t_page,
                        "region_id": f"REG_{did}_P{t_page}_TAB",
                        "region_type": "table",
                        "table_id": c["table_id"],
                        "table_cell_provenance": {
                            "row_index": c["row_index"],
                            "column_index": c["column_index"],
                            "row_label": ent,
                            "column_label": met,
                            "raw_cell": val
                        },
                        "exact_content": f"Bảng trang {t_page} | Đối tượng: {ent} | Chỉ tiêu: {met} | Giá trị: {val}",
                        "role": "VALUE",
                        "role_basis": "TABLE_CELL",
                        "role_confidence": 1.0,
                        "indispensable": True
                    }
                    ev2 = {
                        "evidence_id": f"EVD_V22_{qa_id_counter:04d}_2",
                        "doc_id": did,
                        "page_number": r_page,
                        "region_id": reg["region_id"],
                        "region_type": reg["region_type"],
                        "table_id": None,
                        "exact_content": r_text,
                        "role": "OPERATIONAL_RULE" if "quy định" in r_text.lower() else "RECOMMENDATION",
                        "role_basis": "EXPLICIT_TEXT_SEMANTICS",
                        "role_confidence": 0.95,
                        "indispensable": True
                    }
                    
                    qa_rec = {
                        "qa_id": f"QA_IRR_V22_{qa_id_counter:04d}",
                        "question": q_text,
                        "answer": a_text,
                        "doc_id": did,
                        "gold_evidence": [ev1, ev2],
                        "evidence_count": 2,
                        "gold_pages": unique_pages,
                        "gold_page_count": len(unique_pages),
                        "gold_page_span": span,
                        "same_page": (span == 0),
                        "cross_page": is_cross,
                        "same_section": False,
                        "cross_section": True,
                        "question_type": ["text_table", "core_long", "cross_page" if is_cross else "same_page", "numerical"],
                        "reasoning_type": ["multi_evidence_aggregation", "joint_necessity_tested"],
                        "modalities": ["table", "text"],
                        "basin": dmeta.get("basin", []),
                        "reservoirs": [ent] if "hồ" in ent.lower() else dmeta.get("reservoirs", []),
                        "entities": [ent],
                        "metrics": [met],
                        "periods": [period],
                        "units": ["theo bảng nguồn"],
                        "research_tags": ["multi_evidence", "text_table", "core_long", "necessity_verified"],
                        "application_tags": ["water_supply_planning" if "kế hoạch" in r_text.lower() else "regulation_procedure"],
                        "application_tag_details": [{"tag": "water_supply_planning", "basis": "TEXT_PLANNING"}],
                        "normalized_question_pattern": norm_pat,
                        "generation_method": "V22_CORE_LONG_TEXT_TABLE",
                        "validation_status": "VALIDATED"
                    }
                    
                    n_check = nec_val.validate_necessity(qa_rec)
                    if (tab_val.validate_qa_table_alignment(qa_rec)["status"] == "PASS" and
                        n_check["necessity_status"] == "PASS"):
                        qa_rec["necessity_test_result"] = {
                            "tested": True,
                            "pass": True,
                            "removal_e1_impact": "UNANSWERABLE_PART_1",
                            "removal_e2_impact": "UNANSWERABLE_PART_2"
                        }
                        qa_rec["necessity_validation"] = n_check
                        new_core_qas.append(qa_rec)
                        qa_id_counter += 1
                        break

    print(f"Generated {len(new_core_qas)} new verified Core-Long QA items.")

    # Combine all accepted QAs
    final_accepted_qas = kept_qas + repaired_qas + new_core_qas
    print(f"Total Final Accepted V2.2 QA items: {len(final_accepted_qas)}")

    # -------------------------------------------------------------
    # 3. REVALIDATE & REPAIR HARD NEGATIVES
    # -------------------------------------------------------------
    print("Revalidating hard negatives with CounterfactualValidator...")
    v2_1_neg_path = Path("data/negatives/v2_1_snapshot/hard_negatives_v2_1.jsonl")
    v2_1_negs = []
    with open(v2_1_neg_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                v2_1_negs.append(json.loads(line))
                
    valid_minimal_negs = []
    non_minimal_negs = []
    invalid_negs = []
    
    for n in v2_1_negs:
        res = neg_val.validate_negative(n)
        n["counterfactual_validation"] = res
        if res["status"] == "VALID":
            valid_minimal_negs.append(n)
        elif res["status"] == "NON_MINIMAL":
            non_minimal_negs.append(n)
        else:
            invalid_negs.append(n)
            
    print(f"Pre-repair Negatives: VALID minimal = {len(valid_minimal_negs)}, NON_MINIMAL = {len(non_minimal_negs)}, INVALID = {len(invalid_negs)}")

    # Generate genuinely minimal WRONG_PERIOD negatives (same entity, same metric, strictly different verified period)
    print("Generating strictly minimal WRONG_PERIOD negatives...")
    temporal_bulletins = [did for did in docs if "IRR_CTL_2019" in did]
    
    # Extract catalog of (entity, metric, period, value, cell)
    candidate_period_cells = defaultdict(list)
    for did in temporal_bulletins:
        dmeta = docs[did]
        d_per = get_doc_period(dmeta)
        for tab in doc_tables.get(did, []):
            cells = extract_valid_cells(tab, tab_val)
            for c in cells:
                key = (c["row_label"].lower(), c["column_label"].lower())
                candidate_period_cells[key].append({
                    "doc_id": did,
                    "period": d_per,
                    "cell": c
                })
                
    new_minimal_wrong_period = []
    neg_id_counter = len(valid_minimal_negs) + 1
    
    for (ent_key, met_key), cell_instances in candidate_period_cells.items():
        if len(cell_instances) >= 2:
            # Find instances with differing periods
            inst1 = cell_instances[0]
            diff_instances = [inst for inst in cell_instances if inst["period"] != inst1["period"]]
            if diff_instances:
                inst2 = diff_instances[0]
                neg_rec = {
                    "negative_set_id": f"NEG_V22_{neg_id_counter:05d}",
                    "qa_id": f"QA_V22_PERIOD_PAIR_{neg_id_counter:04d}",
                    "evidence_ids": [f"NEG_EVD_{neg_id_counter}_1"],
                    "negative_type": "WRONG_PERIOD",
                    "corrupted_factor": "PERIOD",
                    "target_signature": {
                        "doc_id": inst1["doc_id"],
                        "entity": inst1["cell"]["row_label"],
                        "metric": inst1["cell"]["column_label"],
                        "period": inst1["period"]
                    },
                    "negative_signature": {
                        "doc_id": inst2["doc_id"],
                        "entity": inst2["cell"]["row_label"],
                        "metric": inst2["cell"]["column_label"],
                        "period": inst2["period"]
                    },
                    "negative_evidence": [{
                        "doc_id": inst2["doc_id"],
                        "page_number": inst2["cell"]["page_number"],
                        "table_id": inst2["cell"]["table_id"],
                        "exact_content": f"Bảng trang {inst2['cell']['page_number']} | Đối tượng: {inst2['cell']['row_label']} | Chỉ tiêu: {inst2['cell']['column_label']} | Giá trị: {inst2['cell']['raw_cell']}",
                        "source_grounded": True
                    }],
                    "source_grounded": True,
                    "minimal_corruption_verified": True,
                    "validation_status": "VALIDATED"
                }
                v_res = neg_val.validate_negative(neg_rec)
                if v_res["status"] == "VALID":
                    new_minimal_wrong_period.append(neg_rec)
                    neg_id_counter += 1
                    if len(new_minimal_wrong_period) >= 25:
                        break

    print(f"Generated {len(new_minimal_wrong_period)} strictly minimal WRONG_PERIOD sets.")
    
    # Combined valid minimal hard negatives
    final_valid_negatives = valid_minimal_negs + new_minimal_wrong_period
    print(f"Total Valid Minimal Hard Negative Sets: {len(final_valid_negatives)}")

    # -------------------------------------------------------------
    # 4. SAVE CANONICAL ARTIFACTS
    # -------------------------------------------------------------
    qa_out_dir = Path("data/qa")
    qa_v2_2_dir = Path("data/qa/v2_2")
    qa_v2_2_dir.mkdir(parents=True, exist_ok=True)
    
    with open(qa_v2_2_dir / "pilot_qa_v2_2.jsonl", "w", encoding="utf-8") as f:
        for q in final_accepted_qas:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
            
    with open(qa_out_dir / "pilot_qa.jsonl", "w", encoding="utf-8") as f:
        for q in final_accepted_qas:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
            
    # Page localization gold
    with open(qa_out_dir / "page_localization_gold.jsonl", "w", encoding="utf-8") as f:
        for q in final_accepted_qas:
            entry = {
                "qa_id": q["qa_id"],
                "doc_id": q["doc_id"],
                "gold_pages": q["gold_pages"],
                "gold_page_count": q["gold_page_count"],
                "gold_page_span": q["gold_page_span"],
                "same_page": q["same_page"],
                "cross_page": q["cross_page"],
                "same_section": q["same_section"],
                "cross_section": q["cross_section"]
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Hard negatives
    neg_out_dir = Path("data/negatives")
    neg_v2_2_dir = Path("data/negatives/v2_2")
    neg_v2_2_dir.mkdir(parents=True, exist_ok=True)
    
    with open(neg_v2_2_dir / "hard_negatives_v2_2.jsonl", "w", encoding="utf-8") as f:
        for n in final_valid_negatives:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")
            
    with open(neg_out_dir / "hard_negatives.jsonl", "w", encoding="utf-8") as f:
        for n in final_valid_negatives:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")

    return final_accepted_qas, final_valid_negatives, qa_audit_results, rejected_qas, repaired_qas, kept_qas, new_core_qas

if __name__ == "__main__":
    run_v2_2_pipeline()
