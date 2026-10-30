"""VietIRR-RAG — Stage 2 Hydraulic Ontology and Evidence Assembly Package.

This package provides:
1. Standardized evidence and claim contracts (EvidenceItem, EvidenceSet, TechnicalClaim).
2. Non-breaking adapter for P5 Evidence dataclasses.
3. Offline schema validation and provenance tracking.
"""

from __future__ import annotations

__version__ = "0.3.0"

from viirr_ontology import adapters, domain, schema, verifier

__all__ = ["adapters", "domain", "schema", "verifier", "__version__"]
