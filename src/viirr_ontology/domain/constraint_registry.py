"""Constraint Registry Manager.

Loads, manages, and queries source-grounded domain constraints defined in
`ontology/domain_constraints_v0_1.json`.

Enforces the core research invariant:
- Unverified source-dependent rules must remain DRAFT or disabled.
- Only VERIFIED_SOURCE constraints are enabled for factual checking by default.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from viirr_ontology.domain.classes import VerificationConstraint


DEFAULT_CONSTRAINTS_FILE = Path(__file__).resolve().parents[3] / "ontology" / "domain_constraints_v0_1.json"
DEFAULT_SOURCE_INDEX = Path(__file__).resolve().parents[3] / "data" / "documents.jsonl"


class ConstraintRegistry:
    """In-memory manager for hydraulic domain verification constraints.

    Enforces:
    1. Rejection of duplicate conflicting constraint IDs.
    2. Separation of structural/unit rules from source-dependent factual/legal rules.
    3. Strict provenance audit before enabling source-dependent rules.
    4. Auditable activation logging.
    """

    def __init__(
        self,
        constraints: Optional[list[VerificationConstraint]] = None,
        metadata: Optional[dict] = None,
        trusted_source_hashes: Optional[dict[str, str]] = None,
    ) -> None:
        self._constraints: dict[str, VerificationConstraint] = {}
        self.metadata = metadata or {}
        self._activation_log: list[dict[str, Any]] = []
        self._trusted_source_hashes = dict(trusted_source_hashes or {})

        # Reject duplicate conflicting constraint IDs
        if constraints:
            for c in constraints:
                if c.constraint_id in self._constraints:
                    existing = self._constraints[c.constraint_id]
                    if existing != c:
                        raise ValueError(
                            f"Duplicate conflicting constraint ID '{c.constraint_id}': "
                            f"existing=({existing.name}, type={existing.constraint_type}) vs "
                            f"new=({c.name}, type={c.constraint_type})"
                        )
                    continue  # Identical duplicate is accepted idempotently
                self._constraints[c.constraint_id] = c

    @classmethod
    def load_from_file(
        cls,
        filepath: Optional[Path | str] = None,
        source_index: Optional[Path | str] = None,
    ) -> ConstraintRegistry:
        """Load constraints from the canonical JSON file."""
        target_path = Path(filepath) if filepath else DEFAULT_CONSTRAINTS_FILE
        if not target_path.exists():
            raise FileNotFoundError(f"Constraint registry file not found: {target_path}")

        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        source_path = Path(source_index) if source_index else DEFAULT_SOURCE_INDEX
        trusted_hashes: dict[str, str] = {}
        if source_path.exists():
            with open(source_path, "r", encoding="utf-8") as source_file:
                for line in source_file:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    doc_id = str(record.get("doc_id", "")).strip()
                    sha256 = str(record.get("sha256", "")).strip()
                    if doc_id and sha256 and record.get("acceptance_status") == "ACCEPT":
                        trusted_hashes[doc_id] = sha256

        return cls.from_dict(data, trusted_source_hashes=trusted_hashes)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        trusted_source_hashes: Optional[dict[str, str]] = None,
    ) -> ConstraintRegistry:
        """Create a ConstraintRegistry from a dictionary structure."""
        raw_list = data.get("constraints", [])
        constraints = [VerificationConstraint.from_dict(item) for item in raw_list]
        metadata = {
            "registry_version": data.get("registry_version", "0.1.0"),
            "project": data.get("project", "VietIRR-RAG"),
            "domain": data.get("domain", "hydraulic_engineering"),
            "last_updated": data.get("last_updated", ""),
        }
        return cls(
            constraints=constraints,
            metadata=metadata,
            trusted_source_hashes=trusted_source_hashes,
        )

    def load_from_dict(self, data: dict[str, Any]) -> None:
        """Load constraints from dict into existing registry, rejecting conflicting duplicates."""
        raw_list = data.get("constraints", [])
        for item in raw_list:
            c = VerificationConstraint.from_dict(item)
            self.register(c)

    def register(self, constraint: VerificationConstraint) -> None:
        """Register a single constraint, rejecting duplicate conflicting IDs."""
        if constraint.constraint_id in self._constraints:
            existing = self._constraints[constraint.constraint_id]
            if existing != constraint:
                raise ValueError(
                    f"Duplicate conflicting constraint ID '{constraint.constraint_id}': "
                    f"existing=({existing.name}, type={existing.constraint_type}) vs "
                    f"new=({constraint.name}, type={constraint.constraint_type})"
                )
            return
        self._constraints[constraint.constraint_id] = constraint

    def get_constraint(self, constraint_id: str) -> Optional[VerificationConstraint]:
        """Retrieve a constraint by its ID."""
        return self._constraints.get(constraint_id)

    def get_all_constraints(self) -> list[VerificationConstraint]:
        """Return all constraints regardless of verification status."""
        return list(self._constraints.values())

    def get_structural_constraints(self) -> list[VerificationConstraint]:
        """Return structural and unit compatibility rules."""
        return [c for c in self._constraints.values() if c.is_structural()]

    def get_source_dependent_constraints(self, only_verified: bool = True) -> list[VerificationConstraint]:
        """Return source-dependent factual or legal rules."""
        if only_verified:
            return [c for c in self.get_active_constraints(only_verified=True) if c.is_source_dependent()]
        return [c for c in self._constraints.values() if c.is_source_dependent()]

    def get_active_constraints(self, only_verified: bool = True) -> list[VerificationConstraint]:
        """Return constraints enabled for verification with an auditable activation log.

        - Structural rules (SCHEMA_TYPE, UNIT_COMPATIBILITY) are enabled by definition.
        - Source-dependent rules MUST pass audit_provenance() to become active.
        - Rules that fail audit are logged as INACTIVE_UNVERIFIED and excluded.
        """
        active: list[VerificationConstraint] = []
        log_entries: list[dict[str, Any]] = []

        for c in self._constraints.values():
            if c.is_structural():
                active.append(c)
                log_entries.append({
                    "constraint_id": c.constraint_id,
                    "name": c.name,
                    "status": "ACTIVE_STRUCTURAL",
                    "reason": "Structural schema or unit compatibility rule",
                })
            elif only_verified:
                is_valid, reason = c.audit_provenance(
                    trusted_doc_ids=set(self._trusted_source_hashes),
                    trusted_hashes=self._trusted_source_hashes,
                )
                if is_valid:
                    active.append(c)
                    log_entries.append({
                        "constraint_id": c.constraint_id,
                        "name": c.name,
                        "status": "ACTIVE_SOURCE_VERIFIED",
                        "document_id": c.document_id,
                        "source_reference": c.source_reference,
                        "reason": reason,
                    })
                else:
                    log_entries.append({
                        "constraint_id": c.constraint_id,
                        "name": c.name,
                        "status": "INACTIVE_UNVERIFIED",
                        "document_id": c.document_id,
                        "reason": reason,
                    })
            else:
                active.append(c)
                log_entries.append({
                    "constraint_id": c.constraint_id,
                    "name": c.name,
                    "status": "ACTIVE_ALL_INCL_DRAFT",
                    "reason": "Draft inclusion explicitly requested",
                })

        self._activation_log = log_entries
        return active

    def get_activation_log(self) -> list[dict[str, Any]]:
        """Return the auditable log explaining why each rule became active or was rejected."""
        if not self._activation_log:
            self.get_active_constraints()
        return list(self._activation_log)

    def get_constraints_for_class(
        self, applicable_class: str, only_verified: bool = True
    ) -> list[VerificationConstraint]:
        """Filter constraints applicable to a specific ontology class or parameter."""
        norm_class = applicable_class.strip().lower()
        active = self.get_active_constraints(only_verified=only_verified)
        return [c for c in active if c.applicable_class.strip().lower() == norm_class]

    def get_constraints_by_type(
        self, constraint_type: str, only_verified: bool = True
    ) -> list[VerificationConstraint]:
        """Filter constraints by type (SCHEMA_TYPE, UNIT_COMPATIBILITY, SOURCE_VERIFIED_FACT, LEGAL_APPLICABILITY)."""
        active = self.get_active_constraints(only_verified=only_verified)
        return [c for c in active if c.constraint_type == constraint_type]
