# VietIrr-RAG Phase C1.2

## 1. Baseline verification

Artifact recomputation passes: 93 Dev QA, 25 retrieval-multi QA, 8 unique multi gold sets, and G0/B100 has complete candidates for 17/25 multi QA. E0/E2/E4 All R@20 are 0.6237, 0.6452, and 0.6559; multi All R@20 is 0.6000, 0.4400, and 0.6000. Candidate Test was byte-hashed only.

## 2. Metadata and time representation

C1.1 marked 9300/9300 occurrences metadata-known because region/report fields counted. It marked 661 evidence-time occurrences, but only 390 contain a real raw/start/end value. C1.2 retains exactly 390 source-valid time occurrences and separates them into evidence versus forecast time; empty time objects are MISSING and region type is not structured metadata. Coverage is reported separately for 1332 unique evidence IDs and 9300 occurrences.

## 3. Requirements and roles

Temporal-comparison predictions fall from 6 to 0; 10 questions are explicitly labeled reference comparisons instead. The deterministic 30-QA queue includes question predictions, top-E0 evidence locators, rule-based roles, reasons, and ambiguity. It is not human-validated and no role-accuracy claim is made.

## 4. Missing multi-evidence diagnosis

All 8 missing units across 8 QA were traced through P0/P2 pages, BM25/E5, flat Top-200, G0/G1, and available B2.2 pools. Primary causes are {'PAGE_PRUNING': 6, 'PAGE_LOCALIZATION_MISS': 2}. Secondary representation-source absence occurs for 2 text-query occurrences. The failures cover 4 unique gold sets and 3 document families. P2 rescues 1 page at the operational Top-20 cutoff and discovers 2 pages absent from P0 Top-100, but those remain outside P2 Top-20.

## 5. Candidate recovery opportunities

All 8/8 missing units occur in at least one existing ranking/pool. The best fixed existing candidate pool is G1 with 21/25 complete multi QA. The union of existing artifacts reaches 25/25, but this is a diagnostic oracle ceiling, not a deployable method and not a measured improvement.

## 6. Limitations

Only 8 unique multi gold sets exist. Gold is used solely after retrieval for failure accounting. Metadata and evidence roles lack verified reference labels; source-quality fields are GOOD for the four unique missing evidence units, so OCR/metadata is not claimed as a causal root. No ranking, candidate ID, model, corpus, or split was changed.

## 7. One next research step

Run one controlled high-recall candidate-generation study at fixed B100 using existing P0/P2/flat signals; do not build provenance-aware selection until structured metadata is validated. READY_FOR_C2 remains false because candidate recall is unresolved and provenance metadata is not sufficiently validated for a more complex selector.
