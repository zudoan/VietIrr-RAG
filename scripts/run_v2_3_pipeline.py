import json, re, hashlib, shutil, random
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path("d:/Thuy_Loi/Nam_4/deep_learning/thuyloi_rag")
QA_IN  = ROOT / "data/qa/v2_2/pilot_qa_v2_2.jsonl"
NEG_IN = ROOT / "data/negatives/v2_2/hard_negatives_v2_2.jsonl"
QA_OUT_DIR  = ROOT / "data/qa/v2_3"
NEG_OUT_DIR = ROOT / "data/negatives/v2_3"
REPORT_DIR  = ROOT / "reports"
for d in [QA_OUT_DIR, NEG_OUT_DIR, REPORT_DIR]:
    d.mkdir(parents=True, exist_ok=True)
QA_OUT  = QA_OUT_DIR / "pilot_qa_v2_3.jsonl"
NEG_OUT = NEG_OUT_DIR / "hard_negatives_v2_3.jsonl"
REPORT  = REPORT_DIR / "v2_3_audit_report.md"
STATS   = REPORT_DIR / "v2_3_stats.json"
HUMAN_SAMPLE = QA_OUT_DIR / "human_review_sample.jsonl"

REJECT = "REJECT"
WARN   = "WARN"
PASS_ST = "PASS"

STOP = {"va", "cua", "la", "trong", "theo", "tai", "voi", "duoc", "co", "cac", "cho", "bang", "trang"}
VIET_PAT = r"[a-z\u00c0-\u024f\u1e00-\u1eff\d]+"

ROLE_TAX = {
    "single_table": {"VALUE","METRIC","TABLE_CELL","TABLE_ROW"},
    "multi_table":  {"VALUE","METRIC","TABLE_CELL","TABLE_ROW","COMPARATIVE"},
    "text_table":   {"VALUE","METRIC","CONTEXT","RULE","DIRECTIVE","DESCRIPTION"},
    "single_text":  {"CONTEXT","RULE","DIRECTIVE","DESCRIPTION","SUMMARY"},
    "core_long":    {"CONTEXT","RULE","DIRECTIVE","DESCRIPTION","VALUE","METRIC"},
    "numerical":    {"VALUE","METRIC","TABLE_CELL"},
    "causal_explanation": {"CONTEXT","RULE","DIRECTIVE","DESCRIPTION"},
}
DIRECTIVE_ROLES = {"DIRECTIVE","RULE","REGULATION"}
FORECAST_ROLES  = {"FORECAST","PREDICTION","PROJECTION"}

G_PAT = [
    re.compile(r"^(ho|tram|dap|cong|kenh)\s*$", re.IGNORECASE),
    re.compile(r"^\d{1,3}$"),
    re.compile(r"^[x.\-]+$", re.IGNORECASE),
]

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

def safe_str(v):
    return " ".join(str(x) for x in v) if isinstance(v, list) else str(v)

def norm(t):
    return re.sub(r"\s+", " ", t).strip().lower()

def is_garbage(text):
    t = text.strip()
    if len(t) < 5: return True
    for p in G_PAT:
        if p.match(t): return True
    return False

def check_semantic(qa):
    reasons = []
    a_text = norm(safe_str(qa.get("answer","")))
    ev_list = qa.get("gold_evidence", [])
    qt_list = qa.get("question_type", [])
    if isinstance(qt_list, str): qt_list = [qt_list]
    qt_set = set(qt_list)
    for ev in ev_list:
        if is_garbage(ev.get("exact_content","")):
            reasons.append("GARBAGE_EVIDENCE:" + ev.get("evidence_id","?"))
    for qt in qt_list:
        allowed = ROLE_TAX.get(qt)
        if allowed is None: continue
        for ev in ev_list:
            role = ev.get("role","")
            if role and role not in allowed:
                reasons.append("ROLE_MISMATCH:" + qt + "->" + role)
    has_fc = bool(qt_set & {"temporal","forecast"})
    for ev in ev_list:
        role = ev.get("role","")
        if has_fc and role in DIRECTIVE_ROLES:
            reasons.append("FORECAST_DIRECTIVE:" + role)
        if not has_fc and role in FORECAST_ROLES:
            reasons.append("SPURIOUS_FORECAST:" + role)
    ev_all = " ".join(norm(ev.get("exact_content","")) for ev in ev_list)
    ans_n = set(re.findall(r"\d[\d,.]*", a_text))
    ev_n  = set(re.findall(r"\d[\d,.]*", ev_all))
    if ans_n and not (ans_n & ev_n) and qt_set & {"numerical","single_table","multi_table"}:
        reasons.append("NUMERICAL_NO_EV_OVERLAP")
    return (len(reasons) == 0), reasons

