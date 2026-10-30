"""Evidence-Targeted Correction Module for Stage 3 Sprint A.

Exports:
- CorrectionGoal, CorrectionPlan, CorrectionAttempt, CorrectionResult
- EvidenceCorrectionPlanner
- PageRegionRetrievalAdapter, MockRetrievalBackend, RealRetrievalBackend
- TargetedCorrectionExecutor
"""

from .executor import TargetedCorrectionExecutor, UntargetedCorrectionExecutor
from .models import CorrectionAttempt, CorrectionGoal, CorrectionPlan, CorrectionResult
from .planner import EvidenceCorrectionPlanner
from .provenance import (
    DocumentIdentityRegistry,
    EvidenceProvenanceValidator,
    ProvenanceValidationStatus,
    StructuralRelationVerifier,
    TrustedSourceStructureRegistry,
)
from .retrieval_adapter import MockRetrievalBackend, PageRegionRetrievalAdapter, RealRetrievalBackend

__all__ = [
    "CorrectionGoal",
    "CorrectionPlan",
    "CorrectionAttempt",
    "CorrectionResult",
    "EvidenceCorrectionPlanner",
    "PageRegionRetrievalAdapter",
    "MockRetrievalBackend",
    "RealRetrievalBackend",
    "TargetedCorrectionExecutor",
    "UntargetedCorrectionExecutor",
    "DocumentIdentityRegistry",
    "StructuralRelationVerifier",
    "EvidenceProvenanceValidator",
    "ProvenanceValidationStatus",
    "TrustedSourceStructureRegistry",
]
