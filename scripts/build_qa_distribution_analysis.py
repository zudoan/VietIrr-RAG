"""Analyze the frozen Q&A corpus without opening sealed Candidate Test content."""

from __future__ import annotations

import csv
import itertools
import json
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "v3_2_final_semantic"
REPORTS = ROOT / "reports"
OUT = REPORTS / "qa_inventory"
INVENTORY = REPORTS / "document_inventory" / "ALL_PDF_DOCUMENT_INVENTORY.csv"


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def plain(value: Any) -> str:
    text = "" if value is None else str(value)
    text = "".join(
        char for char in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"\s+", " ", text).strip()


def join_values(values: Iterable[Any]) -> str:
    return "; ".join(str(value) for value in values if value not in (None, ""))


def effective_modality(qa: dict[str, Any]) -> str:
    raw = str(qa.get("modality") or "").upper()
    if raw == "MULTI_TEXT":
        return "TEXT_ONLY"
    if raw:
        return raw
    qa_type = str(qa.get("qa_type") or "").upper()
    if qa_type in {"TEXT_ONLY", "TABLE_ONLY"}:
        return qa_type
    if "TABLE_TO_TABLE" in qa_type:
        return "TABLE_TABLE"
    if "TABLE_TO_TEXT" in qa_type or "STATE_TO" in qa_type:
        return "TEXT_TABLE"
    return "UNKNOWN"


def qa_class(qa: dict[str, Any]) -> str:
    return "CORE" if str(qa.get("qa_type") or "").upper() in {"TEXT_ONLY", "TABLE_ONLY"} else "CHALLENGE"


def primary_topic(qa: dict[str, Any]) -> str:
    candidates = [
        (((qa.get("validation_v3_2_final") or {}).get("topic_alignment") or {}).get("primary_topic")),
        (((qa.get("validation_v3_2") or {}).get("topic_alignment") or {}).get("primary_topic")),
        ((qa.get("contextual_topic_alignment_final") or {}).get("primary_topic")),
    ]
    for value in candidates:
        if value:
            return str(value)
    return "UNCLASSIFIED"


def metric_set(qa: dict[str, Any]) -> str:
    metrics = sorted({str(item.get("metric")) for item in qa.get("gold_evidence", []) if item.get("metric")})
    return " + ".join(metrics) if metrics else "NO_STRUCTURED_METRIC"


def linguistic_intent(qa: dict[str, Any]) -> str:
    question = plain(qa.get("question"))
    qa_type = str(qa.get("qa_type") or "")
    if qa_type not in {"TEXT_ONLY", "TABLE_ONLY"}:
        return "RELATIONAL_OR_MULTI_EVIDENCE"
    if any(term in question for term in ("khuyen nghi", "can lam gi", "giai phap", "hanh dong")):
        return "ACTION_OR_RECOMMENDATION"
    if any(term in question for term in ("tai sao", "vi sao", "nguyen nhan")):
        return "EXPLANATION_OR_CAUSE"
    if any(term in question for term in ("so sanh", "chenh lech", "tang hay giam", "cao hon", "thap hon")):
        return "COMPARISON"
    if any(term in question for term in ("bao nhieu", "la bao nhieu", "gia tri", "muc nao")):
        return "QUANTITATIVE_LOOKUP"
    if any(term in question for term in ("nhu the nao", "dien bien", "tinh hinh", "nhan dinh")):
        return "DESCRIPTIVE_STATUS"
    if any(term in question for term in ("nhung gi", "gom", "liet ke", "nao")):
        return "LIST_OR_SELECTION"
    return "DIRECT_FACT_LOOKUP"


