"""Reclassify accepted V3 documents for the V3.1 scientific-validity repair."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TRUE_CORE_LONG = {
    # Official inter-reservoir operating procedures and amendment.
    "IRR_CP_2019_ee0bca33", "IRR_CP_2025_2d3e4a1e", "IRR_CP_2019_4886b4cb",
    "IRR_CP_2019_89661cdf", "IRR_CP_2019_e417f65d", "IRR_CP_2019_e4f9044f",
    "IRR_CP_2018_b4331af5",
    # Long annual water-quality/resource assessments.
    "IRR_CTL_2024_9a520097", "IRR_CTL_2024_9c1d87a6",
    # Seasonal water-use/supply plans (not routine weekly bulletins).
    "IRR_CTL_2025_c049b8bb", "IRR_CTL_2025_dee3c4a4",
    # Structured operational/regulatory/resource documents.
    "IRR_GOV_2023_29fb8ed6", "IRR_GOV_2021_b37b0316", "IRR_GOV_2021_7063d2bd",
    "IRR_GOV_2024_7f8a5df6", "IRR_GOV_2026_2b689fe4",
}

SUPPORTING_REFERENCE = {
    "IRR_GOV_2015_b1eee844",   # broad climate assessment
    "IRR_GOV_2013_78d34d5c",   # strategy monitoring framework
    "IRR_GOV_UNKNOWN_08a6c46e", # historical dike reference
    "IRR_GOV_2005_7f8ee792",   # generic community disaster manual
}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def classify(doc: dict) -> tuple[str, str, float]:
    doc_id = doc["doc_id"]
    title = doc.get("title", "")
    if doc_id in TRUE_CORE_LONG:
        if doc_id.startswith("IRR_CP_"):
            return "core_long", "Official inter-reservoir operating procedure or verified amendment.", 0.99
        if doc_id in {"IRR_CTL_2024_9a520097", "IRR_CTL_2024_9c1d87a6"}:
            return "core_long", "Long annual irrigation-system water-quality assessment with structured analysis.", 0.98
        if doc_id in {"IRR_CTL_2025_c049b8bb", "IRR_CTL_2025_dee3c4a4"}:
            return "core_long", "Seasonal regional water-use/supply plan with structured resource and demand tables.", 0.96
        return "core_long", "Structured operational, regulatory, water-resource, or water-supply assessment document.", 0.94
    if doc_id in SUPPORTING_REFERENCE:
        return "supporting_reference", "Relevant background/reference material but not a primary irrigation operational or water-resource benchmark document.", 0.94
    return "temporal", f"Time-bounded bulletin, monitoring update, forecast, notice, or routine report: {title[:90]}", 0.96


def main() -> None:
    source = read_jsonl(ROOT / "data" / "parsed" / "documents.jsonl")
    accepted = [doc for doc in source if doc.get("acceptance_status") == "ACCEPT"]
    audit_rows = []
    versioned_docs = []
    for doc in accepted:
        new_type, reason, confidence = classify(doc)
        audit_rows.append({
            "doc_id": doc["doc_id"], "title": doc.get("title"),
            "old_type": doc.get("core_or_temporal"), "new_type": new_type,
            "reason": reason, "confidence": confidence,
        })
        updated = dict(doc)
        updated["v3_0_document_type"] = doc.get("core_or_temporal")
        updated["document_type_v3_1"] = new_type
        updated["document_type_audit_reason"] = reason
        updated["document_type_audit_confidence"] = confidence
        versioned_docs.append(updated)

    out_meta = ROOT / "data" / "v3_1" / "metadata"
    write_jsonl(out_meta / "documents.jsonl", versioned_docs)
    write_jsonl(out_meta / "document_type_audit.jsonl", audit_rows)
    counts = Counter(row["new_type"] for row in audit_rows)
    changed = sum(row["old_type"] != row["new_type"] for row in audit_rows)
    audit = {
        "accepted_documents": len(accepted), "counts": dict(counts),
        "changed_from_v3": changed, "records": audit_rows,
        "policy": "content-role classification; no target-count forcing",
    }
    reports = ROOT / "reports" / "v3_1"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "document_type_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# V3.1 Document Type Audit", "",
        "Classification was based on document role and content, not a quota.", "",
        f"- Accepted documents: {len(accepted)}",
        f"- True core-long: {counts['core_long']}",
        f"- Temporal: {counts['temporal']}",
        f"- Supporting reference: {counts['supporting_reference']}",
        f"- Other: {counts['other']}",
        f"- Labels changed from V3: {changed}", "",
        "| doc_id | old type | new type | confidence | reason |", "|---|---|---|---:|---|",
    ]
    for row in audit_rows:
        lines.append(f"| {row['doc_id']} | {row['old_type']} | {row['new_type']} | {row['confidence']:.2f} | {row['reason']} |")
    (reports / "01_document_type_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": len(accepted), "counts": dict(counts), "changed": changed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
