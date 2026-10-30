"""Comprehensive tests for Stage 2 Sprint B: S2.3 Hydraulic Domain Ontology MVP.

Validates:
1. RDF/OWL ontology parsing, namespace consistency, and version metadata.
2. 6 Primary classes, subclasses, and key relations existence in the RDF graph.
3. MeasurementAssertion n-ary fact reification structure.
4. Physical unit and dimension consistency validation (Positive & Negative).
5. Source-grounded constraint registry provenance (VERIFIED_SOURCE vs DRAFT_UNVERIFIED).
6. Invariant: Unverified rules are disabled by default.
7. Preservation of P5-KNOWN-01 (multi-word jurisdiction) and P5-KNOWN-02 (legal negation) representation.
8. SHACL shapes structural integrity.
"""

from __future__ import annotations

from pathlib import Path
import pytest
import rdflib
from rdflib.namespace import OWL, RDF, RDFS

from viirr_ontology.domain import (
    ConstraintRegistry,
    HydraulicOntology,
    HydraulicStructure,
    MeasurementAssertion,
    TechnicalParameter,
    UnitDimension,
    check_unit_compatibility,
    get_unit_dimension,
)
from viirr_ontology.schema import ClaimPolarity, TechnicalClaim


ONTOLOGY_FILE = Path(__file__).resolve().parents[1] / "ontology" / "viirr_hydraulic_v0_1.ttl"
SHACL_FILE = Path(__file__).resolve().parents[1] / "ontology" / "constraints_v0_1.ttl"
CONSTRAINTS_FILE = Path(__file__).resolve().parents[1] / "ontology" / "domain_constraints_v0_1.json"


# =============================================================================
# 1. ONTOLOGY PARSING & VOCABULARY VALIDATION
# =============================================================================

def test_ontology_file_exists_and_parses_turtle():
    """Ontology file must exist and parse cleanly as W3C Turtle."""
    assert ONTOLOGY_FILE.exists()
    ontology = HydraulicOntology.load(ONTOLOGY_FILE)
    assert len(ontology.graph) > 200


def test_ontology_metadata_namespace_and_version():
    """Ontology must declare stable namespace and versionIRI 0.1.0."""
    ontology = HydraulicOntology.load(ONTOLOGY_FILE)
    g = ontology.graph

    ontology_uri = rdflib.URIRef("http://vietirr-rag.org/ontology/hydraulic")
    version_iri = rdflib.URIRef("http://vietirr-rag.org/ontology/hydraulic/0.1.0")

    assert (ontology_uri, RDF.type, OWL.Ontology) in g
    assert (ontology_uri, OWL.versionIRI, version_iri) in g
    version_info = list(g.objects(ontology_uri, OWL.versionInfo))
    assert len(version_info) == 1
    assert str(version_info[0]) == "0.1.0"


def test_primary_ontology_classes_exist():
    """All 6 primary classes from the roadmap must be declared as owl:Class."""
    ontology = HydraulicOntology.load(ONTOLOGY_FILE)
    classes = ontology.get_classes()

    expected_classes = [
        "http://vietirr-rag.org/ontology/hydraulic#HydraulicStructure",
        "http://vietirr-rag.org/ontology/hydraulic#TechnicalParameter",
        "http://vietirr-rag.org/ontology/hydraulic#DesignCondition",
        "http://vietirr-rag.org/ontology/hydraulic#StandardDocument",
        "http://vietirr-rag.org/ontology/hydraulic#EvidenceRegion",
        "http://vietirr-rag.org/ontology/hydraulic#TechnicalClaim",
    ]
    for exp in expected_classes:
        assert exp in classes, f"Expected primary class {exp} missing from ontology"


def test_supporting_classes_exist():
    """Supporting classes (MeasurementAssertion, Unit, Jurisdiction, VerificationConstraint) must exist."""
    ontology = HydraulicOntology.load(ONTOLOGY_FILE)
    classes = ontology.get_classes()

    expected_supporting = [
        "http://vietirr-rag.org/ontology/hydraulic#MeasurementAssertion",
        "http://vietirr-rag.org/ontology/hydraulic#Unit",
        "http://vietirr-rag.org/ontology/hydraulic#Jurisdiction",
        "http://vietirr-rag.org/ontology/hydraulic#VerificationConstraint",
    ]
    for exp in expected_supporting:
        assert exp in classes, f"Expected supporting class {exp} missing"


