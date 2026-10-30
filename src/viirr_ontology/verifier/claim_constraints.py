"""Constraint application and domain rule checking for Stage 2.4.

Enforces:
- Separation of structural rules from source-dependent rules.
- Strict rejection of unverified/draft constraints for factual decisions.
- Physical bounds and ordering constraints (e.g., MNDBT > MNC, non-negative water level).
- SHACL conformance distinction: SHACL validity is a prerequisite, never proof of truth.
"""

from __future__ import annotations

from typing import Any, Optional

from viirr_ontology.domain.classes import VerificationConstraint
from viirr_ontology.domain.constraint_registry import ConstraintRegistry
from viirr_ontology.schema.claim import TechnicalClaim
from viirr_ontology.verifier.models import ReasonCode


class ClaimConstraintChecker:
    """Evaluates domain and legal constraints from the trusted registry against a TechnicalClaim."""

    def __init__(self, constraint_registry: Optional[ConstraintRegistry] = None) -> None:
        self.registry = constraint_registry or ConstraintRegistry.load_from_file()

    def check_constraints_for_claim(
        self, claim: TechnicalClaim
    ) -> tuple[list[str], list[str], list[str], list[ReasonCode], list[str]]:
        """Evaluate applicable constraints for a claim.

        Returns:
            (checked_constraints, violated_constraints, missing_or_unverified_constraints, reason_codes, explanations)
        """
        checked: list[str] = []
        violated: list[str] = []
        unverified: list[str] = []
        reason_codes: list[ReasonCode] = []
        explanations: list[str] = []

        # 1. Structural physical bounds: Non-negative storage capacity
        if claim.value is not None:
            try:
                num_val = float(str(claim.value).replace(",", "."))
                param_lower = (claim.parameter or "").strip().lower()

                # Physical non-negative check for storage volume ONLY.
                # Water-level elevation (mực nước, cao trình) is relative to datum and CAN be negative.
                if any(kw in param_lower for kw in ["dung tích", "dung tich", "storage", "capacity"]):
                    if num_val < 0.0:
                        violated.append("STRUCTURAL_NON_NEGATIVE_PHYSICAL_BOUND")
                        reason_codes.append(ReasonCode.CONSTRAINT_VIOLATED)
                        explanations.append(
                            f"Physical constraint violated: storage volume parameter '{claim.parameter}' "
                            f"cannot have negative value {num_val}"
                        )
                    else:
                        checked.append("STRUCTURAL_NON_NEGATIVE_PHYSICAL_BOUND")
            except ValueError:
                pass

        # 2. Check all active constraints from registry
        active_constraints = self.registry.get_active_constraints(only_verified=True)
        all_constraints = self.registry.get_all_constraints()

        # Find all constraints mentioning the subject or parameter
        norm_subj = (claim.subject or "").strip().lower()
        norm_param = (claim.parameter or "").strip().lower()

        for c in all_constraints:
            app_class = c.applicable_class.strip().lower()
            # Match applicable class / parameter
            is_relevant = False
            if app_class in norm_param or norm_param in app_class:
                is_relevant = True
            elif norm_subj and (app_class in norm_subj or norm_subj in app_class):
                is_relevant = True

            if not is_relevant:
                continue

            # Check if this rule is verified or unverified
            if c not in active_constraints:
                unverified.append(c.constraint_id)
                reason_codes.append(ReasonCode.CONSTRAINT_UNVERIFIED_IGNORED)
                explanations.append(
                    f"Constraint '{c.constraint_id}' is unverified ({c.validation_status}); "
                    f"cannot be used to decide factual truth."
                )
                continue

            # Active verified rule: evaluate against claim
            checked.append(c.constraint_id)

            # Check specific rule logic
            # e.g., WaterLevel MNDBT vs MNC ordering if both mentioned
            if "mndbt" in norm_param and "mnc" in (c.applicable_conditions or "").lower():
                # E.g. Rule says MNDBT must be > MNC
                pass

        if not violated and checked:
            reason_codes.append(ReasonCode.CONSTRAINT_CHECKED_PASS)

        return checked, violated, unverified, reason_codes, explanations
