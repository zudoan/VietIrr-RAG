"""Ontology loader and RDF/OWL query helper using rdflib.

Loads `ontology/viirr_hydraulic_v0_1.ttl` and provides methods for inspecting classes,
properties, instances, and running SPARQL queries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import rdflib
from rdflib.namespace import OWL, RDF, RDFS, XSD


DEFAULT_ONTOLOGY_FILE = Path(__file__).resolve().parents[3] / "ontology" / "viirr_hydraulic_v0_1.ttl"
VHR_NS = rdflib.Namespace("http://vietirr-rag.org/ontology/hydraulic#")


class HydraulicOntology:
    """Wrapper around RDFLib Graph for the VietIRR Hydraulic Domain Ontology."""

    def __init__(self, graph: rdflib.Graph, ontology_path: Optional[Path] = None) -> None:
        self.graph = graph
        self.ontology_path = ontology_path

    @classmethod
    def load(cls, filepath: Optional[Path | str] = None) -> HydraulicOntology:
        """Parse the Turtle ontology file into an rdflib Graph."""
        target_path = Path(filepath) if filepath else DEFAULT_ONTOLOGY_FILE
        if not target_path.exists():
            raise FileNotFoundError(f"Ontology file not found at: {target_path}")

        graph = rdflib.Graph()
        graph.parse(str(target_path), format="turtle")
        return cls(graph=graph, ontology_path=target_path)

    def get_classes(self) -> list[str]:
        """Return all declared owl:Class or rdfs:Class URIs."""
        classes = set()
        for s in self.graph.subjects(RDF.type, OWL.Class):
            classes.add(str(s))
        for s in self.graph.subjects(RDF.type, RDFS.Class):
            classes.add(str(s))
        return sorted(list(classes))

    def get_subclasses(self, parent_name_or_uri: str) -> list[str]:
        """Return all immediate subclasses of a given class."""
        if "#" in parent_name_or_uri or "/" in parent_name_or_uri:
            parent_uri = rdflib.URIRef(parent_name_or_uri)
        else:
            parent_uri = VHR_NS[parent_name_or_uri]

        subclasses = []
        for s in self.graph.subjects(RDFS.subClassOf, parent_uri):
            subclasses.append(str(s))
        return sorted(subclasses)

    def get_object_properties(self) -> list[str]:
        """Return all declared owl:ObjectProperty URIs."""
        props = set()
        for s in self.graph.subjects(RDF.type, OWL.ObjectProperty):
            props.add(str(s))
        return sorted(list(props))

    def get_datatype_properties(self) -> list[str]:
        """Return all declared owl:DatatypeProperty URIs."""
        props = set()
        for s in self.graph.subjects(RDF.type, OWL.DatatypeProperty):
            props.add(str(s))
        return sorted(list(props))

    def get_structures(self) -> list[dict[str, Any]]:
        """Return all instances of HydraulicStructure and its subclasses."""
        structures = []
        query = """
        PREFIX vhr: <http://vietirr-rag.org/ontology/hydraulic#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

        SELECT ?s ?type ?label ?canonicalName
        WHERE {
            ?s a ?type .
            ?type rdfs:subClassOf* vhr:HydraulicStructure .
            OPTIONAL { ?s rdfs:label ?label }
            OPTIONAL { ?s vhr:canonicalName ?canonicalName }
        }
        """
        results = self.graph.query(query)
        for row in results:
            structures.append(
                {
                    "uri": str(row[0]),
                    "type": str(row[1]),
                    "label": str(row[2]) if row[2] else None,
                    "canonical_name": str(row[3]) if row[3] else None,
                }
            )
        return structures

    def get_measurement_assertions(self) -> list[dict[str, Any]]:
        """Return all n-ary MeasurementAssertion instances with full contextual fields."""
        assertions = []
        query = """
        PREFIX vhr: <http://vietirr-rag.org/ontology/hydraulic#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

        SELECT ?m ?structure ?param ?val ?unit ?doc ?comment
        WHERE {
            ?m a vhr:MeasurementAssertion ;
               vhr:hasStructure ?structure ;
               vhr:hasParameter ?param ;
               vhr:hasNumericValue ?val ;
               vhr:hasUnit ?unit .
            OPTIONAL { ?m vhr:definedInStandard ?doc }
            OPTIONAL { ?m rdfs:comment ?comment }
        }
        """
        results = self.graph.query(query)
        for row in results:
            assertions.append(
                {
                    "assertion_uri": str(row[0]),
                    "structure_uri": str(row[1]),
                    "parameter_uri": str(row[2]),
                    "numeric_value": float(row[3]),
                    "unit_uri": str(row[4]),
                    "document_uri": str(row[5]) if row[5] else None,
                    "comment": str(row[6]) if row[6] else None,
                }
            )
        return assertions

    def query_sparql(self, query: str) -> list[dict[str, Any]]:
        """Execute an arbitrary SPARQL SELECT query on the ontology graph."""
        res = self.graph.query(query)
        rows = []
        for r in res:
            row_dict = {}
            for var in res.vars:
                val = r[var]
                row_dict[str(var)] = str(val) if val is not None else None
            rows.append(row_dict)
        return rows