def test_subclasses_hierarchy():
    """Subclasses must inherit correctly from primary classes."""
    ontology = HydraulicOntology.load(ONTOLOGY_FILE)

    # Subclasses of HydraulicStructure
    struct_subs = ontology.get_subclasses("HydraulicStructure")
    assert any("Reservoir" in s for s in struct_subs)
    assert any("Dam" in s for s in struct_subs)
    assert any("MonitoringStation" in s for s in struct_subs)
    assert any("SluiceGate" in s for s in struct_subs)

    # Subclasses of TechnicalParameter
    param_subs = ontology.get_subclasses("TechnicalParameter")
    assert any("WaterLevel" in s for s in param_subs)
    assert any("StorageCapacity" in s for s in param_subs)
    assert any("Discharge" in s for s in param_subs)
    assert any("WaterQualityParameter" in s for s in param_subs)


def test_candidate_properties_exist():
    """Candidate object and datatype properties must be defined with clear semantics."""
    ontology = HydraulicOntology.load(ONTOLOGY_FILE)
    obj_props = ontology.get_object_properties()
    dt_props = ontology.get_datatype_properties()

    expected_obj_props = [
        "hasParameter",
        "hasUnit",
        "hasStructure",
        "appliesUnderCondition",
        "definedInStandard",
        "supportedByEvidence",
        "requiresCondition",
        "referencesTable",
        "supersedesVersion",
        "hasJurisdiction",
    ]
    for prop in expected_obj_props:
        assert any(prop in p for p in obj_props), f"Expected object property '{prop}' missing"

    expected_dt_props = [
        "hasValue",
        "hasNumericValue",
        "hasTemporalScope",
        "hasAction",
        "hasPolarity",
        "documentNumber",
        "pageNumber",
        "regionId",
    ]
    for prop in expected_dt_props:
        assert any(prop in p for p in dt_props), f"Expected datatype property '{prop}' missing"


def test_measurement_assertion_n_ary_reification():
    """MeasurementAssertion instances in ontology connect structure, parameter, value, unit, and document."""
    ontology = HydraulicOntology.load(ONTOLOGY_FILE)
    assertions = ontology.get_measurement_assertions()

    assert len(assertions) >= 4, f"Expected at least 4 source-grounded assertions, found {len(assertions)}"

    # Check Hoa Binh MNDBT fact
    hb_mndbt = next((a for a in assertions if "HoaBinh_MNDBT" in a["assertion_uri"]), None)
    assert hb_mndbt is not None
    assert hb_mndbt["numeric_value"] == 117.0
    assert "HoaBinhReservoir" in hb_mndbt["structure_uri"]
    assert "WaterLevel" in hb_mndbt["parameter_uri"]
    assert "Unit_Metre" in hb_mndbt["unit_uri"]
    assert "QD_740" in hb_mndbt["document_uri"]

    # Check Hoa Binh MNC fact
    hb_mnc = next((a for a in assertions if "HoaBinh_MNC" in a["assertion_uri"]), None)
    assert hb_mnc is not None
    assert hb_mnc["numeric_value"] == 80.0


# =============================================================================
# 2. UNIT DIMENSION AND COMPATIBILITY TESTS
# =============================================================================

def test_unit_dimension_resolution():
    """Unit strings resolve to their accurate physical dimensions."""
    assert get_unit_dimension("m") == UnitDimension.LENGTH
    assert get_unit_dimension("mét") == UnitDimension.LENGTH
    assert get_unit_dimension("cm") == UnitDimension.LENGTH

    assert get_unit_dimension("m3/s") == UnitDimension.FLOW_RATE
    assert get_unit_dimension("m³/s") == UnitDimension.FLOW_RATE

    assert get_unit_dimension("triệu m3") == UnitDimension.VOLUME
    assert get_unit_dimension("million_m3") == UnitDimension.VOLUME
    assert get_unit_dimension("10^6 m3") == UnitDimension.VOLUME

    assert get_unit_dimension("mg/l") == UnitDimension.CONCENTRATION
    assert get_unit_dimension("%") == UnitDimension.RATIO
    assert get_unit_dimension("unsupported_unit") == UnitDimension.UNKNOWN


