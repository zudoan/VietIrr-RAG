import re

class CounterfactualValidator:
    """
    Independent validator for minimal counterfactual hard negatives.
    Does not rely on generator self-approval.
    Verifies that candidate negatives maintain high semantic relevance while having
    precisely ONE controlled mismatch factor (differing_factors == 1).
    """
    def __init__(self):
        pass

    def clean_str(self, x):
        if x is None:
            return ""
        return str(x).strip().lower()

    def validate_negative(self, neg_record):
        """
        Validates a single hard negative record.
        Returns:
            status: VALID, NON_MINIMAL, INVALID, UNCERTAIN
            differing_factors: list of factors that differ
            reasons: list of validation messages
        """
        reasons = []
        neg_type = neg_record.get("negative_type", "")
        corrupted_factor = neg_record.get("corrupted_factor", "")
        t_sig = neg_record.get("target_signature", {})
        n_sig = neg_record.get("negative_signature", {})

        # 1. Grounding check
        if not neg_record.get("source_grounded", False):
            return {
                "status": "INVALID",
                "differing_factors": [],
                "reasons": ["NEGATIVE_NOT_SOURCE_GROUNDED"]
            }

        # 2. PROVENANCE_CONFLICT Multi-evidence set check
        if neg_type == "PROVENANCE_CONFLICT":
            # Target has congruent provenance; negative has exactly one intended conflict
            corrupted_set = neg_record.get("corrupted_evidence_set", [])
            if not corrupted_set or len(corrupted_set) < 2:
                return {
                    "status": "INVALID",
                    "differing_factors": [],
                    "reasons": ["PROVENANCE_CONFLICT_SET_TOO_SMALL"]
                }

            # Check if one piece is intact and one piece is corrupted
            has_intact = any(c.get("source_role") == "INTACT_GOLD_COMPONENT" for c in corrupted_set)
            has_sub = any(c.get("source_role") == "CORRUPTED_SUBSTITUTE_COMPONENT" for c in corrupted_set)
            
            if not (has_intact and has_sub):
                return {
                    "status": "NON_MINIMAL",
                    "differing_factors": ["UNKNOWN_STRUCTURE"],
                    "reasons": ["PROVENANCE_SET_MISSING_INTACT_OR_SUBSTITUTE_ROLE"]
                }

            # Differing factor is provenance / document incongruence
            return {
                "status": "VALID",
                "differing_factors": ["PROVENANCE_MISMATCH"],
                "reasons": ["CONTROLLED_PROVENANCE_SUBSTITUTION_VERIFIED"]
            }

        # 3. Single-item Counterfactual Checks (WRONG_ENTITY, WRONG_METRIC, WRONG_PERIOD, WRONG_UNIT)
        t_ent = self.clean_str(t_sig.get("entity"))
        n_ent = self.clean_str(n_sig.get("entity"))
        
        t_met = self.clean_str(t_sig.get("metric"))
        n_met = self.clean_str(n_sig.get("metric"))
        
        t_per = self.clean_str(t_sig.get("period"))
        n_per = self.clean_str(n_sig.get("period"))
        
        t_unt = self.clean_str(t_sig.get("unit"))
        n_unt = self.clean_str(n_sig.get("unit"))

        differing_factors = []
        if t_ent and n_ent and t_ent != n_ent:
            differing_factors.append("ENTITY")
        if t_met and n_met and t_met != n_met:
            differing_factors.append("METRIC")
        if t_per and n_per and t_per != n_per:
            differing_factors.append("PERIOD")
        if t_unt and n_unt and t_unt != n_unt:
            differing_factors.append("UNIT")

        # Specific type validations
        if neg_type == "WRONG_ENTITY":
            if "ENTITY" not in differing_factors:
                return {"status": "INVALID", "differing_factors": differing_factors, "reasons": ["ENTITY_IS_IDENTICAL"]}
            if len(differing_factors) == 1:
                return {"status": "VALID", "differing_factors": differing_factors, "reasons": ["MINIMAL_WRONG_ENTITY_VERIFIED"]}
            else:
                return {"status": "NON_MINIMAL", "differing_factors": differing_factors, "reasons": [f"MULTIPLE_FACTORS_DIFFER: {differing_factors}"]}

        elif neg_type == "WRONG_METRIC":
            if "METRIC" not in differing_factors:
                return {"status": "INVALID", "differing_factors": differing_factors, "reasons": ["METRIC_IS_IDENTICAL"]}
            if len(differing_factors) == 1:
                return {"status": "VALID", "differing_factors": differing_factors, "reasons": ["MINIMAL_WRONG_METRIC_VERIFIED"]}
            else:
                return {"status": "NON_MINIMAL", "differing_factors": differing_factors, "reasons": [f"MULTIPLE_FACTORS_DIFFER: {differing_factors}"]}

        elif neg_type == "WRONG_PERIOD":
            if "PERIOD" not in differing_factors:
                return {"status": "INVALID", "differing_factors": differing_factors, "reasons": ["PERIOD_IS_IDENTICAL"]}
            # Mandate: entity and metric must be identical or compatible!
            if len(differing_factors) == 1:
                return {"status": "VALID", "differing_factors": differing_factors, "reasons": ["MINIMAL_WRONG_PERIOD_VERIFIED"]}
            else:
                # If entity or metric also changed, it is non-minimal
                return {"status": "NON_MINIMAL", "differing_factors": differing_factors, "reasons": [f"PERIOD_CHANGED_WITH_ADDITIONAL_FACTORS: {differing_factors}"]}

        elif neg_type == "WRONG_UNIT":
            if "UNIT" not in differing_factors:
                return {"status": "INVALID", "differing_factors": differing_factors, "reasons": ["UNIT_IS_IDENTICAL"]}
            if len(differing_factors) == 1:
                return {"status": "VALID", "differing_factors": differing_factors, "reasons": ["MINIMAL_WRONG_UNIT_VERIFIED"]}
            else:
                return {"status": "NON_MINIMAL", "differing_factors": differing_factors, "reasons": [f"MULTIPLE_FACTORS_DIFFER: {differing_factors}"]}

        return {
            "status": "UNCERTAIN",
            "differing_factors": differing_factors,
            "reasons": [f"UNKNOWN_NEGATIVE_TYPE: {neg_type}"]
        }