def template(qa: dict[str, Any]) -> str:
    value = plain(qa.get("question"))
    entities = sorted(
        {plain(item.get("entity")) for item in qa.get("gold_evidence", []) if item.get("entity")},
        key=len,
        reverse=True,
    )
    labels = sorted(
        {
            plain(item.get(key))
            for item in qa.get("gold_evidence", [])
            for key in ("metric_label", "metric_raw")
            if item.get(key)
        },
        key=len,
        reverse=True,
    )
    for entity in entities:
        if len(entity) >= 3:
            value = value.replace(entity, "<entity>")
    for label in labels:
        if len(label) >= 3:
            value = value.replace(label, "<metric>")
    value = re.sub(r"\b\d+(?:[.,/]\d+)*(?:\s*[-–]\s*\d+(?:[.,/]\d+)*)?\b", "<num>", value)
    return re.sub(r"\s+", " ", value).strip()


def token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", plain(text)))


def gini(values: list[int]) -> float:
    if not values or sum(values) == 0:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    weighted = sum(index * value for index, value in enumerate(ordered, start=1))
    return (2 * weighted) / (n * sum(ordered)) - (n + 1) / n


def concentration(values: list[int]) -> dict[str, float]:
    total = sum(values)
    shares = [value / total for value in values if value > 0] if total else []
    hhi = sum(share * share for share in shares)
    entropy = -sum(share * math.log(share) for share in shares)
    normalized_entropy = entropy / math.log(len(values)) if len(values) > 1 else 0.0
    ordered = sorted(values, reverse=True)
    return {
        "gini_including_zero_qa_documents": round(gini(values), 6),
        "hhi": round(hhi, 6),
        "normalized_entropy": round(normalized_entropy, 6),
        "top_1_share": round(sum(ordered[:1]) / total, 6) if total else 0.0,
        "top_5_share": round(sum(ordered[:5]) / total, 6) if total else 0.0,
        "top_10_share": round(sum(ordered[:10]) / total, 6) if total else 0.0,
    }


def pct(count: int, total: int) -> str:
    return f"{count / total * 100:.1f}%" if total else "0.0%"


