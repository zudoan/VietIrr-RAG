"""Build V3.1 challenge QA only from validated evidence relations."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.structure.semantic_table_parser import clean, fold
from src.validation.necessity_validator_v3_1 import validate_necessity


QUOTAS = {
    "SAME_ENTITY_DIFFERENT_TIME": 74,
    "TABLE_TO_TABLE_COMPARISON": 65,
    "TABLE_TO_TEXT_FORECAST": 35,
    "TABLE_TO_TEXT_EXPLANATION": 46,
    "STATE_TO_RECOMMENDATION": 5,
    "CONDITION_TO_ACTION": 2,
}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def join_vi(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " và " + items[-1]


def table_component(ev: dict, include_period: bool = False) -> str:
    period = f" tại {ev['period']['raw']}" if include_period and ev.get("period", {}).get("raw") else ""
    unit = f" {ev['unit']}" if ev.get("unit") and ev["unit"] not in ev.get("value", "") else ""
    return f"{ev['entity']} có {ev['metric_label']} {ev['value']}{unit}{period}."


def relation_to_qa(relation: dict, qa_id: str) -> dict:
    evidence = relation["evidence"]
    rel_type = relation["relation_type"]
    title = evidence[0]["document_title"]
    if rel_type == "SAME_ENTITY_DIFFERENT_TIME":
        periods = [ev["period"]["raw"] for ev in evidence]
        question = f"Theo chuỗi tài liệu liên quan, {evidence[0]['metric_label']} của {evidence[0]['entity']} tại các kỳ {join_vi(periods)} lần lượt là bao nhiêu?"
        answer = " ".join(table_component(ev, include_period=True) for ev in evidence)
    elif rel_type == "TABLE_TO_TABLE_COMPARISON":
        entities = [ev["entity"] for ev in evidence]
        unit = evidence[0].get("unit")
        unit_phrase = f" (tính theo {unit})" if unit else ""
        question = f"Trong {title}, {evidence[0]['metric_label']}{unit_phrase} của {join_vi(entities)} lần lượt là bao nhiêu?"
        answer = " ".join(table_component(ev) for ev in evidence)
    elif rel_type in {"TABLE_TO_TEXT_FORECAST", "TABLE_TO_TEXT_EXPLANATION"}:
        table = next(ev for ev in evidence if ev["evidence_type"] == "TABLE_CELL")
        text = next(ev for ev in evidence if ev["evidence_type"] == "TEXT_REGION")
        verb = "dự báo điều gì" if rel_type.endswith("FORECAST") else "nhận định điều gì"
        metric_context = clean(table.get("metric_raw") or table["metric_label"])
        question = f"Theo {title}, chỉ tiêu {metric_context} của {table['entity']} là bao nhiêu và báo cáo {verb} về chính đối tượng này?"
        answer = f"{table_component(table)} {clean(text['claim_text'])}"
    else:
        anchor = relation.get("shared_entity") or "đối tượng được nêu"
        prompts = {
            "STATUS_TO_EXPLANATION": f"Báo cáo nêu trạng thái và phần giải thích liên quan đến {anchor} như thế nào?",
            "STATUS_TO_FORECAST": f"Báo cáo nêu trạng thái hiện tại và dự báo tiếp theo đối với {anchor} như thế nào?",
            "STATE_TO_RECOMMENDATION": f"Báo cáo mô tả trạng thái của {anchor} và khuyến nghị hành động gì?",
            "CONDITION_TO_ACTION": f"Điều kiện nào được nêu đối với {anchor} và hành động tương ứng là gì?",
        }
        question = prompts[rel_type]
        answer = " ".join(clean(ev["claim_text"]) for ev in evidence)
    pages = sorted({int(ev["page_number"]) for ev in evidence})
    doc_ids = sorted({ev["doc_id"] for ev in evidence})
    signatures = []
    for ev in evidence:
        signatures.append({
            "entity": {"raw": ev.get("entity") or relation.get("shared_entity"), "canonical": ev.get("entity_canonical"), "confidence": 0.95, "basis": "validated relation entity"},
            "metric": {"raw": ev.get("metric_raw") or ev.get("metric"), "canonical": ev.get("metric") or "NarrativeStatement", "confidence": 0.95, "basis": "validated relation metric/role"},
            "period": ev.get("period"), "unit": {"raw": ev.get("unit"), "normalized": ev.get("unit_normalized"), "confidence": 0.95 if ev.get("unit") else 1.0},
            "role": ev.get("role"), "value_type": "NUMERIC" if ev["evidence_type"] == "TABLE_CELL" else "TEXT",
            "source": {"doc_id": ev["doc_id"], "page_id": ev["page_id"], "evidence_id": ev["evidence_id"]},
        })
    modality = "TABLE_TABLE" if all(ev["evidence_type"] == "TABLE_CELL" for ev in evidence) else ("TEXT_TABLE" if {ev["evidence_type"] for ev in evidence} == {"TABLE_CELL", "TEXT_REGION"} else "MULTI_TEXT")
    qa = {
        "qa_id": qa_id, "status": "CANDIDATE", "review_status": "AUTO_VALIDATED", "human_validated": False,
        "question": question, "answer": answer, "relation_id": relation["relation_id"],
        "relation_type": rel_type, "relation_metadata": {key: relation.get(key) for key in ("shared_entity", "shared_metric", "shared_period", "relation_basis", "relation_confidence", "validation_status")},
        "relation_validation_status": relation["validation_status"], "question_generated_after_relation_pass": True,
        "gold_evidence": evidence, "gold_evidence_ids": [ev["evidence_id"] for ev in evidence],
        "evidence_count": len(evidence), "doc_id": doc_ids[0], "doc_ids": doc_ids,
        "gold_pages": pages, "cross_page": len({(ev["doc_id"], ev["page_id"]) for ev in evidence}) > 1,
        "page_span": (max(pages) - min(pages)) if len(doc_ids) == 1 else None,
        "modality": modality, "qa_type": rel_type,
        "document_type": "core_long" if any(ev["document_type"] == "core_long" for ev in evidence) else "temporal",
        "source_groups": sorted({ev.get("source_group") for ev in evidence}),
        "provenance_signatures": signatures,
    }
    return qa


def select_relations(relations: list[dict]) -> list[dict]:
    selected = []
    evidence_use = Counter()
    doc_use = Counter()
    doc_type_use = Counter()
    by_type = defaultdict(list)
    for relation in relations:
        if relation.get("validation_status") == "PASS":
            by_type[relation["relation_type"]].append(relation)
    for rel_type, quota in QUOTAS.items():
        rows = sorted(by_type.get(rel_type, []), key=lambda row: (
            0 if any(ev["document_type"] == "core_long" for ev in row["evidence"]) else 1,
            -row["relation_confidence"], row["relation_id"],
        ))
        triple_target = 17 if rel_type == "SAME_ENTITY_DIFFERENT_TIME" else (20 if rel_type == "TABLE_TO_TABLE_COMPARISON" else 0)
        triples = [row for row in rows if len(row["evidence_ids"]) >= 3]
        pairs = [row for row in rows if len(row["evidence_ids"]) == 2]
        ordered_rows = triples[:triple_target] + pairs + triples[triple_target:]
        taken = 0
        for row in ordered_rows:
            doc_ids = {ev["doc_id"] for ev in row["evidence"]}
            if any(evidence_use[eid] >= 8 for eid in row["evidence_ids"]):
                continue
            if any(doc_use[doc_id] >= 150 or doc_type_use[(rel_type, doc_id)] >= 40 for doc_id in doc_ids):
                continue
            selected.append(row); taken += 1
            evidence_use.update(row["evidence_ids"])
            doc_use.update(doc_ids)
            doc_type_use.update((rel_type, doc_id) for doc_id in doc_ids)
            if taken >= quota:
                break
    return selected


def main() -> None:
    relations = read_jsonl(ROOT / "data" / "v3_1" / "relations" / "evidence_relations.jsonl")
    selected = select_relations(relations)
    raw_candidates = [relation_to_qa(row, f"V3_1_CHAL_{index:05d}") for index, row in enumerate(selected, 1)]
    candidates, seen_questions = [], set()
    for qa in raw_candidates:
        key = fold(qa["question"])
        if key in seen_questions:
            continue
        seen_questions.add(key)
        candidates.append(qa)
    accepted, rejected, uncertain = [], [], []
    necessity_rows = []
    for qa in candidates:
        necessity = validate_necessity(qa)
        necessity_rows.append(necessity)
        qa["answer_components"] = necessity["components"]
        qa["evidence_support_matrix"] = necessity["support_matrix"]
        qa["necessity_validation"] = necessity
        qa["minimal_gold_set"] = necessity["minimal_gold_set"]
        qa["necessity_status"] = necessity["necessity_status"]
        if necessity["necessity_status"] == "PASS":
            qa["status"] = "PASS"; accepted.append(qa)
        elif necessity["necessity_status"] == "UNCERTAIN":
            qa["status"] = "UNCERTAIN"; uncertain.append(qa)
        else:
            qa["status"] = "REJECT"; rejected.append(qa)
    out = ROOT / "data" / "v3_1" / "qa"
    write_jsonl(out / "challenge_candidates.jsonl", candidates)
    write_jsonl(out / "challenge_qa.jsonl", accepted)
    write_jsonl(out / "rejected_challenge.jsonl", rejected)
    write_jsonl(out / "uncertain_challenge.jsonl", uncertain)
    write_jsonl(ROOT / "data" / "v3_1" / "metadata" / "necessity_validation.jsonl", necessity_rows)
    summary = {
        "relations_selected": len(selected), "pass": len(accepted), "fail": len(rejected), "uncertain": len(uncertain),
        "relation_types": dict(Counter(q["relation_type"] for q in accepted)),
        "modalities": dict(Counter(q["modality"] for q in accepted)),
        "three_plus": sum(q["evidence_count"] >= 3 for q in accepted),
        "cross_page": sum(q["cross_page"] for q in accepted),
        "core_long": sum(q["document_type"] == "core_long" for q in accepted),
    }
    (ROOT / "reports" / "v3_1" / "challenge_build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