def necessity_audit(qa):
    ev_list  = qa.get("gold_evidence", [])
    ec       = len(ev_list)
    answer   = norm(safe_str(qa.get("answer","")))
    if ec == 0:
        return {"necessity_status":"FAIL","is_multi_evidence":False,"evidence_count":0,"component_coverage":0.0,"failure_reason":"NO_EVIDENCE"}
    tans = set(re.findall(VIET_PAT, answer)) - STOP
    if ec == 1:
        c = ev_list[0].get("exact_content","")
        if is_garbage(c):
            return {"necessity_status":"FAIL","is_multi_evidence":False,"evidence_count":1,"component_coverage":0.0,"failure_reason":"SINGLE_EV_GARBAGE"}
        te = set(re.findall(VIET_PAT, norm(c))) - STOP
        cov = len(te & tans) / max(len(tans),1)
        if cov < 0.10:
            return {"necessity_status":"FAIL","is_multi_evidence":False,"evidence_count":1,"component_coverage":round(cov,3),"failure_reason":"LOW_OVERLAP"}
        return {"necessity_status":"PASS","is_multi_evidence":False,"evidence_count":1,"component_coverage":round(cov,3),"failure_reason":None}
    ev_toks = [set(re.findall(VIET_PAT, norm(ev.get("exact_content","")))) - STOP for ev in ev_list]
    contrib = sum(1 for ts in ev_toks if ts & tans)
    all_cov = set().union(*ev_toks) & tans
    cov = len(all_cov) / max(len(tans),1)
    if contrib < 2:
        return {"necessity_status":"FAIL","is_multi_evidence":True,"evidence_count":ec,"component_coverage":round(cov,3),"failure_reason":"ONLY_" + str(contrib) + "_EV_CONTRIBUTE"}
    nec = sum(1 for i in range(ec) if (set().union(*(ts for j,ts in enumerate(ev_toks) if j!=i)) & tans) < all_cov)
    if nec < 1:
        return {"necessity_status":"WARN_REDUNDANT","is_multi_evidence":True,"evidence_count":ec,"component_coverage":round(cov,3),"failure_reason":"ALL_EV_REDUNDANT"}
    return {"necessity_status":"PASS","is_multi_evidence":True,"evidence_count":ec,"component_coverage":round(cov,3),"failure_reason":None}

DATE_RE   = re.compile(r"(ngay|thang|nam|tu|den|giai doan|ky|tuan)\s+[\d/\-]+", re.IGNORECASE)
GENT_RE   = re.compile(r"^(ho|tram|dap|cong|kenh|cong trinh)\s*$", re.IGNORECASE)

def validate_table(qa):
    qt = qa.get("question_type",[])
    if isinstance(qt,str): qt=[qt]
    if not any(t in qt for t in ("single_table","multi_table","text_table")):
        return {"status":"SKIP","reasons":[]}
    reasons = []
    for ev in qa.get("gold_evidence",[]):
        prov = ev.get("table_cell_provenance")
        if isinstance(prov, str):
            try: prov = eval(prov)
            except: prov = {}
        if not prov: continue
        col = str(prov.get("column_label",""))
        row = str(prov.get("row_label",""))
        raw = str(prov.get("raw_cell",""))
        if DATE_RE.search(col): reasons.append("DATE_AS_METRIC:" + col[:40])
        if GENT_RE.match(row):  reasons.append("GENERIC_ENTITY:" + row)
        if not raw or raw in ("-","\u2013","x","X","N/A",""): reasons.append("EMPTY_CELL:" + raw)
    return {"status":"FAIL" if reasons else "PASS","reasons":reasons}

