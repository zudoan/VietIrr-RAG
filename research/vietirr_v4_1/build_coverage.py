"""Generate evidence-driven V4.1 domain/use-case and gap matrices."""
from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent


def write(name: str, fields: list[str], rows: list[dict]) -> None:
    with (HERE / name).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


BASE = {
    "provenance": "V4.0 coverage matrix + V4.1 screened PDFs; Candidate Test excluded",
    "knowledge_coverage_rule": "Counts do not establish support; every status is based on named evidence dependencies.",
}

ROWS = [
    ("D01", "Facility/system identity", "UC01", "Hà Nam; Nam Định", "Bắc Nam Hà", "official procedure+inventory tables", "2025", "V4_CTTL_2025_77c60f84", "facility list, system scope, irrigation/drainage maps", "item-level identity review", "PARTIALLY_SUPPORTED", "P1"),
    ("D01", "Facility/system identity", "UC01", "Mekong delta", "Cái Lớn–Cái Bé", "draft procedure+appendices", "2024", "V4_CTTL_2024_dda51c21", "facility clusters, monitoring-control points, maps", "effective final procedure; human identity review", "PARTIALLY_SUPPORTED", "P1"),
    ("D01", "Maintenance/current condition", "UC01", "National", "named facility", "inspection/condition dossier", "current", "", "none eligible", "facility-specific current inspection", "UNSUPPORTED", "P2"),
    ("D02", "Irrigation-system operation", "UC02", "Hà Nam; Nam Định", "Bắc Nam Hà", "signed current procedure", "2025", "V4_CTTL_2025_77c60f84", "conditions, actions, responsibilities, replacement chain", "clause-level human legal review", "PARTIALLY_SUPPORTED", "P0"),
    ("D02", "Draft operation/version resolution", "UC14", "Mekong delta", "Cái Lớn–Cái Bé", "official draft+legacy temporary decision metadata", "2021–2024", "V4_CTTL_2024_dda51c21", "draft text explicitly lacks signed decision number/date", "final/effective act and verified supersession chain", "FRAGMENTED", "P0"),
    ("D02+D03", "Rule-observation alignment", "UC03", "Hà Nam; Nam Định", "Bắc Nam Hà", "procedure+seasonal forecast/plan", "2021 vs 2025", "V4_CTTL_2025_77c60f84;V4_IWRP_2021_3031564c", "typed thresholds and historical values exist", "same-period applicable rule or explicit historical rule text", "FRAGMENTED", "P0"),
    ("D03", "Observed value", "UC04", "multiple", "monitoring stations", "bulletin table", "2018–2026", "40 legacy mapped docs", "many accepted bulletins", "typed observation time/role at locator level", "PARTIALLY_SUPPORTED", "P1"),
    ("D03", "Forecast with horizon", "UC05", "multiple", "basins/systems", "forecast bulletin", "2018–2026", "37 legacy forecast docs;V4_IWRP_2021_3031564c", "issue/target windows in source", "locator-level role and time review", "PARTIALLY_SUPPORTED", "P1"),
    ("D03", "Comparable time series", "UC06", "multiple", "same station/system", "aligned observations/forecasts", "multi-period", "legacy families", "candidate series", "verified entity+metric+unit+method+time alignment", "FRAGMENTED", "P1"),
    ("D04", "Irrigation demand and delivery plan", "UC07", "Hà Nam; Nam Định", "Bắc Nam Hà", "seasonal water-use plan", "Đông Xuân 2020–2021", "V4_IWRP_2021_3031564c", "demand, pumping facilities, delivery releases, served area", "human table-cell review; distinguish plan from actual", "PARTIALLY_SUPPORTED", "P0"),
    ("D04", "Plan-versus-actual delivery", "UC08", "any", "irrigation system", "plan+actual operation log", "same period", "", "plan sources only", "verified actual delivery/outcome log", "UNSUPPORTED", "P1"),
    ("D04", "Drainage outcome", "UC07", "any", "drainage system", "operation log+impact record", "event/season", "", "procedures but no aligned outcome", "actual drainage operations and outcome", "UNSUPPORTED", "P2"),
    ("D05", "Water-quality measurement", "UC09", "five Mekong provinces", "Cái Lớn–Cái Bé", "monitoring/forecast tables", "2025", "IRR_CTL_2025_c3d033a0;IRR_CTL_2025_57989573", "parameter/station/date tables", "human cell/header inheritance review", "PARTIALLY_SUPPORTED", "P1"),
    ("D05", "Quality standard comparison", "UC10", "multiple", "irrigation system", "measurement+applicable standard", "aligned", "29 legacy quality docs", "measurements and some source classifications", "current applicable standard/method/class relation", "FRAGMENTED", "P0"),
    ("D06", "Seasonal safety duties", "UC12", "National", "dikes/dams/irrigation works", "ministerial directive", "2025 rainy season", "V4_BNNMT_2025_594e7382", "inspection/preparedness/reporting duties", "scope/application human review; not facility condition", "PARTIALLY_SUPPORTED", "P1"),
    ("D06", "Facility-specific dam safety", "UC12", "any", "named dam/reservoir", "current inspection+valid rule", "current", "", "general directive only", "facility inspection/condition dossier", "UNSUPPORTED", "P0"),
    ("D06", "Drought/shortage scenario", "UC11", "Hà Nam; Nam Định", "Bắc Nam Hà", "seasonal official forecast/plan", "2020–2021", "V4_IWRP_2021_3031564c", "scenario and at-risk area", "locator-level numeric review", "PARTIALLY_SUPPORTED", "P1"),
    ("ANY", "Insufficient evidence detection", "UC13", "all", "all", "manifest+evidence contract", "all", "V4_CORPUS_MANIFEST", "explicit missing dependencies", "human review of business realism", "SUPPORTED", "P0"),
]


