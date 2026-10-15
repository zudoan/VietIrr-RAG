# V4.3 Adversarial and Mutation Test Report

Result: **18/18 passed**.

| Test | Category | Result |
|---|---|---|
| `baseline_valid` | positive | PASS |
| `fixtures_cover_bank` | positive | PASS |
| `all_calculations_reproduce` | positive | PASS |
| `ledger_starts_empty` | positive | PASS |
| `review_data_real` | positive | PASS |
| `deep_review_18` | positive | PASS |
| `mutation_missing_dossier_caught` | mutation | PASS |
| `mutation_invalid_machine_status_caught` | mutation | PASS |
| `mutation_fabricated_gold_caught` | mutation | PASS |
| `mutation_fabricated_human_caught` | mutation | PASS |
| `mutation_qa026_false_pass_caught` | mutation | PASS |
| `mutation_qa036_extra_evidence_caught` | mutation | PASS |
| `mutation_revision_lineage_caught` | mutation | PASS |
| `mutation_rejected_audit_row_loss_caught` | mutation | PASS |
| `mutation_invalid_page_detected` | mutation | PASS |
| `mutation_source_hash_detected` | mutation | PASS |
| `candidate_test_absent` | adversarial | PASS |
| `no_reviewed_prefill` | adversarial | PASS |

Tests cover source/dossier completeness, calculation reproducibility, false gold/human labels, QA-026 completeness, QA-036 minimality, revision lineage, rejected-QA retention and Candidate Test exclusion.