def test_unit_compatibility_positive():
    """Compatible parameter and unit combinations must pass."""
    # Water level with metre
    ok, msg = check_unit_compatibility("Mực nước dâng bình thường", "m")
    assert ok
    assert "compatible" in msg

    # Discharge with m3/s
    ok, msg = check_unit_compatibility("Lưu lượng xả", "m3/s")
    assert ok

    # Storage capacity with million m3
    ok, msg = check_unit_compatibility("Dung tích hữu ích", "triệu m3")
    assert ok

    # Water quality with mg/l
    ok, msg = check_unit_compatibility("Nồng độ oxy hòa tan (DO)", "mg/l")
    assert ok


def test_unit_compatibility_negative():
    """Incompatible parameter and unit combinations must be rejected with informative explanation."""
    # Water level cannot have flow rate unit (m3/s)
    ok, msg = check_unit_compatibility("Mực nước dâng bình thường", "m3/s")
    assert not ok
    assert "Incompatible unit dimension" in msg
    assert "FLOW_RATE" in msg
    assert "LENGTH" in msg

    # Storage capacity cannot have length unit (m)
    ok, msg = check_unit_compatibility("Dung tích toàn bộ", "m")
    assert not ok
    assert "Incompatible unit dimension" in msg
    assert "VOLUME" in msg

    # Discharge cannot have concentration unit (mg/l)
    ok, msg = check_unit_compatibility("Lưu lượng thiết kế", "mg/l")
    assert not ok


# =============================================================================
# 3. SOURCE-GROUNDED CONSTRAINT REGISTRY TESTS
# =============================================================================

def test_constraint_registry_loading_and_structure():
    """Constraint registry must load valid JSON constraints with all required fields."""
    registry = ConstraintRegistry.load_from_file(CONSTRAINTS_FILE)
    constraints = registry.get_all_constraints()

    assert len(constraints) >= 8

    for c in constraints:
        assert c.constraint_id
        assert c.name
        assert c.description
        assert c.constraint_type in {
            "SCHEMA_TYPE",
            "UNIT_COMPATIBILITY",
            "SOURCE_VERIFIED_FACT",
            "LEGAL_APPLICABILITY",
        }
        assert c.validation_status in {"VERIFIED_SOURCE", "DRAFT_UNVERIFIED"}
        assert c.source_reference
        assert c.explanation


def test_verified_vs_draft_constraint_separation():
    """Unverified rules must remain DRAFT and not be enabled by default."""
    registry = ConstraintRegistry.load_from_file(CONSTRAINTS_FILE)

    active_verified = registry.get_active_constraints(only_verified=True)
    all_constraints = registry.get_active_constraints(only_verified=False)

    # Active verified must strictly exclude DRAFT_UNVERIFIED
    for c in active_verified:
        assert c.validation_status == "VERIFIED_SOURCE"

    draft_rules = [c for c in all_constraints if c.validation_status == "DRAFT_UNVERIFIED"]
    assert len(draft_rules) >= 1
    # Check that draft discharge alert is not in active_verified
    assert not any(c.constraint_id == "CONST-DRAFT-DISCHARGE-ALERT" for c in active_verified)
    assert any(c.constraint_id == "CONST-DRAFT-DISCHARGE-ALERT" for c in all_constraints)


def test_verified_source_grounding_in_corpus():
    """Grounded constraints must reference actual document IDs and articles."""
    registry = ConstraintRegistry.load_from_file(CONSTRAINTS_FILE)

    hb_mndbt = registry.get_constraint("CONST-FACT-HB-MNDBT")
    assert hb_mndbt is not None
    assert hb_mndbt.document_id == "IRR_CP_2019_ee0bca33"
    assert "740/QĐ-TTg" in hb_mndbt.source_reference
    assert "Điều 5" in hb_mndbt.source_reference
    assert hb_mndbt in registry.get_active_constraints(only_verified=True)
    # A metadata object alone is not authoritative without the registry's trusted
    # corpus record and hash binding.
    assert not hb_mndbt.is_verified()


# =============================================================================
# 4. PRESERVATION OF P5 KNOWN LIMITATIONS
# =============================================================================

