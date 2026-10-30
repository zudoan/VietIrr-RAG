"""Domain module for Stage 2 Hydraulic Domain Ontology MVP."""

from viirr_ontology.domain.classes import (
    DesignCondition,
    HydraulicStructure,
    Jurisdiction,
    MeasurementAssertion,
    StandardDocument,
    TechnicalParameter,
    VerificationConstraint,
)
from viirr_ontology.domain.constraint_registry import ConstraintRegistry
from viirr_ontology.domain.ontology_loader import HydraulicOntology
from viirr_ontology.domain.unit_registry import (
    UnitDimension,
    check_unit_compatibility,
    get_unit_dimension,
)

__all__ = [
    "HydraulicStructure",
    "TechnicalParameter",
    "DesignCondition",
    "StandardDocument",
    "MeasurementAssertion",
    "Jurisdiction",
    "VerificationConstraint",
    "ConstraintRegistry",
    "HydraulicOntology",
    "UnitDimension",
    "check_unit_compatibility",
    "get_unit_dimension",
]
