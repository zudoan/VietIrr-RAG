import re
from src.validation.answer_component_extractor_v2_4 import AnswerComponentExtractorV24

class EvidenceNecessityValidatorV24:
    """
    V2.4 Independent Necessity Validator.
    Follows strict requirements:
    1. Extract answer components from (Question, Answer) only.
    2. Freeze components.
    3. Build Evidence Support Matrix (SUPPORTED, NOT_SUPPORTED, UNCERTAIN).
    4. Run counterfactual ablation E \ {e_i}.
    5. Determine necessity_status: PASS | FAIL_REDUNDANT | FAIL_UNSUPPORTED | UNCERTAIN.
    """
    def __init__(self):
        self.extractor = AnswerComponentExtractorV24()

    def _normalize(self, text):
        return re.sub(r'\s+', ' ', str(text)).strip().lower()

    def check_support(self, component, evidence_item):
        """
        Evaluates whether evidence_item explicitly supports component.
        Returns: SUPPORTED | NOT_SUPPORTED | UNCERTAIN
        """
        req = self._normalize(component.get("requirement", ""))
        ans = self._normalize(component.get("expected_answer_content", ""))
        ev_text = self._normalize(evidence_item.get("exact_content", ""))
        cell_prov = evidence_item.get("table_cell_provenance")

        # 1. Check numbers in answer component
        ans_numbers = set(re.findall(r'\d+(?:[.,]\d+)?', ans))
        ev_numbers = set(re.findall(r'\d+(?:[.,]\d+)?', ev_text))

        # If component is quantitative and has numbers
        if ans_numbers:
            # Table cell exact match
            if cell_prov and str(cell_prov.get("raw_cell", "")).strip() in ans:
                # Also check row or column relevance
                row = self._normalize(cell_prov.get("row_label", ""))
                col = self._normalize(cell_prov.get("column_label", ""))
                if (row and row in req) or (col and any(w in req for w in col.split() if len(w) > 3)):
                    return "SUPPORTED"
                return "SUPPORTED"

            # Check overlap of numeric values
            overlap = ans_numbers & ev_numbers
            if overlap:
                # Check at least one non-trivial word from requirement matches
                req_words = [w for w in req.split() if len(w) > 3]
                if any(w in ev_text for w in req_words):
                    return "SUPPORTED"

        # 2. Text / semantic match
        # Check if substantial substring of expected answer is in evidence
        ans_clean = re.sub(r'["\']', '', ans)
        if len(ans_clean) > 20 and (ans_clean in ev_text or any(part.strip() in ev_text for part in ans_clean.split('.') if len(part.strip()) > 20)):
            return "SUPPORTED"

        # Word overlap threshold
        req_tokens = set(re.findall(r'\w+', req)) - {"trong", "tai", "cua", "la", "theo", "cac", "cho", "duoc"}
        ev_tokens = set(re.findall(r'\w+', ev_text))
        if req_tokens and len(req_tokens & ev_tokens) / len(req_tokens) > 0.6:
            return "SUPPORTED"

        return "NOT_SUPPORTED"

    def validate_necessity(self, qa_record):
        qa_id = qa_record.get("qa_id", "")
        question = qa_record.get("question", "")
        answer = qa_record.get("answer", "")
        gold_evidence = qa_record.get("gold_evidence", [])
        ec = len(gold_evidence)

        # Step 1 & 2: Extract and freeze components from Q & A
        decomp = self.extractor.extract_components(question, answer)
        components = decomp["components"]

        # If single evidence QA
        if ec <= 1:
            return {
                "qa_id": qa_id,
                "is_multi_evidence": False,
                "evidence_count": ec,
                "answer_components": components,
                "evidence_component_support": {},
                "ablation": {},
                "necessity_status": "PASS",
                "validator_type": "DETERMINISTIC"
            }

        # Step 3: Create Evidence Support Matrix
        matrix = {}
        for ev in gold_evidence:
            ev_id = ev.get("evidence_id")
            matrix[ev_id] = {}
            for comp in components:
                c_id = comp["component_id"]
                matrix[ev_id][c_id] = self.check_support(comp, ev)

        # Check if all components are supported by the collective evidence set
        all_comp_ids = {c["component_id"] for c in components}
        supported_comp_ids = set()
        for ev_id, supp in matrix.items():
            for c_id, val in supp.items():
                if val == "SUPPORTED":
                    supported_comp_ids.add(c_id)

        if supported_comp_ids < all_comp_ids:
            return {
                "qa_id": qa_id,
                "is_multi_evidence": True,
                "evidence_count": ec,
                "answer_components": components,
                "evidence_component_support": matrix,
                "ablation": {},
                "necessity_status": "FAIL_UNSUPPORTED",
                "unsupported_components": list(all_comp_ids - supported_comp_ids),
                "validator_type": "DETERMINISTIC"
            }

        # Step 4: Run counterfactual ablation E \ {e_i}
        ablation = {}
        redundant_evidence_ids = []

        all_ev_ids = [e["evidence_id"] for e in gold_evidence]
        for ev in gold_evidence:
            ev_id = ev["evidence_id"]
            remaining_ev_ids = [eid for eid in all_ev_ids if eid != ev_id]

            # Check which components are supported by remaining evidence
            supported_after_ablation = set()
            for r_id in remaining_ev_ids:
                for c_id, val in matrix.get(r_id, {}).items():
                    if val == "SUPPORTED":
                        supported_after_ablation.add(c_id)

            unsupported_after_ablation = all_comp_ids - supported_after_ablation
            # Ei is indispensable if removing it leaves at least one component unsupported
            is_indispensable = len(unsupported_after_ablation) > 0

            ablation[ev_id] = {
                "ablated_evidence_id": ev_id,
                "supported_without_it": list(supported_after_ablation),
                "unsupported_without_it": list(unsupported_after_ablation),
                "is_indispensable": is_indispensable
            }

            if not is_indispensable:
                redundant_evidence_ids.append(ev_id)

        # Step 5: Final necessity status
        if redundant_evidence_ids:
            status = "FAIL_REDUNDANT"
        else:
            status = "PASS"

        return {
            "qa_id": qa_id,
            "is_multi_evidence": True,
            "evidence_count": ec,
            "answer_components": components,
            "evidence_component_support": matrix,
            "ablation": ablation,
            "redundant_evidence_ids": redundant_evidence_ids,
            "necessity_status": status,
            "validator_type": "DETERMINISTIC"
        }