def test_p5_known_01_representation_preserves_full_jurisdiction():
    """P5-KNOWN-01 Representation Test: Full jurisdiction string is preserved and distinguished.

    Prevents single-token regex truncation (Đồng Nai vs Đồng Tháp).
    """
    claim_dn = TechnicalClaim(
        claim_id="CLM-DN-01",
        claim_text="Công trình xả lũ thuộc địa bàn tỉnh Đồng Nai.",
        subject="Hồ Trị An",
        jurisdiction="tỉnh Đồng Nai",
        polarity=ClaimPolarity.AFFIRMED,
    )
    claim_dt = TechnicalClaim(
        claim_id="CLM-DT-01",
        claim_text="Công trình xả lũ thuộc địa bàn tỉnh Đồng Tháp.",
        subject="Hồ Trị An",
        jurisdiction="tỉnh Đồng Tháp",
        polarity=ClaimPolarity.AFFIRMED,
    )

    # Exact string comparison prevents confusing Đồng Nai and Đồng Tháp
    assert claim_dn.jurisdiction != claim_dt.jurisdiction
    assert claim_dn.jurisdiction == "tỉnh Đồng Nai"
    assert claim_dt.jurisdiction == "tỉnh Đồng Tháp"


def test_p5_known_02_representation_isolates_action_and_polarity():
    """P5-KNOWN-02 Representation Test: Decouples action ('quyết định') and polarity ('NEGATED').

    Prevents mistaken affirmation due to the intervening Vietnamese word 'được'
    in 'không được quyết định'.
    """
    claim_aff = TechnicalClaim(
        claim_id="CLM-LEGAL-01",
        claim_text="Chủ tịch UBND tỉnh quyết định xả lũ.",
        subject="Chủ tịch UBND tỉnh",
        action="quyết định",
        polarity=ClaimPolarity.AFFIRMED,
    )
    claim_neg = TechnicalClaim(
        claim_id="CLM-LEGAL-02",
        claim_text="Chủ tịch UBND tỉnh không được quyết định xả lũ.",
        subject="Chủ tịch UBND tỉnh",
        action="quyết định",
        polarity=ClaimPolarity.NEGATED,
    )

    # Same action, strictly opposite polarities
    assert claim_aff.action == claim_neg.action == "quyết định"
    assert claim_aff.polarity == ClaimPolarity.AFFIRMED
    assert claim_neg.polarity == ClaimPolarity.NEGATED
    assert claim_aff.polarity != claim_neg.polarity


# =============================================================================
# 5. SHACL SHAPES VALIDITY TEST
# =============================================================================

def test_shacl_file_syntax():
    """SHACL constraints file must parse cleanly as Turtle."""
    assert SHACL_FILE.exists()
    g = rdflib.Graph()
    g.parse(str(SHACL_FILE), format="turtle")
    assert len(g) > 30


# =============================================================================
# 6. S2.3 SCIENTIFIC INTEGRITY FIX TESTS
# =============================================================================

import pyshacl
from viirr_ontology.domain.classes import VerificationConstraint


def test_shacl_actual_execution_and_closed_world_conformance():
    """Execute actual SHACL validation using pyshacl on the ontology graph.
    
    Demonstrates actual SHACL constraint execution, closed-world conformance,
    and datatype alignment (xsd:double / xsd:decimal).
    """
    ontology = HydraulicOntology.load(ONTOLOGY_FILE)
    shacl_graph = rdflib.Graph().parse(str(SHACL_FILE), format="turtle")

    # Closed-world validation without RDFS
    conforms, report_graph, report_text = pyshacl.validate(
        data_graph=ontology.graph,
        shacl_graph=shacl_graph,
        rdfs=False,
    )
    assert conforms, f"SHACL closed-world validation failed:\n{report_text}"

    # Validation with RDFS inferencing
    conforms_rdfs, _, report_text_rdfs = pyshacl.validate(
        data_graph=ontology.graph,
        shacl_graph=shacl_graph,
        rdfs=True,
    )
    assert conforms_rdfs, f"SHACL RDFS validation failed:\n{report_text_rdfs}"


def test_shacl_negative_detection_missing_property():
    """SHACL validation must detect invalid MeasurementAssertion missing mandatory properties."""
    shacl_graph = rdflib.Graph().parse(str(SHACL_FILE), format="turtle")

    invalid_data = """
    @prefix vhr: <http://vietirr-rag.org/ontology/hydraulic#> .
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

    vhr:Invalid_Assertion a vhr:MeasurementAssertion ;
        vhr:hasNumericValue "100.0"^^xsd:double ;
        vhr:hasUnit vhr:Unit_Metre .
    """
    g = rdflib.Graph().parse(data=invalid_data, format="turtle")
    conforms, _, report_text = pyshacl.validate(data_graph=g, shacl_graph=shacl_graph, rdfs=False)
    assert not conforms
    assert "hasStructure" in report_text
    assert "hasParameter" in report_text


