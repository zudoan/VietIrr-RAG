# V4.2 Baseline Reconciliation

- V4.1 corpus manifest: 93 records (89 immutable legacy references + 4 V4.1 additions).
- V4.1 raw pilot: 10 records, unchanged.
- Full-workspace V4.1 adversarial suite: 16/16 caught; independent audit: 34/34.
- Standalone extraction of the old V4.1 review bundle: only 2/16 caught because required source files were absent. Test 13 consequently reached `SOURCE_UNREADABLE` instead of proving wrong-fact detection.
- V4.2 remedy: a checksum-bound minimal source fixture is shipped with the tests. Test 13 now asserts both `FACT_VALUE_NOT_FOUND` and absence of `SOURCE_UNREADABLE`.
- Candidate Test: sealed, not opened, not hashed.

V4.1 data and code were not overwritten. `V4_2_INPUT_FREEZE.json` seals all readable inputs used by this phase.