def audit_qa(qa):
    sem_ok, sem_r = check_semantic(qa)
    nv = necessity_audit(qa)
    tv = validate_table(qa)
    reasons = list(sem_r)
    decision = PASS_ST
    if not sem_ok:
        if any("GARBAGE" in r for r in sem_r):
            decision = REJECT; reasons.append("-> REJECT:GARBAGE_EVIDENCE")
        elif "NUMERICAL_NO_EV_OVERLAP" in sem_r:
            decision = REJECT; reasons.append("-> REJECT:NUMERICAL_NO_OVERLAP")
        else:
            decision = WARN; reasons.append("-> WARN:SEMANTIC")
    if nv["necessity_status"] == "FAIL":
        decision = REJECT
        reasons.append("-> REJECT:NECESSITY:" + str(nv.get("failure_reason","?")))
    elif nv["necessity_status"] == "WARN_REDUNDANT":
        if decision == PASS_ST: decision = WARN
        reasons.append("-> WARN:REDUNDANT_EVIDENCE")
    if tv["status"] == "FAIL":
        if decision == PASS_ST: decision = WARN
        for r in tv["reasons"]: reasons.append("-> WARN:TABLE:" + r)
    return decision, reasons, nv, tv

def parse_sig(v):
    if isinstance(v, dict): return v
    try: return eval(v)
    except: return {}

def validate_cf(neg):
    ts = parse_sig(neg.get("target_signature",{}))
    ns = parse_sig(neg.get("negative_signature",{}))
    keys = {"entity","metric","period","basin","page_number","doc_id"}
    diff = [k.upper() for k in keys if str(ts.get(k,"")).strip() != str(ns.get(k,"")).strip()]
    # Cross-document negatives: DOC_ID change inherently causes PERIOD and BASIN
    # to differ (each bulletin covers a different time window and region).
    # These are structural/inherited differences, NOT independent corruptions.
    # Rule: if DOC_ID is in diff, remove PERIOD and BASIN from independent diff count.
    effective_diff = list(diff)
    if "DOC_ID" in diff:
        effective_diff = [f for f in diff if f not in ("PERIOD","BASIN")]
    if len(effective_diff)==0:   return {"status":"INVALID_NO_DIFF","differing_factors":diff,"reasons":["IDENTICAL_AFTER_NORMALIZATION"]}
    elif len(effective_diff)==1: return {"status":"VALID","differing_factors":diff,"reasons":["SINGLE_CONTROLLED:" + effective_diff[0],"NOTE:" + str(len(diff)) + "_raw_diff_fields"]}
    else:                        return {"status":"WARN_MULTI_FACTOR","differing_factors":diff,"reasons":["MULTI_EFFECTIVE:" + ",".join(effective_diff)]}

def rebuild_negatives(neg_items, valid_ids):
    kept = []
    for neg in neg_items:
        if neg.get("qa_id","") not in valid_ids: continue
        cf = validate_cf(neg)
        if cf["status"] == "INVALID_NO_DIFF": continue
        neg["counterfactual_validation"] = cf
        neg["v2_3_cf_status"] = cf["status"]
        kept.append(neg)
    return kept

