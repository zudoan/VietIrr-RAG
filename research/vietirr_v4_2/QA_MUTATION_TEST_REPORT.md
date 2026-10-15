# QA Mutation Test Report

The V4.2 suite ran **16** required adversarial mutations; **16** were caught and all produced non-default behavior. Test 13 uses `fixtures/SOURCE_FIXTURE_FACT_VALUE.json`, detected `FACT_VALUE_NOT_FOUND`, and explicitly did not emit `SOURCE_UNREADABLE`.

Covered failures include shallow intent, unknown/out-of-set evidence, duplicate evidence IDs, unsupported components, wrong arithmetic, fake comparison/multi-document labels, non-ground-up lineage, wrong generation order, invalid human acceptance, candidate leakage, and paraphrase duplication.
