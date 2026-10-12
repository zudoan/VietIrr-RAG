from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from viirr_retrieval.io_utils import read_jsonl, sha256, write_json


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/MAR_ER_EXPERIMENT"


def _mapping(path: Path) -> dict[str, dict]:
    return {row["qa_id"]: row for row in read_jsonl(path)}


def main() -> int:
    REPORT.mkdir(parents=True, exist_ok=True)
    official_outputs = [
        ROOT / "outputs/MAR_ER/rankings/m4_dev.jsonl",
        REPORT / "RESULTS.csv",
        REPORT / "READINESS.json",
    ]
    errors: list[str] = []
    if any(path.exists() for path in official_outputs):
        errors.append("one_shot_outputs_already_exist")

    config_path = ROOT / "configs/mar_er.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    dev = read_jsonl(ROOT / "data/benchmark/dev.jsonl")
    units = read_jsonl(ROOT / "data/processed/evidence_units.jsonl")
    unit_by_id = {row["evidence_id"]: row for row in units}
    pages = {row["page_id"] for row in read_jsonl(ROOT / "data/parsed/pages.jsonl")}
    signatures = {"|".join(sorted(qa["retrieval_evidence_ids"])) for qa in dev}
    multi_signatures = {
        "|".join(sorted(qa["retrieval_evidence_ids"]))
        for qa in dev if qa["retrieval_multi_evidence"]
    }
    counts = {
        "retrieval_units": len(units),
        "text_units": sum(row["unit_type"] == "TEXT_REGION" for row in units),
        "table_units": sum(row["unit_type"] == "TABLE_REGION" for row in units),
        "dev_qa": len(dev),
        "retrieval_multi_qa": sum(bool(qa["retrieval_multi_evidence"]) for qa in dev),
        "unique_gold_sets": len(signatures),
        "multi_unique_gold_sets": len(multi_signatures),
    }
    if counts != config["expected_counts"]:
        errors.append("expected_counts_mismatch")

    mapping_checks = {
        "unique_evidence_ids": len(unit_by_id) == len(units),
        "all_parent_pages_exist": all(row["page_id"] in pages for row in units),
        "all_dev_gold_ids_exist": all(
            item in unit_by_id for qa in dev for item in qa["retrieval_evidence_ids"]
        ),
        "dev_gold_page_mapping_valid": all(
            {unit_by_id[item]["page_id"] for item in qa["retrieval_evidence_ids"]}
            == set(qa["gold_page_ids"]) for qa in dev
        ),
    }
    errors.extend(name for name, passed in mapping_checks.items() if not passed)

    baseline = _mapping(ROOT / "outputs/MASH_ER/rankings/a0_dev.jsonl")
    page_rankings = _mapping(ROOT / "outputs/B2_1/rankings/p0_pages_dev_top100.jsonl")
    page_region = _mapping(ROOT / config["retrieval"]["page_region_source"])
    qa_ids = {qa["qa_id"] for qa in dev}
    baseline_checks = {
        "qa_ids_match": set(baseline) == qa_ids,
        "all_baseline_candidates_unique_100": all(
            len(row["candidate_ids"]) == len(set(row["candidate_ids"])) == 100
            for row in baseline.values()
        ),
        "all_baseline_ids_known": all(
            item in unit_by_id for row in baseline.values() for item in row["candidate_ids"]
        ),
        "page_rankings_cover_dev": set(page_rankings) == qa_ids,
        "page_region_source_covers_dev": set(page_region) == qa_ids,
        "page_region_has_100": all(len(row["results"]) >= 100 for row in page_region.values()),
    }
    errors.extend(name for name, passed in baseline_checks.items() if not passed)

    mash_baseline = json.loads(
        (ROOT / "reports/MASH_ER/BASELINE_VERIFICATION.json").read_text(encoding="utf-8")
    )
    if mash_baseline.get("status") != "PASS":
        errors.append("upstream_mash_baseline_not_verified")
    candidate_path = ROOT / "data/benchmark/candidate_test.jsonl"
    candidate_hash = sha256(candidate_path)
    if candidate_hash != mash_baseline["candidate_test"]["sha256_after"]:
        errors.append("candidate_test_hash_changed_since_mash")

    view_manifest = read_jsonl(ROOT / "outputs/MASH_ER/views/view_manifest.jsonl")
    representation_checks = {
        "view_manifest_count": len(view_manifest) == len(units),
        "view_manifest_id_order": [row["evidence_id"] for row in view_manifest]
        == [row["evidence_id"] for row in units],
        "view_manifest_no_gold": not any(row["gold_answer_or_qa_used"] for row in view_manifest),
        "alternate_fallback_consistent": not any(
            row["alternate_valid"] and row["fallback_to_raw"] for row in view_manifest
        ),
    }
    errors.extend(name for name, passed in representation_checks.items() if not passed)

    cache_references = json.loads(
        (ROOT / "outputs/MASH_ER/cache/CACHE_REFERENCES.json").read_text(encoding="utf-8")
    )
    cache_checks = {}
    for name in ("raw", "text_context", "table_struct"):
        reference = cache_references[name]
        path = ROOT / reference["embedding"]
        cache_checks[f"{name}_exists"] = path.exists()
        cache_checks[f"{name}_sha256"] = path.exists() and sha256(path) == reference["sha256"]
    errors.extend(name for name, passed in cache_checks.items() if not passed)
    raw_windows = read_jsonl(ROOT / "outputs/R1/windows/r0_window_map.jsonl")
    context_windows = read_jsonl(ROOT / "outputs/R1/windows/r1_window_map.jsonl")
    table_windows = read_jsonl(ROOT / "outputs/MASH_ER/windows/table_struct_window_map.jsonl")
    window_checks = {
        "raw_window_count_matches": len(raw_windows)
        == np.load(ROOT / config["windowing"]["raw_cache"], mmap_mode="r").shape[0],
        "context_window_count_matches": len(context_windows)
        == np.load(ROOT / config["windowing"]["text_context_cache"], mmap_mode="r").shape[0],
        "table_window_count_matches": len(table_windows)
        == np.load(ROOT / config["windowing"]["table_struct_cache"], mmap_mode="r").shape[0],
    }
    errors.extend(name for name, passed in window_checks.items() if not passed)

    design_checks = {
        "candidate_budget_100": config["retrieval"]["candidate_budget"] == 100,
        "candidate_anchor_80": config["retrieval"]["candidate_anchor"] == 80,
        "rescue_quota_20": config["retrieval"]["rescue_quota"] == 20,
        "final_k_20": config["retrieval"]["final_k"] == 20,
        "intrusion_budget_5": config["retrieval"]["intrusion_budget"] == 5,
        "protected_top15": config["retrieval"]["protected_top_k"] == 15,
        "rrf_k_60": config["retrieval"]["rrf_k"] == 60,
        "one_shot": config["one_shot"] is True,
        "no_post_result_change": config["post_result_parameter_changes_allowed"] is False,
    }
    errors.extend(name for name, passed in design_checks.items() if not passed)

    compared = {}
    baseline_ids = {qa_id: row["candidate_ids"] for qa_id, row in baseline.items()}
    for label, path in {
        "LEGACY_E0": ROOT / "outputs/C1/rankings/e0_g0_global_rrf_dev.jsonl",
        "R1_R0": ROOT / "outputs/R1/rankings/full_retrieval_r0_dev.jsonl",
        "PAGE_REGION_P0_P20": ROOT / config["retrieval"]["page_region_source"],
    }.items():
        rows = _mapping(path)
        exact100 = 0
        exact20 = 0
        overlap = []
        for qa_id in qa_ids:
            other = rows[qa_id].get("candidate_ids") or [
                item["evidence_id"] for item in rows[qa_id]["results"]
            ]
            exact100 += baseline_ids[qa_id][:100] == other[:100]
            exact20 += baseline_ids[qa_id][:20] == other[:20]
            overlap.append(len(set(baseline_ids[qa_id][:20]) & set(other[:20])) / 20)
        compared[label] = {
            "exact_top100_queries": int(exact100),
            "exact_top20_queries": int(exact20),
            "mean_top20_overlap": float(np.mean(overlap)),
            "matched_control": False,
        }

    protected_inputs = [
        "configs/mar_er.json",
        "reports/MAR_ER_DESIGN/METHOD_SPEC.md",
        "reports/MAR_ER_DESIGN/EXPERIMENT_PLAN.md",
        "reports/MAR_ER_DESIGN/RESEARCH_READINESS.md",
        "data/benchmark/dev.jsonl",
        "data/processed/evidence_units.jsonl",
        "data/parsed/pages.jsonl",
        "outputs/B2/cache/bm25_regions.pkl",
        "outputs/B2_1/rankings/p0_pages_dev_top100.jsonl",
        config["retrieval"]["page_region_source"],
        "outputs/MASH_ER/rankings/a0_dev.jsonl",
        "outputs/MASH_ER/views/view_manifest.jsonl",
        "outputs/R1/windows/r0_window_map.jsonl",
        "outputs/R1/windows/r1_window_map.jsonl",
        "outputs/MASH_ER/windows/table_struct_window_map.jsonl",
        config["windowing"]["raw_cache"],
        config["windowing"]["text_context_cache"],
        config["windowing"]["table_struct_cache"],
    ]
    source_files = [
        "src/viirr_retrieval/mar_er.py",
        "scripts/preflight_mar_er.py",
        "scripts/run_mar_er.py",
        "scripts/audit_mar_er.py",
        "scripts/recompute_mar_er_metrics.py",
        "scripts/package_mar_er.py",
        "tests/test_mar_er.py",
    ]
    for relative in source_files:
        if not (ROOT / relative).exists():
            errors.append(f"missing_source:{relative}")
    hashes = {
        relative: sha256(ROOT / relative)
        for relative in protected_inputs + source_files if (ROOT / relative).exists()
    }
    preflight = {
        "status": "PASS" if not errors else "BASELINE_BLOCKED",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "mapping_checks": mapping_checks,
        "baseline_checks": baseline_checks,
        "representation_checks": representation_checks,
        "cache_checks": cache_checks,
        "window_checks": window_checks,
        "design_checks": design_checks,
        "legacy_difference_audit": compared,
        "matched_baseline_source": "outputs/MASH_ER/rankings/a0_dev.jsonl",
        "matched_baseline_reproduction_pending_official_query_scoring": True,
        "candidate_test": {
            "policy": config["candidate_test_policy"],
            "parsed": False,
            "sha256": candidate_hash,
        },
        "errors": errors,
    }
    write_json(REPORT / "PREFLIGHT.json", preflight)
    if errors:
        print(json.dumps(preflight, indent=2))
        return 1
    frozen = {
        "status": "FROZEN_BEFORE_OFFICIAL_M0_M4_RUN",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "hashes": hashes,
        "protected_inputs": protected_inputs,
        "source_files": source_files,
        "candidate_test_sha256": candidate_hash,
        "protocol": {
            "methods": ["M0", "M1", "M2", "M3", "M4"],
            "official_runs_allowed": 1,
            "post_result_tuning": False,
            "bootstrap_resamples": 1000,
            "seed": 42,
        },
    }
    write_json(REPORT / "FROZEN_CONFIG.json", frozen)
    print(json.dumps({
        "status": preflight["status"], "counts": counts,
        "candidate_test_sha256": candidate_hash,
        "frozen_config_sha256": sha256(REPORT / "FROZEN_CONFIG.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