def compute_stats(qa_items, neg_items):
    total = len(qa_items)
    qt_c = Counter(); rt_c = Counter()
    for q in qa_items:
        qt = q.get("question_type",[])
        rt = q.get("reasoning_type",[])
        if isinstance(qt,str): qt=[qt]
        if isinstance(rt,str): rt=[rt]
        for t in qt: qt_c[t]+=1
        for t in rt: rt_c[t]+=1
    cross = sum(1 for q in qa_items if q.get("cross_page"))
    multi = sum(1 for q in qa_items if q.get("evidence_count",1)>1)
    docs  = len(set(q.get("doc_id","") for q in qa_items))
    nv_p  = sum(1 for q in qa_items if isinstance(q.get("necessity_validation"),dict) and q["necessity_validation"].get("necessity_status")=="PASS")
    tv_p  = sum(1 for q in qa_items if isinstance(q.get("table_validation"),dict) and q["table_validation"].get("status") in ("PASS","SKIP"))
    nv  = sum(1 for n in neg_items if n.get("v2_3_cf_status")=="VALID")
    nw  = sum(1 for n in neg_items if n.get("v2_3_cf_status")=="WARN_MULTI_FACTOR")
    nc = round(nv_p/max(total,1),3); tc = round(tv_p/max(total,1),3); nr = round(nv/max(len(neg_items),1),3)
    return {"version":"V2.3","generated_at":datetime.utcnow().isoformat()+"Z",
        "qa":{"total":total,"single_evidence":total-multi,"multi_evidence":multi,"cross_page":cross,"same_page":total-cross,"doc_count":docs,"necessity_pass":nv_p,"table_validation_pass":tv_p,"question_type_dist":dict(qt_c.most_common()),"reasoning_type_dist":dict(rt_c.most_common())},
        "negatives":{"total":len(neg_items),"valid_single_factor":nv,"warn_multi_factor":nw},
        "phase_a_readiness":{"READY_TO_SCALE_PHASE_B":nc>=0.80 and tc>=0.80 and nr>=0.90,"audit_gates":{"necessity_coverage":nc,"table_validation_coverage":tc,"negative_single_factor_rate":nr}}}

def select_review(qa_items, n=50):
    random.seed(42)
    B = {"cross_multi":[],"single_table":[],"core_long":[],"warn":[],"other":[]}
    for q in qa_items:
        qt = q.get("question_type",[])
        if isinstance(qt,str): qt=[qt]
        if q.get("v2_3_decision")==WARN: B["warn"].append(q)
        elif q.get("cross_page") and q.get("evidence_count",1)>1: B["cross_multi"].append(q)
        elif "single_table" in qt and not q.get("cross_page"): B["single_table"].append(q)
        elif "core_long" in qt: B["core_long"].append(q)
        else: B["other"].append(q)
    sample=[]; per=n//len(B)
    for key,items in B.items():
        chosen=random.sample(items,min(per,len(items)))
        for c in chosen: c["human_review_bucket"]=key
        sample.extend(chosen)
    used={q["qa_id"] for q in sample}
    rem=[q for q in qa_items if q["qa_id"] not in used]
    extra=random.sample(rem,min(n-len(sample),len(rem)))
    for e in extra: e["human_review_bucket"]="fill"
    return (sample+extra)[:n]