def test_shacl_negative_detection_wrong_datatype():
    """SHACL validation must reject non-numeric string values for hasNumericValue."""
    shacl_graph = rdflib.Graph().parse(str(SHACL_FILE), format="turtle")

    invalid_data = """
    @prefix vhr: <http://vietirr-rag.org/ontology/hydraulic#> .
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

    vhr:HB a vhr:HydraulicStructure .
    vhr:WL a vhr:TechnicalParameter .
    vhr:M a vhr:Unit .
    vhr:Doc a vhr:StandardDocument ; vhr:documentNumber "740" .
    vhr:Ev a vhr:EvidenceRegion ; vhr:pageNumber 4 ; vhr:documentId "D1" ; vhr:regionId "R1" .

    vhr:BadType_Assertion a vhr:MeasurementAssertion ;
        vhr:hasStructure vhr:HB ;
        vhr:hasParameter vhr:WL ;
        vhr:hasUnit vhr:M ;
        vhr:definedInStandard vhr:Doc ;
        vhr:supportedByEvidence vhr:Ev ;
        vhr:hasNumericValue "one_hundred_meters" .
    """
    g = rdflib.Graph().parse(data=invalid_data, format="turtle")
    conforms, _, report_text = pyshacl.validate(data_graph=g, shacl_graph=shacl_graph, rdfs=False)
    assert not conforms
    assert "hasNumericValue" in report_text


def test_shacl_negative_detection_missing_evidence():
    """SHACL validation must reject MeasurementAssertion lacking verified evidence support."""
    shacl_graph = rdflib.Graph().parse(str(SHACL_FILE), format="turtle")

    invalid_data = """
    @prefix vhr: <http://vietirr-rag.org/ontology/hydraulic#> .
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

    vhr:HB a vhr:HydraulicStructure .
    vhr:WL a vhr:TechnicalParameter .
    vhr:M a vhr:Unit .
    vhr:Doc a vhr:StandardDocument ; vhr:documentNumber "740" .

    vhr:NoEv_Assertion a vhr:MeasurementAssertion ;
        vhr:hasStructure vhr:HB ;
        vhr:hasParameter vhr:WL ;
        vhr:hasUnit vhr:M ;
        vhr:definedInStandard vhr:Doc ;
        vhr:hasNumericValue "117.0"^^xsd:double .
    """
    g = rdflib.Graph().parse(data=invalid_data, format="turtle")
    conforms, _, report_text = pyshacl.validate(data_graph=g, shacl_graph=shacl_graph, rdfs=False)
    assert not conforms
    assert "supportedByEvidence" in report_text


def test_specific_technical_parameter_identity():
    """MNDBT and MNC must be distinct machine-readable classes, not just generic WaterLevel."""
    ontology = HydraulicOntology.load(ONTOLOGY_FILE)
    g = ontology.graph

    vhr = rdflib.Namespace("http://vietirr-rag.org/ontology/hydraulic#")

    # Verify class hierarchy
    assert (vhr.NormalPoolWaterLevel, RDFS.subClassOf, vhr.WaterLevel) in g
    assert (vhr.DeadWaterLevel, RDFS.subClassOf, vhr.WaterLevel) in g
    assert (vhr.FloodControlWaterLevel, RDFS.subClassOf, vhr.WaterLevel) in g
    assert (vhr.DesignFloodWaterLevel, RDFS.subClassOf, vhr.WaterLevel) in g
    assert (vhr.CheckFloodWaterLevel, RDFS.subClassOf, vhr.WaterLevel) in g

    # Check Hoa Binh MNDBT vs MNC assertions in ontology
    hb_mndbt_param = list(g.objects(vhr.HoaBinh_MNDBT_Assertion, vhr.hasParameter))[0]
    hb_mnc_param = list(g.objects(vhr.HoaBinh_MNC_Assertion, vhr.hasParameter))[0]

    assert hb_mndbt_param == vhr.NormalPoolWaterLevel
    assert hb_mnc_param == vhr.DeadWaterLevel
    assert hb_mndbt_param != hb_mnc_param, "MNDBT and MNC must not share the identical parameter identity URI"


