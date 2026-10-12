# MAR-ER One-Shot Experiment

## Protocol

The method, B=100, K=20, candidate anchor=80, protected Top-15, intrusion budget=5,
RRF constant=60, source depth=100, bootstrap=1,000 and seed=42 were frozen before
the official M0--M4 run. Candidate Test was not parsed or evaluated.

## Primary results

| Method | Coverage@100 | All R@20 | Multi All R@20 | Unique-set balanced All R@20 |
|---|---:|---:|---:|---:|
| M0 | 0.7742 | 0.6237 | 0.6000 | 0.4684 |
| M1 | 0.7742 | 0.6237 | 0.6000 | 0.5384 |
| M2 | 0.8065 | 0.5269 | 0.5600 | 0.4195 |
| M3 | 0.7742 | 0.6237 | 0.6000 | 0.4684 |
| M4 | 0.8280 | 0.5914 | 0.6000 | 0.4737 |

M4 versus M0: candidate recovered/lost = 5/
0; final recovered/regressed = 2/
5; recovered unique signatures =
2.

## Modality and mechanism

- Text-only All R@20: M0=0.3448,
  M4=0.3793.
- Table-only All R@20: M0=0.8462,
  M4=0.7436; delta=-0.1026.
- Mixed (`TEXT_TABLE`) All R@20: M0=0.5909,
  M4=0.5455.
- Minimum Top-20 overlap was 15/20 and maximum
  protected-anchor displacement was 5.
- Gold lost from baseline ranks 16--20 occurred in
  7 QA.

One-sided uplift protects score contribution, not relevance or gold rank. The protected
prefix prevents large displacement but also preserves strong baseline false positives and
limits rescue capacity to five final slots.

## Uncertainty

- QA bootstrap M4-M0 All R@20: effect
  -0.0323, 95% CI
  [-0.0860, +0.0215],
  INCONCLUSIVE.
- Gold-signature cluster bootstrap: effect
  -0.0323, 95% CI
  [-0.0428,
  +0.0684],
  INCONCLUSIVE.

These are exploratory Dev results. The 25 multi QA reduce to only eight unique gold
signatures and cannot support an independent superiority claim.

## Efficiency

Device: cuda; peak VRAM: 2194.4169921875 MB. M4 mean
latency was 24.81 ms/query with all dense evidence
vectors loaded from verified caches.

## Decision

Main finding: MAR-ER did not improve final complete-evidence recall over M0.

- `EXPERIMENT_VALID=true`
- `METHOD_PROMISING=false`
- `PAPER_READY=false`
- Decision: `STOP_MAR_ER_BRANCH`

No MAR-ER V2, weight change, Candidate Test run or follow-on optimization is authorized
by this experiment.