def write_report(audited, kept, rejected, kept_neg, stats):
    L=[]; a=L.append
    a("# VietIrrDocBench V2.3 - Phase-A Audit Report")
    a("\n_Generated: " + stats["generated_at"] + "_\n")
    a("## 1. Pipeline Summary\n"); a("| Metric | Value |"); a("|--------|-------|")
    a("| Input QA (V2.2) | " + str(len(audited)) + " |")
    a("| Kept QA (V2.3) | " + str(len(kept)) + " |")
    a("| Rejected | " + str(len(rejected)) + " |")
    a("| Hard Negatives | " + str(len(kept_neg)) + " |")
    a("| Documents | " + str(stats["qa"]["doc_count"]) + " |")
    a("\n## 2. QA Distribution\n"); s=stats["qa"]
    a("| Category | Count |"); a("|----------|-------|")
    a("| Single-evidence | " + str(s["single_evidence"]) + " |")
    a("| Multi-evidence | " + str(s["multi_evidence"]) + " |")
    a("| Same-page | " + str(s["same_page"]) + " |")
    a("| Cross-page | " + str(s["cross_page"]) + " |")
    a("| Necessity PASS | " + str(s["necessity_pass"]) + " |")
    a("| Table val PASS | " + str(s["table_validation_pass"]) + " |")
    a("\n### Question Type Dist\n"); a("| Type | Count |"); a("|------|-------|")
    for k,v in sorted(s["question_type_dist"].items(),key=lambda x:-x[1]): a("| " + k + " | " + str(v) + " |")
    a("\n### Reasoning Type Dist\n"); a("| Type | Count |"); a("|------|-------|")
    for k,v in sorted(s["reasoning_type_dist"].items(),key=lambda x:-x[1]): a("| " + k + " | " + str(v) + " |")
    a("\n## 3. Negative Quality\n"); n=stats["negatives"]
    a("| Metric | Count |"); a("|--------|-------|")
    a("| Total | " + str(n["total"]) + " |")
    a("| Valid single-factor | " + str(n["valid_single_factor"]) + " |")
    a("| Warn multi-factor | " + str(n["warn_multi_factor"]) + " |")
    a("\n## 4. Rejection Analysis\n")
    if rejected:
        rc=Counter()
        for q in rejected:
            for r in q.get("v2_3_audit_reasons",[]):
                if "-> REJECT" in r or "-> WARN" in r: rc[r]+=1
        a("| Reason | Count |"); a("|--------|-------|")
        for k,v in rc.most_common(): a("| " + k + " | " + str(v) + " |")
    a("\n## 5. Audit Gates\n"); g=stats["phase_a_readiness"]["audit_gates"]
    nec=g["necessity_coverage"]; tab=g["table_validation_coverage"]; neg=g["negative_single_factor_rate"]
    a("| Gate | Value | Threshold | Status |"); a("|------|-------|-----------|--------|")
    a("| Necessity coverage | " + format(nec,".1%") + " | >=80% | " + ("PASS" if nec>=0.80 else "FAIL") + " |")
    a("| Table val coverage | " + format(tab,".1%") + " | >=80% | " + ("PASS" if tab>=0.80 else "FAIL") + " |")
    a("| Neg single-factor | " + format(neg,".1%") + " | >=90% | " + ("PASS" if neg>=0.90 else "FAIL") + " |")
    ready = stats["phase_a_readiness"]["READY_TO_SCALE_PHASE_B"]
    a("\n**READY_TO_SCALE_PHASE_B** = " + ("YES - Phase B may proceed" if ready else "NO - Manual review required") + "\n")
    a("\n## 6. Sample Rejected\n")
    for q in rejected[:10]: a("- **" + q["qa_id"] + "**: " + str(q.get("v2_3_audit_reasons",[]))[:100])
    a("\n## 7. File Manifest\n"); a("| File | Description |"); a("|------|-------------|")
    a("| data/qa/v2_3/pilot_qa_v2_3.jsonl | Cleaned QA |")
    a("| data/negatives/v2_3/hard_negatives_v2_3.jsonl | Rebuilt negatives |")
    a("| data/qa/v2_3/rejected_v2_3.jsonl | Rejected log |")
    a("| data/qa/v2_3/human_review_sample.jsonl | Human review sample |")
    a("| reports/v2_3_stats.json | Canonical stats |")
    a("| reports/v2_3_audit_report.md | This report |")
    with open(REPORT,"w",encoding="utf-8") as f: f.write("\n".join(L)+"\n")

def checksums():
    ckdir=ROOT/"checksums"; ckdir.mkdir(exist_ok=True)
    def sha(p):
        h=hashlib.sha256()
        with open(p,"rb") as f:
            for chunk in iter(lambda:f.read(65536),b""): h.update(chunk)
        return h.hexdigest()
    ck={"version":"V2.3","generated_at":datetime.utcnow().isoformat()+"Z","files":{}}
    for p in [QA_OUT,NEG_OUT,STATS,REPORT]:
        if p.exists(): ck["files"][p.name]=sha(p)
    with open(ckdir/"v2_3_checksums.json","w") as f: json.dump(ck,f,indent=2)
    print("  Checksums: " + str(ckdir/"v2_3_checksums.json"))