def test_factual_provenance_explicit_linking():
    """All MeasurementAssertion instances must link to verified EvidenceRegion instances."""
    ontology = HydraulicOntology.load(ONTOLOGY_FILE)
    g = ontology.graph
    vhr = rdflib.Namespace("http://vietirr-rag.org/ontology/hydraulic#")

    for assertion in [
        vhr.HoaBinh_MNDBT_Assertion,
        vhr.HoaBinh_MNC_Assertion,
        vhr.SonLa_MNDBT_Assertion,
        vhr.SonLa_MNC_Assertion,
    ]:
        ev_regions = list(g.objects(assertion, vhr.supportedByEvidence))
        assert len(ev_regions) == 1, f"Assertion {assertion} must link to exactly 1 EvidenceRegion"
        ev = ev_regions[0]
        assert (ev, RDF.type, vhr.EvidenceRegion) in g

        # Document ID must be verified
        doc_ids = list(g.objects(ev, vhr.documentId))
        assert len(doc_ids) == 1
        assert str(doc_ids[0]) == "IRR_CP_2019_ee0bca33"

        # Page must be valid integer
        pages = list(g.objects(ev, vhr.pageNumber))
        assert len(pages) == 1
        assert int(pages[0]) == 4

        # Region ID must not be empty or fabricated
        region_ids = list(g.objects(ev, vhr.regionId))
        assert len(region_ids) == 1
        assert "REG_IRR_CP_2019_ee0bca33_P0004_" in str(region_ids[0])


def test_source_verification_policy_audit():
    """A constraint with missing provenance cannot be promoted to active verified status."""
    fake_rule = VerificationConstraint(
        constraint_id="CONST-UNVERIFIED-CLAIM",
        name="Fake Verified Rule",
        description="Claims to be verified without source document",
        constraint_type="SOURCE_VERIFIED_FACT",
        applicable_class="Reservoir",
        validation_status="VERIFIED_SOURCE",
        source_reference="trust me bro",
        explanation="Testing audit failure",
        document_id=None,
        quoted_evidence=None,
    )
    ok, reason = fake_rule.audit_provenance()
    assert not ok
    assert "lacks a traceable SourceValidationRecord" in reason or "missing" in reason.lower()
    assert not fake_rule.is_verified()

    # In Registry, fake rule must be rejected from active verified
    registry = ConstraintRegistry()
    registry.register(fake_rule)
    active = registry.get_active_constraints(only_verified=True)
    assert not any(c.constraint_id == "CONST-UNVERIFIED-CLAIM" for c in active)

    # Check activation log explains reason
    log = registry.get_activation_log()
    assert any(e["constraint_id"] == "CONST-UNVERIFIED-CLAIM" and "INACTIVE" in e["status"] for e in log)


def test_source_verification_rejects_fake_doc_id():
    """Adversarial test: constraint claiming VERIFIED_SOURCE with fake document ID is rejected."""
    from viirr_ontology.domain.classes import SourceValidationRecord

    fake_rule = VerificationConstraint(
        constraint_id="CONST-ADV-FAKE-DOC",
        name="Fake Doc Rule",
        description="Plausible claim with fake doc ID",
        constraint_type="SOURCE_VERIFIED_FACT",
        applicable_class="Reservoir",
        document_id="DOC_FAKE_2026_9999",
        source_reference="Điều 1 Fake",
        validation_status="VERIFIED_SOURCE",
        validation_record=SourceValidationRecord(
            source_document_id="DOC_FAKE_2026_9999",
            citation_key="DOC_FAKE_2026_9999:P0001",
            verification_method="MECHANICAL_TEXT_MATCH",
            verification_outcome="VALID",
        ),
    )
    ok, reason = fake_rule.audit_provenance()
    assert not ok
    assert "fake or unresolved document_id" in reason


def test_source_verification_rejects_revoked_record():
    """Adversarial test: constraint with revoked validation record is rejected."""
    from viirr_ontology.domain.classes import SourceValidationRecord

    revoked_rule = VerificationConstraint(
        constraint_id="CONST-ADV-REVOKED",
        name="Revoked Rule",
        description="Evidence was revoked",
        constraint_type="SOURCE_VERIFIED_FACT",
        applicable_class="Reservoir",
        document_id="IRR_CP_2019_ee0bca33",
        source_reference="Điều 5",
        validation_status="VERIFIED_SOURCE",
        validation_record=SourceValidationRecord(
            source_document_id="IRR_CP_2019_ee0bca33",
            citation_key="IRR_CP_2019_ee0bca33:P0004",
            verification_method="EXPERT_CONFIRMED",
            verification_outcome="REVOKED",
            notes="Revoked due to calculation re-assessment",
        ),
    )
    ok, reason = revoked_rule.audit_provenance()
    assert not ok
    assert "REVOKED" in reason


