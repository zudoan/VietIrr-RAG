# V4.4 mandatory test report

Result: **22/22 passed**.

| ID | Case | Fixture | Result |
|---|---|---|---|
| C01 | corpus document missing | synthetic_negative | PASS |
| C02 | canonical hash mismatch | synthetic_negative | PASS |
| C03 | duplicate physical PDF | synthetic_negative | PASS |
| C04 | incorrect domain assignment | synthetic_negative | PASS |
| C05 | title suggests content but PDF does not | synthetic_negative | PASS |
| R06 | same facility name, different entities | synthetic_negative | PASS |
| R07 | same basin does not prove applicability | synthetic_negative | PASS |
| R08 | draft treated as effective rule | synthetic_negative | PASS |
| R09 | invalid replacement relation | synthetic_negative | PASS |
| R10 | same metric with incompatible times | synthetic_negative | PASS |
| R11 | same value with different units | synthetic_negative | PASS |
| R12 | unrelated evidence in a set | synthetic_negative | PASS |
| Q13 | cross-document label with one source | synthetic_negative | PASS |
| Q14 | multi-hop without dependency | synthetic_negative | PASS |
| Q15 | arithmetic uses wrong table result | synthetic_negative | PASS |
| Q16 | extrema lacks complete scope | synthetic_negative | PASS |
| Q17 | duplicate question with altered entity | synthetic_negative | PASS |
| Q18 | legitimate simple factual QA | actual_positive | PASS |
| Q19 | legitimate single-document comparison | actual_positive | PASS |
| Q20 | legitimate real cross-document QA | actual_positive | PASS |
| Q21 | insufficient evidence scope | synthetic_negative | PASS |
| Q22 | frozen 38 modified | synthetic_negative | PASS |

Negative cases are synthetic mutations only. Positive cases Q18-Q20 load actual V4.4 artifacts. Candidate Test was not accessed.
