# VietIrrDocBench — Prompt Configuration: QA Validation V1

## Directive: Automated Evidence Necessity & Provenance Verification

### Verification Checklist:
1. **Answerability Test**:
   - Given the full set of gold evidence, is the question completely and unambiguously answerable?
2. **Necessity Test**:
   - For every evidence item $e_i \in E_{\text{gold}}$:
     - When evaluated with $E_{\text{gold}} \setminus \{e_i\}$, does the answer become incomplete or unverifiable?
     - If NO (answer is still complete without $e_i$), REJECT or prune $e_i$.
3. **Exact Grounding**:
   - Does the answer contain numbers, dates, units, or names not present in the source evidence?
   - If YES, REJECT.
4. **Metadata Shortcut Check**:
   - Can the question be answered merely from the document title or header without reading the text?
   - If YES, REJECT.
5. **Validation Status**:
   - Allowed statuses: `GENERATED`, `AUTO_VALIDATED`, `LLM_REVIEWED`, `REJECTED`.
   - Never label as `HUMAN_REVIEWED` without manual human audit.