def test_source_verification_rejects_pending_expert_review():
    """Adversarial test: rule with PENDING_EXPERT_REVIEW cannot become active."""
    from viirr_ontology.domain.classes import SourceValidationRecord

    pending_rule = VerificationConstraint(
        constraint_id="CONST-ADV-PENDING",
        name="Pending Rule",
        description="Text matched but legal interpretation pending",
        constraint_type="SOURCE_VERIFIED_FACT",
        applicable_class="Reservoir",
        document_id="IRR_CP_2019_ee0bca33",
        source_reference="Điều 5",
        validation_status="VERIFIED_SOURCE",
        validation_record=SourceValidationRecord(
            source_document_id="IRR_CP_2019_ee0bca33",
            citation_key="IRR_CP_2019_ee0bca33:P0004",
            verification_method="PENDING_EXPERT_REVIEW",
            verification_outcome="VALID",
        ),
    )
    ok, reason = pending_rule.audit_provenance()
    assert not ok
    assert "PENDING_EXPERT_REVIEW" in reason


def test_measurement_assertion_not_inferred_as_hydraulic_structure():
    """Phase 0 Fix 3.3: MeasurementAssertion must not be inferred as a HydraulicStructure under RDFS reasoning."""
    import owlrl

    ontology = HydraulicOntology.load(ONTOLOGY_FILE)
    g = rdflib.Graph()
    for triple in ontology.graph:
        g.add(triple)
    owlrl.RDFSClosure.RDFS_Semantics(g, False, False, False).closure()
    vhr = rdflib.Namespace("http://vietirr-rag.org/ontology/hydraulic#")
    assert (vhr.HoaBinh_MNDBT_Assertion, RDF.type, vhr.MeasurementAssertion) in g
    assert (vhr.HoaBinh_MNDBT_Assertion, RDF.type, vhr.HydraulicStructure) not in g


def test_structural_vs_source_dependent_separation():
    """Structural rules and source-dependent rules must be cleanly partitioned."""
    registry = ConstraintRegistry.load_from_file(CONSTRAINTS_FILE)

    structural = registry.get_structural_constraints()
    source_dep = registry.get_source_dependent_constraints()

    assert len(structural) >= 3
    assert len(source_dep) >= 5

    # No overlap
    struct_ids = {c.constraint_id for c in structural}
    source_ids = {c.constraint_id for c in source_dep}
    assert struct_ids.isdisjoint(source_ids)

    # Structural rules must be SCHEMA_TYPE or UNIT_COMPATIBILITY
    for c in structural:
        assert c.is_structural()
        assert c.constraint_type in {"SCHEMA_TYPE", "UNIT_COMPATIBILITY"}

    # Source-dependent rules must be SOURCE_VERIFIED_FACT or LEGAL_APPLICABILITY
    for c in source_dep:
        assert c.is_source_dependent()
        assert c.constraint_type in {"SOURCE_VERIFIED_FACT", "LEGAL_APPLICABILITY"}


def test_duplicate_conflicting_constraint_id_rejection():
    """Duplicate conflicting constraint IDs must be rejected immediately on load."""
    registry = ConstraintRegistry()
    registry.register(
        VerificationConstraint(
            constraint_id="CONST-DUP-01",
            name="First Rule",
            description="First definition",
            constraint_type="SCHEMA_TYPE",
            applicable_class="TechnicalParameter",
            validation_status="VERIFIED_SOURCE",
            source_reference="Schema Spec",
            explanation="First explanation",
        )
    )

    duplicate_data = {
        "constraints": [
            {
                "constraint_id": "CONST-DUP-01",
                "name": "Conflicting Second Rule",
                "description": "Second definition with same ID",
                "constraint_type": "UNIT_COMPATIBILITY",
                "applicable_class": "TechnicalParameter",
                "validation_status": "DRAFT_UNVERIFIED",
                "source_reference": "Another Spec",
                "explanation": "Conflicting explanation",
            }
        ]
    }
    with pytest.raises(ValueError, match="Duplicate conflicting constraint ID"):
        registry.load_from_dict(duplicate_data)