def main() -> None:
    fields = ["domain", "subdomain", "use_case", "geography", "facility", "evidence_type", "time", "available_documents",
              "available_evidence", "missing_dependency", "coverage_status", "priority", "provenance", "knowledge_coverage_rule"]
    rows = []
    for values in ROWS:
        row = dict(zip(fields[:12], values)); row.update(BASE); rows.append(row)
    write("DOMAIN_USE_CASE_MATRIX.csv", fields, rows)

    gaps = [
        ("G01", "P1", "Verified facility inventory and hierarchy", "D01/UC01", "Current official inventory/dossier with system membership", "Identity anchors all downstream QA", "Named IDs and membership reviewed", "PARTIALLY_ADDRESSED", "V4_CTTL_2025_77c60f84;V4_CTTL_2024_dda51c21"),
        ("G02", "P0", "Applicable operation rule and version chain", "D02/UC02/UC14", "Signed act, full procedure, amendment/replacement chain", "Wrong version creates unsafe answers", "Clause+version+effectivity human reviewed", "PARTIALLY_ADDRESSED", "Bắc Nam Hà current act added; CLCB remains draft"),
        ("G03", "P0", "Verified cross-document relations", "cross-source", "Explicit relation evidence and human decision", "Blocks legitimate multi-document QA", "Relation status VERIFIED_FOR_GOLD", "OPEN", "2 candidate packs, 0 gold relations"),
        ("G04", "P0", "Irrigation demand/allocation/delivery", "D04/UC07", "Plan plus actual delivery for same system/period", "Core applied irrigation need", "Plan and actual matched in compatible units", "PARTIALLY_ADDRESSED", "Bắc Nam Hà historical plan added; actual missing"),
        ("G05", "P1", "Forecast/observation time roles", "D03/UC04–06", "Typed issue, target and observation timestamps", "Prevents temporal category errors", "Each fact has reviewed time role", "OPEN", "Source exists; tuple review missing"),
        ("G06", "P0", "Facility-specific safety/maintenance", "D06/UC12", "Inspection, condition, incident and emergency plan", "High consequence use case", "Current named-facility inspection and applicable duty", "PARTIALLY_ADDRESSED", "General 2025 directive added; facility condition still missing"),
        ("G07", "P0", "Water-quality standard applicability", "D05/UC10", "Current standard, class, method and station relation", "Prevents false compliance conclusion", "Rule+measurement relation reviewed", "OPEN", "Monitoring rich; legal/method relation fragmented"),
        ("G08", "P1", "Comparable time series", "D03/D05/UC06", "Same entity, metric, method, unit, aligned periods", "Needed for true temporal comparison", "At least 2 verified comparable facts", "OPEN", "Candidate families only"),
        ("G09", "P0", "Evidence tuple and QA human review", "all", "Tier-1 evidence and Tier-2 QA decisions", "Auto checks cannot establish semantic gold", "Named reviewer decisions per released QA", "OPEN", "0 V4.1 QA human accepted"),
        ("G10", "P2", "Geographic/system balance", "all", "Verified sources beyond dominant bulletin families", "Avoids misleading national coverage", "Coverage by actual verified hierarchy", "PARTIALLY_ADDRESSED", "Bắc Nam Hà added; south remains dominant"),
    ]
    gf = ["gap_id", "priority", "gap", "affected_cells", "evidence_needed", "rationale", "exit_criterion", "status", "evidence"]
    write("CORPUS_GAP_PRIORITY.csv", gf, [dict(zip(gf, x)) for x in gaps])
    print(f"domain_rows={len(rows)} gaps={len(gaps)}")


if __name__ == "__main__":
    main()
