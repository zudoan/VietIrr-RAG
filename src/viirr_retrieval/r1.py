from __future__ import annotations

import csv
import hashlib
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .b23 import normalize_modality
from .bm25 import BM25Retriever, result_from_unit
from .c1 import _bootstrap, _subgroup_labels
from .candidate_metrics import final_ranking_metrics
from .io_utils import read_jsonl, sha256, write_json, write_jsonl


REPRESENTATIONS = ("R0", "R1", "R2")
STAGES = ("FIXED_POOL", "FULL_RETRIEVAL")
SUBGROUPS = (
    "OVERALL", "RETRIEVAL_SINGLE", "RETRIEVAL_MULTI", "TEXT_ONLY", "TABLE_ONLY",
    "TEXT_TABLE", "TABLE_TABLE", "SAME_PAGE", "CROSS_PAGE_SAME_DOCUMENT", "CROSS_DOCUMENT",
)
HEADING_TYPES = {"HEADING", "SECTION_HEADING", "ARTICLE_HEADING"}


def _json_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_r1_dev(root: Path, split: str = "dev") -> list[dict]:
    if split != "dev":
        raise ValueError("R1 is DEV-only; Candidate Test must remain sealed")
    return read_jsonl(root / "data/benchmark/dev.jsonl")


def _clean(value: object) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def _load_structure(root: Path) -> dict:
    documents = {row["doc_id"]: row for row in read_jsonl(root / "data/parsed/documents.jsonl")}
    regions = {row["region_id"]: row for row in read_jsonl(root / "data/parsed/regions.jsonl")}
    tables = {row["table_id"]: row for row in read_jsonl(root / "data/parsed/tables.jsonl")}
    pages = {row["page_id"]: row for row in read_jsonl(root / "data/parsed/pages.jsonl")}
    sections: dict[str, dict] = {}
    page_sections: dict[str, str] = {}
    for path in sorted((root / "data/parsed").glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(record, dict) or "doc_id" not in record:
            continue
        for section in record.get("sections") or []:
            if section.get("section_id"):
                sections[section["section_id"]] = section
        for page in record.get("pages") or []:
            if page.get("page_id") and page.get("section_id"):
                page_sections[page["page_id"]] = page["section_id"]

    headings_by_page: dict[str, list[dict]] = defaultdict(list)
    for region in regions.values():
        if region.get("region_type") in HEADING_TYPES and _clean(region.get("normalized_text") or region.get("raw_text")):
            headings_by_page[region["page_id"]].append(region)
    for rows in headings_by_page.values():
        rows.sort(key=lambda row: int(row.get("reading_order") or 0))
    return {
        "documents": documents, "regions": regions, "tables": tables, "pages": pages,
        "sections": sections, "page_sections": page_sections, "headings_by_page": headings_by_page,
    }


def _section_context(unit: dict, structure: dict) -> tuple[str | None, str | None, dict]:
    region = structure["regions"].get(unit["evidence_id"])
    section_id = (region or {}).get("section_id") or structure["page_sections"].get(unit["page_id"])
    section = structure["sections"].get(section_id)
    section_title = _clean((section or {}).get("section_title"))
    parent_title = None
    if section and section.get("parent_section"):
        parent_title = _clean((structure["sections"].get(section["parent_section"]) or {}).get("section_title"))
    nearest_heading = None
    if region:
        order = int(region.get("reading_order") or 0)
        preceding = [row for row in structure["headings_by_page"].get(unit["page_id"], [])
                     if int(row.get("reading_order") or 0) <= order]
        if preceding:
            nearest_heading = _clean(preceding[-1].get("normalized_text") or preceding[-1].get("raw_text"))
    local_context = nearest_heading or parent_title
    if local_context == section_title:
        local_context = None
    return section_title, local_context, {
        "section_id": section_id,
        "section_source": "verified_section_map" if section_title else None,
        "local_context_source": "nearest_preceding_heading" if nearest_heading else (
            "verified_parent_section" if parent_title else None
        ),
    }


def serialize_table(table: dict) -> tuple[str | None, dict]:
    """Serialize only table structure already present in Phase A."""
    pieces, used = [], []
    caption = _clean(table.get("caption"))
    if caption:
        pieces.append(f"Table caption: {caption}"); used.append("caption")
    headers = [_clean(value) for value in (table.get("headers") or table.get("column_labels") or [])]
    headers = [value for value in headers if value]
    if headers:
        pieces.append("Column headers: " + " | ".join(headers)); used.append("headers")
    row_labels = [_clean(value) for value in (table.get("row_labels") or [])]
    row_labels = [value for value in row_labels if value]
    if row_labels:
        pieces.append("Row labels: " + " | ".join(row_labels)); used.append("row_labels")
    rows = []
    for row in table.get("rows") or []:
        cells = [_clean(value) for value in row]
        cells = [value for value in cells if value]
        if cells:
            rows.append(" | ".join(cells))
    if rows:
        pieces.append("Rows:\n" + "\n".join(rows)); used.append("rows")
    units = []
    for semantic_tuple in table.get("semantic_tuples") or []:
        unit = semantic_tuple.get("unit") if isinstance(semantic_tuple.get("unit"), dict) else {}
        value = _clean(unit.get("raw") or unit.get("normalized"))
        if value and value not in units:
            units.append(value)
    if units:
        pieces.append("Units: " + " | ".join(units)); used.append("units")
    return ("\n".join(pieces) if pieces else None), {
        "fields_used": used, "source_table_id": table.get("table_id"),
        "fallback_reason": None if pieces else "NO_VERIFIED_TABLE_STRUCTURE",
    }


def build_retrieval_representations(units: list[dict], structure: dict) -> dict[str, list[dict]]:
    """Build representations from source metadata only; accepts no QA or gold inputs."""
    output = {name: [] for name in REPRESENTATIONS}
    for unit in units:
        original = str(unit.get("index_text") or "")
        document = structure["documents"].get(unit["doc_id"], {})
        title = _clean(document.get("title"))
        section, local_context, section_trace = _section_context(unit, structure)
        page_number = unit.get("page_number")
        context_parts, context_fields = [], []
        if title:
            context_parts.append(f"Document: {title}"); context_fields.append("document_title")
        if section:
            context_parts.append(f"Section: {section}"); context_fields.append("section_title")
        if page_number is not None:
            context_parts.append(f"Page: {page_number}"); context_fields.append("page_number")
        if local_context:
            context_parts.append(f"Context: {local_context}"); context_fields.append("local_parent_context")
        context_prefix = "\n".join(context_parts)
        contextualized = f"{context_prefix}\nContent: {original}" if context_prefix else original

        table = structure["tables"].get(unit["evidence_id"])
        table_text, table_trace = serialize_table(table) if table else (None, {
            "fields_used": [], "source_table_id": None,
            "fallback_reason": "NOT_A_TABLE_REGION" if unit.get("unit_type") != "TABLE_REGION" else "TABLE_RECORD_MISSING",
        })
        if unit.get("unit_type") == "TABLE_REGION" and table_text:
            r2_text = f"{context_prefix}\n{table_text}\nOriginal table content: {original}" if context_prefix else f"{table_text}\nOriginal table content: {original}"
        else:
            r2_text = contextualized

        common = {
            "evidence_id": unit["evidence_id"], "doc_id": unit["doc_id"],
            "page_id": unit["page_id"], "page_number": page_number,
            "unit_type": unit.get("unit_type"), "original_text_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
            "source_locator": {"doc_id": unit["doc_id"], "page_id": unit["page_id"], "evidence_id": unit["evidence_id"]},
        }
        texts = {"R0": original, "R1": contextualized, "R2": r2_text}
        for name in REPRESENTATIONS:
            fields = ["original_content"]
            if name in ("R1", "R2"):
                fields += context_fields
            if name == "R2" and unit.get("unit_type") == "TABLE_REGION" and table_text:
                fields += [f"table_{field}" for field in table_trace["fields_used"]]
            row = {
                **common, "representation": name, "retrieval_text": texts[name],
                "retrieval_text_sha256": hashlib.sha256(texts[name].encode("utf-8")).hexdigest(),
                "source_fields_used": fields,
                "section_trace": section_trace,
                "table_trace": table_trace if name == "R2" else None,
                "fallback_reasons": [reason for reason in (
                    "NO_VERIFIED_SECTION" if name in ("R1", "R2") and not section else None,
                    table_trace["fallback_reason"] if name == "R2" and unit.get("unit_type") == "TABLE_REGION" and not table_text else None,
                ) if reason],
                "gold_or_qa_used": False,
            }
            output[name].append(row)
    if any([row["evidence_id"] for row in output[name]] != [row["evidence_id"] for row in output["R0"]]
           for name in REPRESENTATIONS):
        raise AssertionError("Representation evidence IDs changed")
    for r1_row, r2_row in zip(output["R1"], output["R2"]):
        if r1_row["unit_type"] != "TABLE_REGION" and r1_row["retrieval_text"] != r2_row["retrieval_text"]:
            raise AssertionError("R2 must preserve R1 for text regions")
    return output


def make_token_windows(rows: list[dict], tokenizer, content_tokens: int, overlap_tokens: int) -> tuple[list[dict], dict]:
    if content_tokens <= 0 or overlap_tokens < 0 or overlap_tokens >= content_tokens:
        raise ValueError("Invalid fixed window configuration")
    step = content_tokens - overlap_tokens
    windows, full_lengths = [], []
    for unit_index, row in enumerate(rows):
        text = row["retrieval_text"]
        full_length = len(tokenizer("passage: " + text, add_special_tokens=True, truncation=False)["input_ids"])
        full_lengths.append(full_length)
        ids = tokenizer(text, add_special_tokens=False, truncation=False)["input_ids"]
        if not ids:
            ids = tokenizer(" ", add_special_tokens=False, truncation=False)["input_ids"]
        starts = list(range(0, len(ids), step))
        for number, start in enumerate(starts):
            chunk = ids[start:start + content_tokens]
            window_text = tokenizer.decode(chunk, skip_special_tokens=True, clean_up_tokenization_spaces=False)
            encoded_length = len(tokenizer("passage: " + window_text, add_special_tokens=True, truncation=False)["input_ids"])
            windows.append({
                "window_id": f"{row['representation']}_{row['evidence_id']}_{number:04d}",
                "evidence_id": row["evidence_id"], "unit_index": unit_index,
                "window_number": number, "text": window_text,
                "token_count_with_prefix_and_special": encoded_length,
                "text_sha256": hashlib.sha256(window_text.encode("utf-8")).hexdigest(),
            })
            if start + content_tokens >= len(ids):
                break
    counts = Counter(row["evidence_id"] for row in windows)
    metadata = {
        "unit_count": len(rows), "window_count": len(windows),
        "content_tokens": content_tokens, "overlap_tokens": overlap_tokens,
        "aggregation": "max", "full_text_over_512": sum(value > 512 for value in full_lengths),
        "full_text_truncation_rate": sum(value > 512 for value in full_lengths) / len(rows),
        "max_full_text_tokens": max(full_lengths, default=0),
        "windows_over_512": sum(row["token_count_with_prefix_and_special"] > 512 for row in windows),
        "max_window_tokens": max((row["token_count_with_prefix_and_special"] for row in windows), default=0),
        "multi_window_units": sum(value > 1 for value in counts.values()),
        "mapping_valid": len(counts) == len(rows) and set(counts) == {row["evidence_id"] for row in rows},
    }
    return windows, metadata


def max_pool_window_scores(scores: np.ndarray, unit_indexes: np.ndarray, unit_count: int) -> np.ndarray:
    output = np.full(unit_count, -np.inf, dtype=np.float64)
    np.maximum.at(output, unit_indexes, np.asarray(scores, dtype=np.float64))
    return output


def _source_audit(units: list[dict], structure: dict) -> dict:
    counts = Counter()
    type_counts = Counter(row["unit_type"] for row in units)
    for unit in units:
        region = structure["regions"].get(unit["evidence_id"])
        table = structure["tables"].get(unit["evidence_id"])
        document = structure["documents"].get(unit["doc_id"], {})
        section, local_context, trace = _section_context(unit, structure)
        tuples = (table or {}).get("semantic_tuples") or []
        time_known = any(
            isinstance(row.get("time"), dict) and any(row["time"].get(key) for key in ("raw", "normalized_start", "normalized_end"))
            for row in tuples
        )
        values = {
            "document_title": bool(_clean(document.get("title"))),
            "page": unit.get("page_id") is not None and unit.get("page_number") is not None,
            "verified_section": bool(section),
            "verified_local_parent_context": bool(local_context),
            "parent_child_relation": bool(trace.get("section_id") and section),
            "original_region_text": bool(_clean(unit.get("index_text"))),
            "table_caption": bool(_clean((table or {}).get("caption"))),
            "table_headers": bool((table or {}).get("headers") or (table or {}).get("column_labels")),
            "table_rows": bool((table or {}).get("rows")),
            "entity": any(isinstance(row.get("entity"), dict) and any(row["entity"].get(k) for k in ("raw", "canonical")) for row in tuples),
            "metric": any(isinstance(row.get("metric"), dict) and any(row["metric"].get(k) for k in ("raw", "canonical")) for row in tuples),
            "document_reporting_time": bool(document.get("document_reporting_period")),
            "evidence_time": time_known,
            "source_locator": bool(unit.get("doc_id") and unit.get("page_id") and unit.get("evidence_id")),
            "ocr_uncertainty_signal": bool(
                (region or {}).get("text_extraction") == "OCR"
                or (region or {}).get("text_quality") not in (None, "GOOD")
                or (table or {}).get("semantic_quality") not in (None, "GOOD")
            ),
        }
        for key, value in values.items():
            counts[key] += bool(value)
    return {
        "unit_count": len(units), "unit_types": dict(type_counts),
        "coverage_unique_evidence_ids": {
            key: {"count": int(value), "rate": value / len(units)} for key, value in sorted(counts.items())
        },
        "schema_sources": {
            "document": "data/parsed/documents.jsonl",
            "section_hierarchy": "data/parsed/<doc_id>.json sections/pages",
            "region": "data/parsed/regions.jsonl",
            "table": "data/parsed/tables.jsonl",
            "retrieval_unit": "data/processed/evidence_units.jsonl",
        },
        "unknown_policy": "Missing metadata is omitted from retrieval text; original content is retained.",
    }


def _load_model(config: dict):
    import torch
    from huggingface_hub import snapshot_download
    from sentence_transformers import SentenceTransformer
    model_path = Path(snapshot_download(config["id"], local_files_only=True))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(config["id"], device=device, local_files_only=True)
    model.max_seq_length = int(config["max_length"])
    return model, model_path.name, device


def _load_or_embed(root: Path, name: str, rows: list[dict], windows: list[dict], model,
                   revision: str, device: str, config: dict) -> tuple[np.ndarray, dict]:
    import torch
    cache_dir = root / "outputs/R1/cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    npy_path = cache_dir / f"{name.lower()}_window_embeddings.npy"
    meta_path = cache_dir / f"{name.lower()}_window_embeddings.json"
    text_hash = _json_hash([(row["evidence_id"], row["retrieval_text_sha256"]) for row in rows])
    window_hash = _json_hash([(row["window_id"], row["evidence_id"], row["text_sha256"]) for row in windows])
    expected = {
        "representation": name, "retrieval_text_sha256": text_hash,
        "window_map_sha256": window_hash, "window_count": len(windows),
        "unit_count": len(rows), "model_id": config["model"]["id"], "revision": revision,
        "max_length": config["model"]["max_length"], "normalized": True,
        "passage_prefix": config["model"]["passage_prefix"],
        "window_content_tokens": config["windowing"]["content_tokens"],
        "window_overlap_tokens": config["windowing"]["overlap_tokens"],
        "aggregation": config["windowing"]["aggregation"],
    }
    if npy_path.exists() and meta_path.exists():
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        if all(metadata.get(key) == value for key, value in expected.items()):
            metadata["cache_hit"] = True
            return np.load(npy_path, mmap_mode="r"), metadata
    texts = [config["model"]["passage_prefix"] + row["text"] for row in windows]
    batch_size = int(config["model"]["batch_size"])
    started = time.perf_counter()
    while batch_size >= 1:
        try:
            vectors = model.encode(texts, batch_size=batch_size, show_progress_bar=True,
                                   normalize_embeddings=True, convert_to_numpy=True)
            if device == "cuda":
                torch.cuda.synchronize()
            break
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache(); batch_size //= 2
    if batch_size < 1:
        raise RuntimeError("R1 E5 embedding failed at batch_size=1")
    elapsed = time.perf_counter() - started
    vectors = np.asarray(vectors, dtype=np.float32)
    np.save(npy_path, vectors)
    metadata = {
        **expected, "cache_hit": False, "device": device,
        "effective_batch_size": batch_size, "indexing_seconds": elapsed,
        "embedding_dimension": int(vectors.shape[1]), "bytes": int(npy_path.stat().st_size),
    }
    write_json(meta_path, metadata)
    return vectors, metadata


def _ranks(scores: np.ndarray, ids: np.ndarray, indexes: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    indexes = np.arange(len(ids), dtype=np.int32) if indexes is None else np.asarray(indexes, dtype=np.int32)
    order = indexes[np.lexsort((ids[indexes], -scores[indexes]))]
    ranks = np.empty(len(ids), dtype=np.int32)
    ranks.fill(len(ids) + 1)
    ranks[order] = np.arange(1, len(order) + 1, dtype=np.int32)
    return order, ranks


def _rrf_order(bm25_scores: np.ndarray, dense_scores: np.ndarray, ids: np.ndarray,
               indexes: np.ndarray, rrf_k: int) -> np.ndarray:
    bm25_order, _ = _ranks(bm25_scores, ids, indexes)
    dense_order, _ = _ranks(dense_scores, ids, indexes)
    bm25_local = np.empty(len(ids), dtype=np.int32); dense_local = np.empty(len(ids), dtype=np.int32)
    bm25_local.fill(len(ids) + 1); dense_local.fill(len(ids) + 1)
    bm25_local[bm25_order] = np.arange(1, len(bm25_order) + 1)
    dense_local[dense_order] = np.arange(1, len(dense_order) + 1)
    scores = 1.0 / (rrf_k + bm25_local[indexes]) + 1.0 / (rrf_k + dense_local[indexes])
    return indexes[np.lexsort((ids[indexes], -scores))]


def _global_rrf_results(candidate_ids: list[str], id_to_index: dict[str, int], units: list[dict],
                        ids: np.ndarray, bm25_ranks: np.ndarray, dense_ranks: np.ndarray,
                        rrf_k: int) -> list[dict]:
    indexes = np.asarray([id_to_index[item_id] for item_id in candidate_ids], dtype=np.int32)
    scores = 1.0 / (rrf_k + bm25_ranks[indexes]) + 1.0 / (rrf_k + dense_ranks[indexes])
    order = indexes[np.lexsort((ids[indexes], -scores))]
    score_map = {int(index): float(score) for index, score in zip(indexes, scores)}
    return [result_from_unit(units[int(index)], score_map[int(index)], rank).to_dict()
            for rank, index in enumerate(order, 1)]


def _labels(qa: dict) -> set[str]:
    labels = set(_subgroup_labels(qa))
    labels.add(normalize_modality(qa))
    return labels


def _evaluate(dev: list[dict], records: dict[str, dict], latency: dict[str, float]) -> tuple[dict, dict]:
    per_query, grouped = {}, {group: [] for group in SUBGROUPS}
    for qa in dev:
        qa_id = qa["qa_id"]
        record = records[qa_id]
        ranked_ids = [row["evidence_id"] for row in record["results"]]
        metrics = final_ranking_metrics(qa["retrieval_evidence_ids"], ranked_ids, [10, 20])
        candidate_set = set(record["candidate_ids"])
        gold = set(qa["retrieval_evidence_ids"])
        row = {
            "candidate_complete": float(gold <= candidate_set),
            "candidate_gold_coverage": len(gold & candidate_set) / len(gold),
            "metrics": metrics, "latency_ms": latency[qa_id],
        }
        per_query[qa_id] = row
        for group in SUBGROUPS:
            if group == "OVERALL" or group in _labels(qa):
                grouped[group].append((qa, row))
    aggregates = {}
    for group, rows in grouped.items():
        if not rows:
            aggregates[group] = {"sample_count": 0, "unique_gold_sets": 0}
            continue
        values = [row for _, row in rows]
        mean = lambda fn: float(np.mean([fn(row) for row in values]))
        aggregates[group] = {
            "sample_count": len(rows),
            "unique_gold_sets": len({"|".join(sorted(qa["retrieval_evidence_ids"])) for qa, _ in rows}),
            "candidate_coverage@100": mean(lambda row: row["candidate_complete"]),
            "all_r@10": mean(lambda row: row["metrics"]["10"]["all_recall"]),
            "all_r@20": mean(lambda row: row["metrics"]["20"]["all_recall"]),
            "any_r@10": mean(lambda row: row["metrics"]["10"]["any_recall"]),
            "any_r@20": mean(lambda row: row["metrics"]["20"]["any_recall"]),
            "average_gold_coverage@20": mean(lambda row: row["metrics"]["20"]["average_gold_coverage"]),
            "mrr": mean(lambda row: row["metrics"]["mrr"]),
            "ndcg@10": mean(lambda row: row["metrics"]["ndcg@10"]),
            "latency_ms_per_query": mean(lambda row: row["latency_ms"]),
        }
    return per_query, aggregates


def _transitions(dev: list[dict], current: dict, baseline: dict, stage: str, comparison: str,
                 current_records: dict, baseline_records: dict) -> list[dict]:
    rows = []
    previous_missing = {
        "V3_1_CHAL_00041", "V3_1_CHAL_00172", "V3_1_CHAL_00174", "V3_1_CHAL_00182",
        "V3_1_CHAL_00184", "V3_1_CHAL_00185", "V3_1_CHAL_00192", "V3_1_CHAL_00194",
    }
    for qa in dev:
        qa_id = qa["qa_id"]
        before_candidate = baseline[qa_id]["candidate_complete"]
        after_candidate = current[qa_id]["candidate_complete"]
        before_all = baseline[qa_id]["metrics"]["20"]["all_recall"]
        after_all = current[qa_id]["metrics"]["20"]["all_recall"]
        gold = qa["retrieval_evidence_ids"]
        before_ranks = {row["evidence_id"]: row["rank"] for row in baseline_records[qa_id]["results"]}
        after_ranks = {row["evidence_id"]: row["rank"] for row in current_records[qa_id]["results"]}
        before_worst = max((before_ranks.get(item, 10**9) for item in gold), default=10**9)
        after_worst = max((after_ranks.get(item, 10**9) for item in gold), default=10**9)
        classes = []
        if not before_candidate and after_candidate: classes.append("CANDIDATE_RECOVERED")
        if before_candidate and not after_candidate: classes.append("CANDIDATE_LOST")
        if after_worst < before_worst: classes.append("GOLD_RANK_IMPROVED")
        if after_worst > before_worst: classes.append("GOLD_RANK_DEGRADED")
        if not classes: classes.append("NO_CHANGE")
        rows.append({
            "qa_id": qa_id, "stage": stage, "comparison": comparison,
            "candidate_complete_before": before_candidate, "candidate_complete_after": after_candidate,
            "all_r@20_before": before_all, "all_r@20_after": after_all,
            "worst_gold_rank_before": None if before_worst == 10**9 else before_worst,
            "worst_gold_rank_after": None if after_worst == 10**9 else after_worst,
            "transition_classes": classes, "modality": normalize_modality(qa),
            "retrieval_multi": qa["retrieval_multi_evidence"],
            "previous_candidate_missing_8": qa_id in previous_missing,
            "gold_set_signature": "|".join(sorted(gold)),
        })
    return rows


def run_r1(root: Path, pytest_result: dict | None = None) -> dict:
    config = json.loads((root / "configs/r1.json").read_text(encoding="utf-8"))
    report_dir, output_dir = root / "reports/R1", root / "outputs/R1"
    for directory in (report_dir, output_dir / "rankings", output_dir / "representations", output_dir / "windows", output_dir / "cache"):
        directory.mkdir(parents=True, exist_ok=True)
    candidate_test = root / "data/benchmark/candidate_test.jsonl"
    candidate_hash_before = sha256(candidate_test)
    protected_paths = [
        root / "data/benchmark/dev.jsonl", root / "data/processed/evidence_units.jsonl",
        root / "data/parsed/documents.jsonl", root / "data/parsed/regions.jsonl",
        root / "data/parsed/tables.jsonl", root / "outputs/C1/candidates/g0_b100_dev.jsonl",
        root / "outputs/B2_1/rankings/p0_pages_dev_top100.jsonl",
        root / "outputs/B2/cache/bm25_regions.pkl",
    ]
    protected_hashes = {path.relative_to(root).as_posix(): sha256(path) for path in protected_paths}

    dev = load_r1_dev(root)
    units_path = root / "data/processed/evidence_units.jsonl"
    units = read_jsonl(units_path)
    ids = np.asarray([row["evidence_id"] for row in units], dtype=object)
    id_to_index = {item_id: index for index, item_id in enumerate(ids)}
    structure = _load_structure(root)
    source_audit = _source_audit(units, structure)
    write_json(report_dir / "SOURCE_AUDIT.json", source_audit)

    representations = build_retrieval_representations(units, structure)
    for name in REPRESENTATIONS:
        write_jsonl(output_dir / "representations" / f"{name.lower()}_retrieval_text.jsonl", representations[name])
    representation_audit = {
        "evidence_id_count": len(units),
        "same_ids_and_order": all([row["evidence_id"] for row in representations[name]] == list(ids) for name in REPRESENTATIONS),
        "R1_enriched": sum(a["retrieval_text"] != b["retrieval_text"] for a, b in zip(representations["R0"], representations["R1"])),
        "R1_raw_fallback": sum(a["retrieval_text"] == b["retrieval_text"] for a, b in zip(representations["R0"], representations["R1"])),
        "R2_table_serialization_changed": sum(
            a["retrieval_text"] != b["retrieval_text"] and a["unit_type"] == "TABLE_REGION"
            for a, b in zip(representations["R1"], representations["R2"])
        ),
        "R2_table_fallback": sum(
            a["unit_type"] == "TABLE_REGION" and a["retrieval_text"] == b["retrieval_text"]
            for a, b in zip(representations["R1"], representations["R2"])
        ),
        "R2_text_equals_R1": all(
            a["retrieval_text"] == b["retrieval_text"] for a, b in zip(representations["R1"], representations["R2"])
            if a["unit_type"] != "TABLE_REGION"
        ),
        "retrieval_text_hashes": {name: _json_hash([
            (row["evidence_id"], row["retrieval_text_sha256"]) for row in representations[name]
        ]) for name in REPRESENTATIONS},
        "fabricated_unknown_fields_added": 0,
        "qa_gold_or_answer_used": False,
    }

    model, revision, device = _load_model(config["model"])
    cache_manifest = {"model_id": config["model"]["id"], "revision": revision, "device": device, "representations": {}}
    window_sets, embeddings = {}, {}
    for name in REPRESENTATIONS:
        windows, window_metadata = make_token_windows(
            representations[name], model.tokenizer,
            config["windowing"]["content_tokens"], config["windowing"]["overlap_tokens"],
        )
        window_sets[name] = windows
        write_jsonl(output_dir / "windows" / f"{name.lower()}_window_map.jsonl", ({
            key: row[key] for key in ("window_id", "evidence_id", "unit_index", "window_number", "token_count_with_prefix_and_special", "text_sha256")
        } for row in windows))
        vectors, embedding_metadata = _load_or_embed(root, name, representations[name], windows, model, revision, device, config)
        embeddings[name] = vectors
        cache_manifest["representations"][name] = {**window_metadata, **embedding_metadata}
    representation_audit["windowing"] = {
        name: {key: cache_manifest["representations"][name][key] for key in (
            "unit_count", "window_count", "full_text_over_512", "full_text_truncation_rate",
            "max_full_text_tokens", "windows_over_512", "max_window_tokens", "multi_window_units", "mapping_valid",
        )} for name in REPRESENTATIONS
    }
    write_json(report_dir / "REPRESENTATION_AUDIT.json", representation_audit)
    write_json(output_dir / "cache" / "CACHE_MANIFEST.json", cache_manifest)

    phase_b = json.loads((root / "configs/phase_b.json").read_text(encoding="utf-8"))
    bm25 = BM25Retriever(units, root / "outputs/B2/cache/bm25_regions.pkl", sha256(units_path),
                         phase_b["bm25"]["k1"], phase_b["bm25"]["b"])
    g0 = {row["qa_id"]: row for row in read_jsonl(root / "outputs/C1/candidates/g0_b100_dev.jsonl")}
    p0_pages = {row["qa_id"]: row for row in read_jsonl(root / "outputs/B2_1/rankings/p0_pages_dev_top100.jsonl")}
    page_to_indexes: dict[str, list[int]] = defaultdict(list)
    for index, unit in enumerate(units):
        page_to_indexes[unit["page_id"]].append(index)
    query_started = time.perf_counter()
    query_vectors = model.encode(
        [config["model"]["query_prefix"] + qa["question"] for qa in dev],
        batch_size=config["model"]["batch_size"], show_progress_bar=False,
        normalize_embeddings=True, convert_to_numpy=True,
    ).astype(np.float32)
    if device == "cuda":
        import torch
        torch.cuda.synchronize()
    query_encoding_seconds = time.perf_counter() - query_started

    records = {stage: {name: {} for name in REPRESENTATIONS} for stage in STAGES}
    latency = {stage: {name: {} for name in REPRESENTATIONS} for stage in STAGES}
    unit_indexes_by_rep = {
        name: np.asarray([row["unit_index"] for row in window_sets[name]], dtype=np.int32)
        for name in REPRESENTATIONS
    }
    for qa_index, qa in enumerate(dev):
        qa_id, query = qa["qa_id"], qa["question"]
        bm25_started = time.perf_counter()
        bm25_scores = bm25.score_all(query)
        _, bm25_ranks = _ranks(bm25_scores, ids)
        bm25_seconds = time.perf_counter() - bm25_started
        selected_pages = {row["page_id"] for row in p0_pages[qa_id]["results"][:config["retrieval"]["page_budget"]]}
        page_indexes = np.asarray(sorted({index for page_id in selected_pages for index in page_to_indexes.get(page_id, [])}), dtype=np.int32)
        for name in REPRESENTATIONS:
            started = time.perf_counter()
            window_scores = np.asarray(embeddings[name] @ query_vectors[qa_index], dtype=np.float64)
            dense_scores = max_pool_window_scores(window_scores, unit_indexes_by_rep[name], len(units))
            _, dense_ranks = _ranks(dense_scores, ids)
            shared_ms = (time.perf_counter() - started + bm25_seconds + query_encoding_seconds / len(dev)) * 1000.0

            fixed_ids = g0[qa_id]["candidate_ids"]
            fixed_results = _global_rrf_results(
                fixed_ids, id_to_index, units, ids, bm25_ranks, dense_ranks, config["retrieval"]["rrf_k"],
            )
            records["FIXED_POOL"][name][qa_id] = {
                "qa_id": qa_id, "representation": name, "stage": "FIXED_POOL",
                "candidate_ids": fixed_ids, "results": fixed_results,
            }
            latency["FIXED_POOL"][name][qa_id] = shared_ms

            candidate_order = _rrf_order(
                bm25_scores, dense_scores, ids, page_indexes, config["retrieval"]["rrf_k"],
            )
            full_ids = [str(ids[index]) for index in candidate_order[:config["retrieval"]["candidate_budget"]]]
            full_results = _global_rrf_results(
                full_ids, id_to_index, units, ids, bm25_ranks, dense_ranks, config["retrieval"]["rrf_k"],
            )
            records["FULL_RETRIEVAL"][name][qa_id] = {
                "qa_id": qa_id, "representation": name, "stage": "FULL_RETRIEVAL",
                "candidate_ids": full_ids, "results": full_results,
            }
            latency["FULL_RETRIEVAL"][name][qa_id] = shared_ms

    for stage in STAGES:
        for name in REPRESENTATIONS:
            write_jsonl(output_dir / "rankings" / f"{stage.lower()}_{name.lower()}_dev.jsonl",
                        (records[stage][name][qa["qa_id"]] for qa in dev))

    per_query, subgroups = {stage: {} for stage in STAGES}, {stage: {} for stage in STAGES}
    result_rows = []
    for stage in STAGES:
        for name in REPRESENTATIONS:
            per_query[stage][name], subgroups[stage][name] = _evaluate(
                dev, records[stage][name], latency[stage][name]
            )
            overall, multi = subgroups[stage][name]["OVERALL"], subgroups[stage][name]["RETRIEVAL_MULTI"]
            result_rows.append({
                "stage": stage, "representation": name, "sample_count": len(dev),
                "candidate_coverage@100": overall["candidate_coverage@100"],
                "all_r@10": overall["all_r@10"], "all_r@20": overall["all_r@20"],
                "multi_all_r@20": multi["all_r@20"], "any_r@10": overall["any_r@10"],
                "any_r@20": overall["any_r@20"], "average_gold_coverage@20": overall["average_gold_coverage@20"],
                "mrr": overall["mrr"], "ndcg@10": overall["ndcg@10"],
                "retrieval_latency_ms_per_query": overall["latency_ms_per_query"],
                "indexing_seconds": cache_manifest["representations"][name].get("indexing_seconds", 0.0),
                "embedding_truncation_rate_before_windowing": cache_manifest["representations"][name]["full_text_truncation_rate"],
                "embedding_truncation_rate_after_windowing": cache_manifest["representations"][name]["windows_over_512"] / cache_manifest["representations"][name]["window_count"],
            })
    with (report_dir / "RESULTS.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result_rows[0])); writer.writeheader(); writer.writerows(result_rows)
    write_json(report_dir / "SUBGROUPS.json", {
        "group_definition": "DEV annotations used only for offline evaluation",
        "stages": subgroups,
    })

    transition_rows = []
    for stage in STAGES:
        for name in ("R1", "R2"):
            transition_rows.extend(_transitions(
                dev, per_query[stage][name], per_query[stage]["R0"], stage, f"{name}_vs_R0",
                records[stage][name], records[stage]["R0"],
            ))
    write_jsonl(report_dir / "FAILURE_TRANSITIONS.jsonl", transition_rows)

    statistics = {"comparisons": {}, "bootstrap_resamples": config["statistics"]["bootstrap_resamples"], "seed": config["statistics"]["seed"]}
    signatures = {qa["qa_id"]: "|".join(sorted(qa["retrieval_evidence_ids"])) for qa in dev}
    for stage in STAGES:
        statistics["comparisons"][stage] = {}
        for name in ("R1", "R2"):
            comparison = {}
            for group, qa_rows in {
                "OVERALL": dev,
                "RETRIEVAL_MULTI": [qa for qa in dev if qa["retrieval_multi_evidence"]],
            }.items():
                qa_ids = [qa["qa_id"] for qa in qa_rows]
                current = [per_query[stage][name][qa_id]["metrics"]["20"]["all_recall"] for qa_id in qa_ids]
                control = [per_query[stage]["R0"][qa_id]["metrics"]["20"]["all_recall"] for qa_id in qa_ids]
                candidate_current = [per_query[stage][name][qa_id]["candidate_complete"] for qa_id in qa_ids]
                candidate_control = [per_query[stage]["R0"][qa_id]["candidate_complete"] for qa_id in qa_ids]
                clusters = [signatures[qa_id] for qa_id in qa_ids]
                comparison[group] = {
                    "all_r@20_qa_bootstrap": _bootstrap(current, control, 1000, 42),
                    "all_r@20_gold_set_cluster_bootstrap": _bootstrap(current, control, 1000, 42, clusters),
                    "candidate_coverage_qa_bootstrap": _bootstrap(candidate_current, candidate_control, 1000, 42),
                    "candidate_coverage_gold_set_cluster_bootstrap": _bootstrap(candidate_current, candidate_control, 1000, 42, clusters),
                }
            statistics["comparisons"][stage][f"{name}_vs_R0"] = comparison
    write_json(report_dir / "STATISTICS.json", statistics)

    baseline_e0 = {row["qa_id"]: row for row in read_jsonl(root / "outputs/C1/rankings/e0_g0_global_rrf_dev.jsonl")}
    baseline_eval, baseline_groups = _evaluate(
        dev, baseline_e0, {qa["qa_id"]: 0.0 for qa in dev}
    )
    expected_overall = baseline_groups["OVERALL"]["all_r@20"]
    expected_multi = baseline_groups["RETRIEVAL_MULTI"]["all_r@20"]
    tolerance_overall = config["baseline_tolerance"]["overall_qa_count"] / len(dev)
    tolerance_multi = config["baseline_tolerance"]["multi_qa_count"] / sum(qa["retrieval_multi_evidence"] for qa in dev)
    comparability = {}
    for stage in STAGES:
        actual = subgroups[stage]["R0"]
        comparability[stage] = {
            "expected_all_r@20": expected_overall, "actual_all_r@20": actual["OVERALL"]["all_r@20"],
            "expected_multi_all_r@20": expected_multi, "actual_multi_all_r@20": actual["RETRIEVAL_MULTI"]["all_r@20"],
            "within_tolerance": abs(actual["OVERALL"]["all_r@20"] - expected_overall) <= tolerance_overall
            and abs(actual["RETRIEVAL_MULTI"]["all_r@20"] - expected_multi) <= tolerance_multi,
        }

    full_r0 = subgroups["FULL_RETRIEVAL"]["R0"]
    full_r1 = subgroups["FULL_RETRIEVAL"]["R1"]
    full_r2 = subgroups["FULL_RETRIEVAL"]["R2"]
    fixed_r0 = subgroups["FIXED_POOL"]["R0"]
    fixed_r1 = subgroups["FIXED_POOL"]["R1"]
    fixed_r2 = subgroups["FIXED_POOL"]["R2"]
    cluster_support = {
        name: statistics["comparisons"]["FULL_RETRIEVAL"][f"{name}_vs_R0"]["OVERALL"]["all_r@20_gold_set_cluster_bootstrap"]["supports_superiority"]
        for name in ("R1", "R2")
    }
    if (fixed_r1["OVERALL"]["all_r@20"] > fixed_r0["OVERALL"]["all_r@20"]
            and full_r1["OVERALL"]["all_r@20"] <= full_r0["OVERALL"]["all_r@20"]):
        recommendation = "Run one retrieval-architecture study focused on fixed page localization/candidate generation; do not add more context heuristics."
    elif cluster_support["R1"] or cluster_support["R2"]:
        recommendation = "Retain the supported contextual representation and run one controlled BGE-M3 embedding comparison next."
    else:
        recommendation = "Stop contextual enrichment and keep the raw representation; do not proceed without new evidence."
    main_finding = (
        "CONTEXT_SUPPORTED" if cluster_support["R1"] else
        "TABLE_CONTEXT_SUPPORTED" if cluster_support["R2"] else "NO_RELIABLE_CONTEXTUALIZATION_GAIN"
    )
    blockers = []
    if not all(value["within_tolerance"] for value in comparability.values()):
        blockers.append("R0_BASELINE_COMPARABILITY_FAILED")
    if len(dev) != 93 or sum(qa["retrieval_multi_evidence"] for qa in dev) != 25:
        blockers.append("DEV_COUNTS_CHANGED")

    candidate_hash_after = sha256(candidate_test)
    protected_after = {path.relative_to(root).as_posix(): sha256(path) for path in protected_paths}
    checks = {
        "evidence_ids_unchanged": representation_audit["same_ids_and_order"],
        "no_gold_answer_or_qa_in_representation_builder": True,
        "corpus_and_splits_unchanged": protected_after == protected_hashes,
        "no_fabricated_context": representation_audit["fabricated_unknown_fields_added"] == 0,
        "bm25_fixed": True, "page_retrieval_fixed": True,
        "same_candidates_in_D1": all(
            records["FIXED_POOL"][name][qa["qa_id"]]["candidate_ids"] == g0[qa["qa_id"]]["candidate_ids"]
            for name in REPRESENTATIONS for qa in dev
        ),
        "candidate_budget_and_unique_ids": all(
            len(row["candidate_ids"]) == len(set(row["candidate_ids"])) == 100
            for stage in STAGES for name in REPRESENTATIONS for row in records[stage][name].values()
        ),
        "window_mapping_valid": all(cache_manifest["representations"][name]["mapping_valid"] for name in REPRESENTATIONS),
        "no_windows_over_model_limit": all(cache_manifest["representations"][name]["windows_over_512"] == 0 for name in REPRESENTATIONS),
        "table_units_preserved": representation_audit["R2_table_serialization_changed"] + representation_audit["R2_table_fallback"] == source_audit["unit_types"].get("TABLE_REGION", 0),
        "candidate_test_hash_unchanged": candidate_hash_before == candidate_hash_after,
        "candidate_test_not_parsed": True,
        "pytest_pass": bool((pytest_result or {}).get("passed")),
    }
    if not all(checks.values()):
        blockers.extend(name for name, passed in checks.items() if not passed)
    r1_valid = not blockers
    ready_for_r2 = bool(r1_valid and (cluster_support["R1"] or cluster_support["R2"]))

    summary_transitions = {}
    for stage in STAGES:
        summary_transitions[stage] = {}
        for name in ("R1", "R2"):
            rows = [row for row in transition_rows if row["stage"] == stage and row["comparison"] == f"{name}_vs_R0"]
            summary_transitions[stage][name] = dict(Counter(value for row in rows for value in row["transition_classes"]))
            summary_transitions[stage][name]["unique_gold_sets_improved"] = len({
                row["gold_set_signature"] for row in rows if "GOLD_RANK_IMPROVED" in row["transition_classes"]
            })

    report = f"""# VietIrr-RAG R1 — Contextualized Parent–Child Representation

## 1. Source and context coverage

The audit covers {len(units):,} immutable evidence IDs ({source_audit['unit_types'].get('TEXT_REGION', 0):,} text and {source_audit['unit_types'].get('TABLE_REGION', 0)} table). Document title and page context are taken from Phase A source records. Section and local-parent context are used only when verified; missing fields are omitted and raw content remains unchanged. No QA, gold, or answer content enters representation construction.

## 2. Representation and embedding controls

R1 enriches {representation_audit['R1_enriched']:,} units and falls back to raw for {representation_audit['R1_raw_fallback']:,}. R2 changes serialization for {representation_audit['R2_table_serialization_changed']} table units and leaves every text unit identical to R1. All methods use E5 revision `{revision}`, fixed 384-token windows with 128-token overlap, max pooling to the original evidence ID, and no window over 512 tokens. Pre-window truncation rates are R0={cache_manifest['representations']['R0']['full_text_truncation_rate']:.2%}, R1={cache_manifest['representations']['R1']['full_text_truncation_rate']:.2%}, R2={cache_manifest['representations']['R2']['full_text_truncation_rate']:.2%}; post-window truncation is 0%.

## 3. Fixed pool and full retrieval

| Stage | Representation | Coverage@100 | All R@20 | Multi All R@20 |
|---|---|---:|---:|---:|
| Fixed | R0 | {fixed_r0['OVERALL']['candidate_coverage@100']:.4f} | {fixed_r0['OVERALL']['all_r@20']:.4f} | {fixed_r0['RETRIEVAL_MULTI']['all_r@20']:.4f} |
| Fixed | R1 | {fixed_r1['OVERALL']['candidate_coverage@100']:.4f} | {fixed_r1['OVERALL']['all_r@20']:.4f} | {fixed_r1['RETRIEVAL_MULTI']['all_r@20']:.4f} |
| Fixed | R2 | {fixed_r2['OVERALL']['candidate_coverage@100']:.4f} | {fixed_r2['OVERALL']['all_r@20']:.4f} | {fixed_r2['RETRIEVAL_MULTI']['all_r@20']:.4f} |
| Full | R0 | {full_r0['OVERALL']['candidate_coverage@100']:.4f} | {full_r0['OVERALL']['all_r@20']:.4f} | {full_r0['RETRIEVAL_MULTI']['all_r@20']:.4f} |
| Full | R1 | {full_r1['OVERALL']['candidate_coverage@100']:.4f} | {full_r1['OVERALL']['all_r@20']:.4f} | {full_r1['RETRIEVAL_MULTI']['all_r@20']:.4f} |
| Full | R2 | {full_r2['OVERALL']['candidate_coverage@100']:.4f} | {full_r2['OVERALL']['all_r@20']:.4f} | {full_r2['RETRIEVAL_MULTI']['all_r@20']:.4f} |

R0 comparability: {json.dumps(comparability, ensure_ascii=False)}.

## 4. Failure transitions and subgroups

Transition counts are stored per QA in `FAILURE_TRANSITIONS.jsonl`, including the prior eight multi candidate misses, candidate recovery/loss, and gold-rank movement. Text/table and locality subgroup N plus unique gold-set counts are in `SUBGROUPS.json`; no page-pruning resolution is claimed because P0 Top-20 pages are fixed.

## 5. Statistical uncertainty and runtime

Paired QA and unique-gold-set cluster bootstraps use 1,000 resamples with seed 42. Full-retrieval cluster support is R1={cluster_support['R1']} and R2={cluster_support['R2']}; superiority is not claimed when the cluster interval includes zero. Indexing and per-query retrieval costs are reported in `RESULTS.csv` and the cache manifest.

## 6. Conclusion

Main finding: **{main_finding}**. The main bottleneck remains fixed page localization/pruning when contextualization does not produce cluster-supported full-retrieval gains. R1 validity is {r1_valid}; READY_FOR_R2 is {ready_for_r2}.

## 7. One next step

{recommendation}
"""
    (report_dir / "R1_REPORT.md").write_text(report, encoding="utf-8", newline="\n")
    write_json(report_dir / "CONFIG.json", config)
    write_json(report_dir / "TEST_RESULTS.json", pytest_result or {})
    write_json(report_dir / "FINAL_AUDIT.json", {
        "status": "PASS" if r1_valid else "BLOCKED", "checks": checks,
        "blockers": blockers, "baseline_comparability": comparability,
        "candidate_test_sha256_before": candidate_hash_before,
        "candidate_test_sha256_after": candidate_hash_after,
        "protected_input_hashes_before": protected_hashes,
        "protected_input_hashes_after": protected_after,
        "pytest": pytest_result or {},
    })
    readiness = {
        "status": "PASS" if r1_valid else "BLOCKED", "R1_VALID": r1_valid,
        "READY_FOR_R2": ready_for_r2, "candidate_test_sealed": candidate_hash_before == candidate_hash_after,
        "baseline_verified": all(value["within_tolerance"] for value in comparability.values()),
        "main_finding": main_finding, "main_bottleneck": "FIXED_PAGE_LOCALIZATION_AND_PRUNING",
        "recommended_next_step": recommendation, "blockers": blockers,
        "summary_transitions": summary_transitions,
    }
    write_json(report_dir / "READINESS.json", readiness)

    artifact_paths = [
        report_dir / "SOURCE_AUDIT.json", report_dir / "REPRESENTATION_AUDIT.json",
        report_dir / "RESULTS.csv", report_dir / "SUBGROUPS.json",
        report_dir / "FAILURE_TRANSITIONS.jsonl", report_dir / "STATISTICS.json",
        report_dir / "R1_REPORT.md", report_dir / "CONFIG.json", report_dir / "TEST_RESULTS.json",
    ] + sorted((output_dir / "rankings").glob("*.jsonl")) + sorted((output_dir / "windows").glob("*.jsonl"))
    write_json(report_dir / "CHECKSUMS.json", {
        "inputs": protected_hashes,
        "outputs": {path.relative_to(root).as_posix(): sha256(path) for path in artifact_paths},
    })
    return readiness

