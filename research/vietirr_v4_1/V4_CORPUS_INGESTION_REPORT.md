# V4.1 Corpus Ingestion Report

## Outcome

The isolated corpus contains **93 manifest records**: 89 immutable references to the accepted V3.2 sources and 4 newly downloaded PDFs. No legacy PDF was copied or modified. Candidate Test was not opened or hashed.

The initial survey screened **20** candidates: **4 ACCEPT**, **5 REJECT**, **10 REVIEW**, and **1 BLOCKED**. ACCEPT means the PDF was downloaded, passed PDF-magic/checksum/duplicate checks, had an attributable official publisher, and yielded reviewable text. It does not mean its facts or resulting QA are human gold.

## Accepted sources

| ID | Scope | Pages | Use restriction |
|---|---|---:|---|
| V4_CTTL_2025_77c60f84 | Current Bắc Nam Hà operation procedure | 38 | Clause-level human review before legal gold |
| V4_IWRP_2021_3031564c | Sông Châu/Bắc Nam Hà water forecast and use plan | 9 | Historical plan/forecast, not actual delivery |
| V4_CTTL_2024_dda51c21 | Cái Lớn–Cái Bé operation draft | 47 | **Draft only; never an applicable rule** |
| V4_BNNMT_2025_594e7382 | 2025 irrigation/dike safety directive | 5 | General duties; not facility-condition evidence |

All four have SHA-256, URL, publisher, date/version status, gap mapping, page count, local raw path and machine-parsed derivative. Parsed text carries a warning that it is not approved gold evidence.

## Duplicate and access findings

The two indexed Bắc Nam Hà attachment URLs returned byte-identical PDFs; only one canonical copy was retained and the other candidate is `REJECT_DUPLICATE`. The proposed TCVN dam-safety draft could not be downloaded and is `BLOCKED`, not ACCEPT. HTML news summaries are not treated as substitute PDFs.

## Linked packs

Two real packs are recorded: Bắc Nam Hà (current operation procedure + historical seasonal plan) and Cái Lớn–Cái Bé (draft operation context + two accepted 2025 water-quality bulletins). Their relations remain `MANIFEST_RELATION_PENDING_HUMAN`; therefore zero relations are eligible for gold.

## Rights and reproducibility

The files are public downloads from official domains. No open redistribution licence was found, so the manifest records the source URLs and does not claim an open licence. The review bundle excludes PDF binaries; reviewers can verify checksums against locally acquired copies.
