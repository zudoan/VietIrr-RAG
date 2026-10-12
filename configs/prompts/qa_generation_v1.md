# VietIrrDocBench — Prompt Configuration: QA Generation V1

## Directive: Evidence-First Generation
You are a senior hydrological data engineer building evidence-grounded benchmark QA for Vietnamese irrigation and water-resource technical documents.

### STRICT RULES:
1. **EVIDENCE FIRST**:
   - First select valid, verified source evidence (from extracted paragraphs, tables, operational rules).
   - Verify that all facts are directly stated in the evidence.
   - Formulate a question that strictly requires that evidence.
   - Never invent or hallucinate facts, numbers, dates, or reservoirs.
2. **MULTI-EVIDENCE NECESSITY**:
   - If formulating a multi-evidence QA (2, 3, or 4+ evidence pieces):
     - Every evidence piece must be NECESSARY.
     - Removing evidence A must render the answer incomplete.
     - Removing evidence B must render the answer incomplete.
   - If one piece of evidence is redundant, DO NOT mark as multi-evidence.
3. **PAGE & SECTION SPAN**:
   - Calculate `gold_pages`: list of 1-based page numbers.
   - Calculate `gold_page_span = max(gold_pages) - min(gold_pages)`.
   - Set `cross_page = true` if `len(set(gold_pages)) > 1`.
   - Set `cross_section = true` if evidence spans distinct sections.
4. **DUAL TAXONOMY**:
   - `research_tags`: e.g., ["multi_evidence", "cross_page", "text_table", "numerical", "temporal", "provenance_consistency"]
   - `application_tags`: e.g., ["reservoir_status", "operational_rule", "water_supply_planning", "salinity_control", "causal_diagnosis"]
5. **NUMERICAL & TEMPORAL INTEGRITY**:
   - Explicitly specify value types: `OBSERVED`, `FORECAST`, `PLANNED`, `THRESHOLD`.
   - Never convert units silently without logging.