def md(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def counter_text(counter: Counter[str], limit: int = 5) -> str:
    return "; ".join(f"{key}:{count}" for key, count in counter.most_common(limit))


def main() -> None:
    with INVENTORY.open(encoding="utf-8-sig", newline="") as handle:
        document_rows = list(csv.DictReader(handle))
    documents = {row["doc_id"]: row for row in document_rows if row["doc_id"]}
    accepted_documents = [row for row in document_rows if row["corpus_status"] == "ACCEPT"]

    qa_rows: list[dict[str, Any]] = []
    for split in ("train", "dev"):
        for qa in read_jsonl(DATASET / f"{split}.jsonl"):
            qa["_analysis_split"] = split
            qa_rows.append(qa)

    split_manifest = json.loads((DATASET / "metadata" / "splits.json").read_text(encoding="utf-8-sig"))
    dataset_stats = json.loads((REPORTS / "v3_2_final_semantic" / "dataset_stats.json").read_text(encoding="utf-8-sig"))

    analysis_records: list[dict[str, Any]] = []
    doc_to_qas: dict[str, set[str]] = defaultdict(set)
    domain_to_qas: dict[str, set[str]] = defaultdict(set)
    doc_split: dict[str, Counter[str]] = defaultdict(Counter)
    doc_class: dict[str, Counter[str]] = defaultdict(Counter)
    doc_modality: dict[str, Counter[str]] = defaultdict(Counter)
    doc_qa_type: dict[str, Counter[str]] = defaultdict(Counter)
    doc_topic: dict[str, Counter[str]] = defaultdict(Counter)

    for qa in qa_rows:
        gold_docs = list(dict.fromkeys(str(item) for item in qa.get("gold_doc_ids", []) if item))
        if not gold_docs and qa.get("doc_id"):
            gold_docs = [str(qa["doc_id"])]
        doc_meta = [documents.get(doc_id, {}) for doc_id in gold_docs]
        categories = sorted({row.get("content_category_review", "UNKNOWN") for row in doc_meta})
        agencies = sorted({row.get("source_agency", "UNKNOWN") for row in doc_meta})
        titles = [row.get("title", "UNKNOWN") for row in doc_meta]
        topic = primary_topic(qa)
        modality = effective_modality(qa)
        qclass = qa_class(qa)
        split = qa["_analysis_split"]
        qid = str(qa.get("qa_id"))
        for doc_id in gold_docs:
            doc_to_qas[doc_id].add(qid)
            doc_split[doc_id][split] += 1
            doc_class[doc_id][qclass] += 1
            doc_modality[doc_id][modality] += 1
            doc_qa_type[doc_id][str(qa.get("qa_type") or "UNKNOWN")] += 1
            doc_topic[doc_id][topic] += 1
        for category in categories:
            domain_to_qas[category].add(qid)

        analysis_records.append({
            "qa_id": qid,
            "split": split,
            "qa_class": qclass,
            "qa_type": qa.get("qa_type"),
            "relation_type": qa.get("relation_type"),
            "effective_modality": modality,
            "location_type": qa.get("location_type"),
            "primary_topic": topic,
            "metric_set": metric_set(qa),
            "linguistic_intent_heuristic": linguistic_intent(qa),
            "question_template_heuristic": template(qa),
            "question": qa.get("question"),
            "answer": qa.get("answer"),
            "answer_component_count": len(qa.get("answer_components") or []),
            "answer_evidence_count": qa.get("answer_evidence_count"),
            "retrieval_evidence_count": qa.get("retrieval_evidence_count"),
            "gold_doc_count": len(gold_docs),
            "gold_doc_ids": join_values(gold_docs),
            "document_titles": join_values(titles),
            "content_domains": join_values(categories),
            "source_agencies": join_values(agencies),
            "human_validated": qa.get("human_validated"),
            "review_status": qa.get("review_status"),
        })

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "QA_ANALYSIS_RECORDS.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(analysis_records[0]))
        writer.writeheader()
        writer.writerows(analysis_records)

    per_document: list[dict[str, Any]] = []
    for doc in accepted_documents:
        doc_id = doc["doc_id"]
        per_document.append({
            "doc_id": doc_id,
            "title": doc["title"],
            "content_domain": doc["content_category_review"],
            "source_agency": doc["source_agency"],
            "track": doc["track"],
            "corpus_pages": doc["page_count_manifest"],
            "corpus_tables": doc["tables"],
            "semantic_good_tables": doc["tables_semantic_good"],
            "train_qa_participation": doc_split[doc_id]["train"],
            "dev_qa_participation": doc_split[doc_id]["dev"],
            "total_qa_participation": len(doc_to_qas[doc_id]),
            "core_challenge": counter_text(doc_class[doc_id]),
            "modalities": counter_text(doc_modality[doc_id]),
            "qa_types": counter_text(doc_qa_type[doc_id]),
            "topics": counter_text(doc_topic[doc_id]),
            "has_any_qa": bool(doc_to_qas[doc_id]),
            "source_url": doc["source_url"],
        })
    per_document.sort(key=lambda row: (-int(row["total_qa_participation"]), row["doc_id"]))
    with (OUT / "QA_PER_DOCUMENT.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_document[0]))
        writer.writeheader()
        writer.writerows(per_document)

    category_documents: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for doc in accepted_documents:
        category_documents[doc["content_category_review"]].append(doc)
    per_domain: list[dict[str, Any]] = []
    for category, docs in category_documents.items():
        doc_ids = {row["doc_id"] for row in docs}
        active = {doc_id for doc_id in doc_ids if doc_to_qas[doc_id]}
        qids = domain_to_qas[category]
        records = [record for record in analysis_records if record["qa_id"] in qids]
        per_domain.append({
            "content_domain": category,
            "corpus_documents": len(docs),
            "documents_with_qa": len(active),
            "document_coverage_percent": round(len(active) / len(docs) * 100, 2),
            "unique_qa_participation": len(qids),
            "qa_share_of_train_dev_percent": round(len(qids) / len(analysis_records) * 100, 2),
            "train_qa": sum(record["split"] == "train" for record in records),
            "dev_qa": sum(record["split"] == "dev" for record in records),
            "topics": counter_text(Counter(record["primary_topic"] for record in records)),
            "modalities": counter_text(Counter(record["effective_modality"] for record in records)),
            "source_agencies": counter_text(Counter(row["source_agency"] for row in docs)),
        })
    per_domain.sort(key=lambda row: (-int(row["unique_qa_participation"]), row["content_domain"]))
    with (OUT / "QA_PER_DOMAIN.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_domain[0]))
        writer.writeheader()
        writer.writerows(per_domain)

    per_topic: list[dict[str, Any]] = []
    for topic, topic_records_iter in itertools.groupby(
        sorted(analysis_records, key=lambda row: row["primary_topic"]),
        key=lambda row: row["primary_topic"],
    ):
        topic_records = list(topic_records_iter)
        topic_docs = Counter(
            doc_id.strip()
            for record in topic_records
            for doc_id in record["gold_doc_ids"].split(";")
            if doc_id.strip()
        )
        per_topic.append({
            "topic": topic,
            "train_qa": sum(record["split"] == "train" for record in topic_records),
            "dev_qa": sum(record["split"] == "dev" for record in topic_records),
            "total_qa": len(topic_records),
            "share_percent": round(len(topic_records) / len(analysis_records) * 100, 2),
            "qa_types": counter_text(Counter(record["qa_type"] for record in topic_records)),
            "modalities": counter_text(Counter(record["effective_modality"] for record in topic_records)),
            "linguistic_intents": counter_text(Counter(record["linguistic_intent_heuristic"] for record in topic_records)),
            "content_domains": counter_text(Counter(
                domain.strip()
                for record in topic_records
                for domain in record["content_domains"].split(";")
                if domain.strip()
            )),
            "top_documents": counter_text(topic_docs),
        })
    per_topic.sort(key=lambda row: (-int(row["total_qa"]), row["topic"]))
    with (OUT / "QA_PER_TOPIC.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_topic[0]))
        writer.writeheader()
        writer.writerows(per_topic)

    # Near-duplicate scan is limited to readable TRAIN+DEV questions.
    duplicate_pairs: list[dict[str, Any]] = []
    tokenized = [(record, token_set(record["question"])) for record in analysis_records]
    for index, (left, left_tokens) in enumerate(tokenized):
        for right, right_tokens in tokenized[index + 1:]:
            union = left_tokens | right_tokens
            score = len(left_tokens & right_tokens) / len(union) if union else 1.0
            if score >= 0.80:
                duplicate_pairs.append({
                    "qa_id_a": left["qa_id"],
                    "split_a": left["split"],
                    "question_a": left["question"],
                    "qa_id_b": right["qa_id"],
                    "split_b": right["split"],
                    "question_b": right["question"],
                    "token_jaccard": round(score, 6),
                    "cross_split": left["split"] != right["split"],
                })
    duplicate_pairs.sort(key=lambda row: -float(row["token_jaccard"]))
    with (OUT / "QA_NEAR_DUPLICATES.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = list(duplicate_pairs[0]) if duplicate_pairs else [
            "qa_id_a", "split_a", "question_a", "qa_id_b", "split_b", "question_b", "token_jaccard", "cross_split"
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(duplicate_pairs)

    counts = [int(row["total_qa_participation"]) for row in per_document]
    active_counts = [value for value in counts if value]
    topic_counts = Counter(record["primary_topic"] for record in analysis_records)
    type_counts = Counter(record["qa_type"] for record in analysis_records)
    modality_counts = Counter(record["effective_modality"] for record in analysis_records)
    location_counts = Counter(record["location_type"] for record in analysis_records)
    intent_counts = Counter(record["linguistic_intent_heuristic"] for record in analysis_records)
    metric_counts = Counter(record["metric_set"] for record in analysis_records)
    template_counts = Counter(record["question_template_heuristic"] for record in analysis_records)
    normalized_question_counts = Counter(plain(record["question"]) for record in analysis_records)
    exact_duplicate_pairs = sum(
        count * (count - 1) // 2 for count in normalized_question_counts.values() if count > 1
    )
    split_counts = Counter(record["split"] for record in analysis_records)
    class_counts = Counter(record["qa_class"] for record in analysis_records)

    summary: dict[str, Any] = {
        "scope": {
            "train_dev_content_read": True,
            "candidate_test_content_read": False,
            "candidate_test_statistics_source": "pre-existing metadata/splits.json and reports/v3_2_final_semantic/dataset_stats.json",
            "train_dev_qa": len(analysis_records),
            "full_frozen_qa_from_published_stats": dataset_stats["qa"]["total"],
        },
        "splits_readable": dict(split_counts),
        "qa_class_readable": dict(class_counts),
        "topics_readable": dict(topic_counts.most_common()),
        "qa_types_readable": dict(type_counts.most_common()),
        "modalities_readable": dict(modality_counts.most_common()),
        "locations_readable": dict(location_counts.most_common()),
        "linguistic_intents_heuristic": dict(intent_counts.most_common()),
        "structured_metric_sets": dict(metric_counts.most_common()),
        "document_distribution": {
            "accepted_corpus_documents": len(accepted_documents),
            "documents_with_any_train_dev_qa": len(active_counts),
            "documents_without_train_dev_qa": len(counts) - len(active_counts),
            "coverage_percent": round(len(active_counts) / len(counts) * 100, 2),
            "participation_total": sum(counts),
            "mean_per_all_accepted_documents": round(statistics.mean(counts), 4),
            "median_per_all_accepted_documents": statistics.median(counts),
            "mean_per_active_document": round(statistics.mean(active_counts), 4),
            "median_per_active_document": statistics.median(active_counts),
            "max_per_document": max(counts),
            **concentration(counts),
        },
        "near_duplicates": {
            "method": "accent-insensitive unique-token Jaccard; high counts can reflect shared templates rather than shared answers",
            "exact_normalized_duplicate_pairs": exact_duplicate_pairs,
            "pairs_jaccard_ge_0_80": len(duplicate_pairs),
            "pairs_jaccard_ge_0_90": sum(float(row["token_jaccard"]) >= 0.90 for row in duplicate_pairs),
            "cross_split_pairs_jaccard_ge_0_80": sum(row["cross_split"] for row in duplicate_pairs),
            "cross_split_pairs_jaccard_ge_0_90": sum(
                row["cross_split"] and float(row["token_jaccard"]) >= 0.90 for row in duplicate_pairs
            ),
        },
        "template_concentration": {
            "unique_heuristic_templates": len(template_counts),
            "top_template_count": template_counts.most_common(1)[0][1],
            "top_10_template_share": round(sum(count for _, count in template_counts.most_common(10)) / len(analysis_records), 6),
        },
        "human_validated_train_dev": sum(record["human_validated"] is True for record in analysis_records),
        "candidate_test_aggregate_only": split_manifest["per_split"]["candidate_test"],
        "candidate_test_family_concentration": split_manifest["candidate_test_family_concentration"],
    }
    (OUT / "QA_ANALYSIS_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    full_splits = split_manifest["per_split"]
    lines = [
        "# Phân tích phân bố và nhóm câu hỏi VietIrrDocBench V3.2",
        "",
        "## Phạm vi và nguyên tắc",
        "",
        "- Phân tích nội dung trực tiếp **343 TRAIN + 93 DEV = 436 Q&A**.",
        "- Không mở nội dung **109 Candidate Test** đang niêm phong; chỉ dùng aggregate đã có trong manifest/report.",
        f"- Tổng frozen benchmark theo thống kê công bố: **{dataset_stats['qa']['total']} Q&A**.",
        f"- Human-validated trong TRAIN+DEV: **{summary['human_validated_train_dev']}/{len(analysis_records)}**.",
        "- Nhóm lĩnh vực dưới đây được nối với document inventory; đó là taxonomy audit, không phải nhãn gold do người gán.",
        "",
        "## 1. Phân bố split và độ khó",
        "",
        "| Split | Tổng | Core | Challenge | Core share | Challenge share |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for split in ("train", "dev", "candidate_test"):
        item = full_splits[split]
        lines.append(
            f"| {split} | {item['total']} | {item['core']} | {item['challenge']} | "
            f"{pct(item['core'], item['total'])} | {pct(item['challenge'], item['total'])} |"
        )
    lines.extend([
        "",
        "Candidate Test là một stress-test khác phân phối: challenge, cross-document và table-table cao hơn rất mạnh so với TRAIN/DEV.",
        "",
        "| Split | Same page | Cross-page cùng tài liệu | Cross-document | Retrieval multi |",
        "|---|---:|---:|---:|---:|",
    ])
    for split in ("train", "dev", "candidate_test"):
        item = full_splits[split]
        lines.append(
            f"| {split} | {item['same_page']} | {item['same_document_cross_page']} | "
            f"{item['cross_document']} | {item['retrieval_multi']} |"
        )

    lines.extend([
        "",
        "## 2. Nhóm câu hỏi TRAIN+DEV",
        "",
        "### Theo loại QA chính thức",
        "",
        "| QA type | Số câu | Tỷ lệ |",
        "|---|---:|---:|",
    ])
    for key, count in type_counts.most_common():
        lines.append(f"| {md(key)} | {count} | {pct(count, len(analysis_records))} |")
    lines.extend([
        "",
        "### Theo modality hiệu dụng",
        "",
        "| Modality | Số câu | Tỷ lệ |",
        "|---|---:|---:|",
    ])
    for key, count in modality_counts.most_common():
        lines.append(f"| {md(key)} | {count} | {pct(count, len(analysis_records))} |")
    lines.extend([
        "",
        "### Theo chủ đề/lĩnh vực câu hỏi",
        "",
        "| Topic | TRAIN | DEV | Tổng | Tỷ lệ |",
        "|---|---:|---:|---:|---:|",
    ])
    for row in per_topic:
        lines.append(
            f"| {md(row['topic'])} | {row['train_qa']} | {row['dev_qa']} | {row['total_qa']} | {row['share_percent']}% |"
        )

    lines.extend([
        "",
        "### Theo dạng hỏi ngôn ngữ (heuristic)",
        "",
        "| Dạng hỏi | Số câu | Tỷ lệ |",
        "|---|---:|---:|",
    ])
    for key, count in intent_counts.most_common():
        lines.append(f"| {md(key)} | {count} | {pct(count, len(analysis_records))} |")

    doc_dist = summary["document_distribution"]
    lines.extend([
        "",
        "## 3. Độ phân tán theo tài liệu",
        "",
        f"- Có QA trên **{doc_dist['documents_with_any_train_dev_qa']}/{doc_dist['accepted_corpus_documents']}** tài liệu ACCEPT "
        f"({doc_dist['coverage_percent']}%); **{doc_dist['documents_without_train_dev_qa']} tài liệu không có câu nào**.",
        f"- Trung bình trên toàn bộ tài liệu ACCEPT: **{doc_dist['mean_per_all_accepted_documents']}** lượt QA/tài liệu; median **{doc_dist['median_per_all_accepted_documents']}**.",
        f"- Tài liệu cao nhất: **{doc_dist['max_per_document']}** câu; top-5 chiếm **{doc_dist['top_5_share'] * 100:.1f}%** lượt tham gia tài liệu.",
        f"- Gini gồm cả tài liệu 0-QA: **{doc_dist['gini_including_zero_qa_documents']:.3f}**; HHI: **{doc_dist['hhi']:.3f}**.",
        "",
        "### 20 tài liệu có nhiều Q&A nhất",
        "",
        "| Hạng | Doc ID | Tài liệu | Lĩnh vực | TRAIN | DEV | Tổng | Nhóm câu chính |",
        "|---:|---|---|---|---:|---:|---:|---|",
    ])
    for rank, row in enumerate(per_document[:20], start=1):
        lines.append(
            f"| {rank} | {row['doc_id']} | {md(row['title'])} | {md(row['content_domain'])} | "
            f"{row['train_qa_participation']} | {row['dev_qa_participation']} | {row['total_qa_participation']} | {md(row['qa_types'])} |"
        )

    lines.extend([
        "",
        "## 4. Phân bố theo lĩnh vực tài liệu",
        "",
        "`Unique QA participation` đếm một QA một lần trong mỗi lĩnh vực mà gold document của nó tham gia; tổng có thể lớn hơn 436 nếu QA nối nhiều lĩnh vực.",
        "",
        "| Lĩnh vực tài liệu | Docs corpus | Docs có QA | Coverage | QA participation | Share TRAIN+DEV | Topic chính |",
        "|---|---:|---:|---:|---:|---:|---|",
    ])
    for row in per_domain:
        lines.append(
            f"| {md(row['content_domain'])} | {row['corpus_documents']} | {row['documents_with_qa']} | "
            f"{row['document_coverage_percent']}% | {row['unique_qa_participation']} | "
            f"{row['qa_share_of_train_dev_percent']}% | {md(row['topics'])} |"
        )

    lines.extend([
        "",
        "## 5. Rủi ro phân bố và chất lượng",
        "",
        f"1. **Không có human ground truth:** 0/{len(analysis_records)} TRAIN+DEV được human-validated.",
        f"2. **Bao phủ tài liệu chưa đủ:** {doc_dist['documents_without_train_dev_qa']}/89 tài liệu ACCEPT không có QA TRAIN/DEV.",
        "3. **Thiên lệch lĩnh vực:** dự báo nguồn nước và chất lượng nước chiếm phần lớn QA; toàn bộ 7 quy trình vận hành liên hồ ACCEPT không có QA TRAIN/DEV.",
        f"4. **Candidate Test tập trung một family:** {split_manifest['candidate_test_family_concentration']['qa_count']}/109 "
        f"({split_manifest['candidate_test_family_concentration']['share'] * 100:.0f}%) thuộc `{split_manifest['candidate_test_family_concentration']['top_family']}`.",
        "5. **Distribution shift có chủ ý nhưng rất mạnh:** Candidate Test có 63/109 cross-document và 63/109 table-table; TRAIN tương ứng 0/343 và 43/343.",
        f"6. **Template/câu gần trùng:** có {summary['near_duplicates']['exact_normalized_duplicate_pairs']} cặp trùng nguyên câu sau chuẩn hóa; "
        f"{summary['near_duplicates']['pairs_jaccard_ge_0_90']} cặp đạt token-set Jaccard >= 0.90 trên toàn TRAIN+DEV, "
        f"nhưng chỉ {summary['near_duplicates']['cross_split_pairs_jaccard_ge_0_90']} cặp xuyên TRAIN–DEV ở ngưỡng này "
        f"({summary['near_duplicates']['cross_split_pairs_jaccard_ge_0_80']} cặp nếu hạ ngưỡng xuống 0.80). "
        "Đây là heuristic nhạy với câu cùng template, không tự động đồng nghĩa leakage nội dung.",
        f"7. **Template hóa:** top-10 heuristic templates chiếm {summary['template_concentration']['top_10_template_share'] * 100:.1f}% TRAIN+DEV.",
        "",
        "## 6. Kết luận sử dụng",
        "",
        "- Bộ Q&A hiện phù hợp hơn với đánh giá retrieval trên hai miền chi phối: dự báo nguồn nước và chất lượng nước.",
        "- Chưa đủ cơ sở gọi là benchmark bao phủ toàn diện thủy lợi/tài nguyên nước vì nhiều nhóm pháp lý, vận hành hồ, đê điều, hạ tầng và PCTT không có hoặc có rất ít QA.",
        "- Candidate Test nên được mô tả là series/family stress-test, không phải đại diện đồng đều cho toàn corpus.",
        "- Trước khi dùng để kết luận khoa học, cần human-review một mẫu phân tầng theo topic × document × modality, rồi sửa/loại các QA sai nguồn hoặc sai semantics.",
        "",
    ])
    (OUT / "QA_DISTRIBUTION_ANALYSIS.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "status": "PASS",
        "train_dev_analyzed": len(analysis_records),
        "candidate_test_content_read": False,
        "outputs": [path.name for path in sorted(OUT.iterdir())],
    }, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