def test_legal_fact_audit_decision_740_scope():
    """CONST-LEGAL-SCOPE-01 must cover exactly 7 Red River reservoirs and exclude Đồng Nai."""
    registry = ConstraintRegistry.load_from_file(CONSTRAINTS_FILE)
    c = registry.get_constraint("CONST-LEGAL-SCOPE-01")
    assert c is not None

    # Must NOT include Dong Nai
    assert "Đồng Nai" not in c.quoted_evidence
    assert "Đồng Nai" not in c.source_reference

    # Must include all 7 reservoirs specified in Article 1
    seven_reservoirs = ["Sơn La", "Hòa Bình", "Thác Bà", "Tuyên Quang", "Lai Châu", "Bản Chát", "Huội Quảng"]
    for res in seven_reservoirs:
        assert res in c.quoted_evidence, f"Reservoir {res} missing from QĐ 740 scope"


def test_legal_fact_audit_decision_922_date_and_amendment():
    """Doc_QD_922_TTg_2025 must record signed date 2025-05-14 and amend QĐ 740."""
    ontology = HydraulicOntology.load(ONTOLOGY_FILE)
    g = ontology.graph
    vhr = rdflib.Namespace("http://vietirr-rag.org/ontology/hydraulic#")

    doc_922 = vhr.Doc_QD_922_TTg_2025
    doc_740 = vhr.Doc_QD_740_TTg_2019

    # Publication date must be 2025-05-14
    dates = list(g.objects(doc_922, vhr.publicationDate))
    assert len(dates) == 1
    assert str(dates[0]) == "2025-05-14"

    # Must have amendsStandard relationship to QĐ 740
    assert (doc_922, vhr.amendsStandard, doc_740) in g
    # Phase 0 Fix 3.2: amendsStandard must be distinct from supersedesVersion (NOT subProperty)
    assert (vhr.amendsStandard, RDFS.subPropertyOf, vhr.supersedesVersion) not in g
    assert (doc_922, vhr.supersedesVersion, doc_740) not in g

    # QĐ 740 legally supersedes QĐ 1622/2015
    doc_1622 = vhr.Doc_QD_1622_TTg_2015
    assert (doc_740, vhr.supersedesVersion, doc_1622) in g


def test_legal_fact_audit_2026_unresolved_decision():
    """2026 Decisions (1936 vs 1928) must preserve UNKNOWN status and remain DRAFT_UNVERIFIED."""
    ontology = HydraulicOntology.load(ONTOLOGY_FILE)
    g = ontology.graph
    vhr = rdflib.Namespace("http://vietirr-rag.org/ontology/hydraulic#")

    doc_2026 = vhr.Doc_QD_RedRiver_2026_Unresolved
    assert (doc_2026, RDF.type, vhr.OperatingProcedure) in g

    versions = list(g.objects(doc_2026, vhr.documentVersion))
    assert len(versions) == 1
    assert str(versions[0]) == "UNKNOWN"

    registry = ConstraintRegistry.load_from_file(CONSTRAINTS_FILE)
    c_2026 = registry.get_constraint("CONST-LEGAL-SCOPE-2026-UNRESOLVED")
    assert c_2026 is not None
    assert c_2026.validation_status == "DRAFT_UNVERIFIED"
    assert c_2026.document_version == "UNKNOWN"
    # Must NOT be in active verified set
    active = registry.get_active_constraints(only_verified=True)
    assert not any(c.constraint_id == "CONST-LEGAL-SCOPE-2026-UNRESOLVED" for c in active)


def test_unit_matching_ambiguity_rejection():
    """Unit matching must reject multi-parameter phrases with conflicting dimensions instead of arbitrary substring selection."""
    # Multi-parameter phrase: "lưu lượng" (FLOW_RATE) + "mực nước" (LENGTH)
    ok, msg = check_unit_compatibility("đo lưu lượng và mực nước", "m3/s")
    assert not ok
    assert "Ambiguous multi-parameter phrase" in msg
    assert "conflicting dimensions" in msg.lower()

    # Opposite unit for same multi-parameter phrase
    ok2, msg2 = check_unit_compatibility("đo lưu lượng và mực nước", "m")
    assert not ok2
    assert "Ambiguous multi-parameter phrase" in msg2

    # Canonical match takes precedence: single parameter phrases remain fully valid
    ok3, msg3 = check_unit_compatibility("lưu lượng xả đáy", "m3/s")
    assert ok3
    assert "FLOW_RATE" in msg3

    ok4, msg4 = check_unit_compatibility("mực nước thượng lưu", "m")
    assert ok4
    assert "LENGTH" in msg4