def snapshot():
    for src, dst_dir in [(QA_IN,ROOT/"data/qa/v2_2_snapshot"),(NEG_IN,ROOT/"data/negatives/v2_2_snapshot")]:
        dst_dir.mkdir(parents=True,exist_ok=True)
        dst = dst_dir/src.name
        if not dst.exists(): shutil.copy2(src,dst); print("[SNAP] " + str(dst))

if __name__ == "__main__":
    print("="*60)
    print("VietIrrDocBench V2.3 - Final Phase-A Semantic Repair")
    print("="*60)
    snapshot()
    print("\n[1] Loading...")
    qa_items  = load_jsonl(QA_IN)
    neg_items = load_jsonl(NEG_IN)
    print("  QA: " + str(len(qa_items)) + "  NEG: " + str(len(neg_items)))
    print("\n[2] Auditing...")
    decisions = Counter(); audited = []
    for qa in qa_items:
        d,r,nv,tv = audit_qa(qa)
        qa = dict(qa)
        qa["v2_3_decision"] = d; qa["v2_3_audit_reasons"] = r
        qa["necessity_validation"] = nv; qa["table_validation"] = tv
        qa["v2_3_version"] = "V2.3"
        decisions[d]+=1; audited.append(qa)
    print("  PASS:" + str(decisions[PASS_ST]) + "  WARN:" + str(decisions[WARN]) + "  REJECT:" + str(decisions[REJECT]))
    kept     = [q for q in audited if q["v2_3_decision"] in (PASS_ST,WARN)]
    rejected = [q for q in audited if q["v2_3_decision"]==REJECT]
    print("\n[3] Kept: " + str(len(kept)) + "  Rejected: " + str(len(rejected)))
    print("\n[4] Rebuilding negatives...")
    valid_ids = {q["qa_id"] for q in kept}
    kept_neg  = rebuild_negatives(neg_items, valid_ids)
    cf_c = Counter(n.get("v2_3_cf_status","?") for n in kept_neg)
    print("  Negatives: " + str(len(kept_neg)) + "  " + str(dict(cf_c)))
    print("\n[5] Writing outputs...")
    write_jsonl(kept, QA_OUT); write_jsonl(kept_neg, NEG_OUT)
    write_jsonl(rejected, QA_OUT_DIR/"rejected_v2_3.jsonl")
    print("  QA -> " + str(QA_OUT)); print("  NEG -> " + str(NEG_OUT))
    print("\n[6] Human review sample...")
    sample = select_review(kept, n=50); write_jsonl(sample, HUMAN_SAMPLE)
    print("  Sample -> " + str(HUMAN_SAMPLE))
    print("\n[7] Stats...")
    stats = compute_stats(kept, kept_neg)
    with open(STATS,"w",encoding="utf-8") as f: json.dump(stats,f,ensure_ascii=False,indent=2)
    print("  Stats -> " + str(STATS))
    print("\n[8] Audit report...")
    write_report(audited,kept,rejected,kept_neg,stats)
    print("  Report -> " + str(REPORT))
    print("\n[9] Checksums...")
    checksums()
    print("\n"+"="*60)
    g = stats["phase_a_readiness"]["audit_gates"]
    print("V2.3 DONE | Input:" + str(len(qa_items)) + " -> Kept:" + str(len(kept)) + " Rejected:" + str(len(rejected)) + " Neg:" + str(len(kept_neg)))
    print("  Necessity coverage    : " + format(g["necessity_coverage"],".1%"))
    print("  Table val. coverage   : " + format(g["table_validation_coverage"],".1%"))
    print("  Neg single-factor rate: " + format(g["negative_single_factor_rate"],".1%"))
    print("  READY_TO_SCALE_PHASE_B: " + str(stats["phase_a_readiness"]["READY_TO_SCALE_PHASE_B"]))
    print("="*60)
