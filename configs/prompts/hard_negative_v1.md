# VietIrrDocBench — Prompt Configuration: Minimal Counterfactual Hard Negatives V1

## Directive: Minimal Corruption Hard Negatives
Construct real-source negative evidence sets that differ from the gold evidence in exactly ONE controlled dimension.

### Corrupted Factors:
1. `PERIOD` / `DATE`: Same reservoir/basin and metric, but measured on a different day, week, or season.
2. `RESERVOIR` / `STATION`: Same metric and date, but at an adjacent or different reservoir or gauging station.
3. `METRIC`: Same reservoir and time, but a different parameter (e.g., Inflow vs Outflow, Dead storage vs Active storage).
4. `UNIT`: Compatible number but wrong physical unit context (e.g., million m3 vs m3/s).
5. `DOCUMENT_VERSION`: Outdated decision vs current amended decision.

### Provenance Conflict Sets:
Create multi-element negative candidate sets labeled `PROVENANCE_CONFLICT` where individual elements appear relevant independently, but cannot jointly answer the question (e.g., Table from period A + narrative from period B).

### Strict Rule:
All negative evidence must exist in the real document corpus. NEVER invent fake values, names, or dates.
