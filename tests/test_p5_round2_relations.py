from __future__ import annotations

import json

import pytest

from viirr_rag.pipeline import Evidence, build_context, enforce_citation_grounding, parse_generation


def evidence(block: int, text: str, *, group: str = "", role: str = "") -> Evidence:
    return Evidence(
        rank=block,
        evidence_id=f"ROUND2_P0001_B{block:03d}",
        doc_id="ROUND2",
        page_id="PAGE_ROUND2_0001",
        page_number=1,
        unit_type="TEXT_REGION",
        score=1.0,
        text=text,
        source="synthetic_p5_round2",
        context_group=group,
        context_role=role,
    )


def citation(item: Evidence) -> dict[str, object]:
    return {
        "doc_id": item.doc_id,
        "page_number": item.page_number,
        "evidence_id": item.evidence_id,
    }


def generated(answer: str, items: list[Evidence]):
    return parse_generation(
        json.dumps(
            {
                "answer": answer,
                "citations": [citation(item) for item in items],
                "abstained": False,
                "abstention_reason": "",
                "evidence_supported": True,
            }
        )
    )


def assessed(answer: str, items: list[Evidence]):
    return enforce_citation_grounding(generated(answer, items), build_context(items, 500))


@pytest.mark.parametrize(
    ("source", "wrong_answer", "correct_answer"),
    [
        (
            "Tram R17, DO 4.93 mg/L, BOD 7.5 mg/L.",
            "Tram R17 co DO 7.5 mg/L.",
            "Tram R17 co DO 4.93 mg/L.",
        ),
        (
            "Nam 2021 tram R17 co DO 4.93 mg/L va nam 2022 co DO 7.5 mg/L.",
            "Nam 2021 tram R17 co DO 7.5 mg/L.",
            "Nam 2021 tram R17 co DO 4.93 mg/L.",
        ),
        (
            "Tram R17 co DO 4.93 mg/L, trong khi tram R42 co DO 7.5 mg/L.",
            "Tram R17 co DO 7.5 mg/L.",
            "Tram R17 co DO 4.93 mg/L.",
        ),
        (
            "Ho Delta co dung tich phong lu 9.5 trieu m3 va dung tich huu ich 8.0 trieu m3.",
            "Ho Delta co dung tich phong lu 8.0 trieu m3.",
            "Ho Delta co dung tich phong lu 9.5 trieu m3.",
        ),
    ],
)
def test_narrative_relations_bind_attribute_value_entity_and_time(source, wrong_answer, correct_answer):
    item = evidence(1, source)

    wrong_result, wrong_audit = assessed(wrong_answer, [item])
    correct_result, correct_audit = assessed(correct_answer, [item])

    assert wrong_result.abstained is True
    assert wrong_audit["support_status"] in {"CONTRADICTED", "INSUFFICIENT"}
    assert correct_result.abstained is False
    assert correct_audit["support_status"] == "SUPPORTED"


def test_structured_table_binds_header_column_to_its_value():
    header = evidence(1, "Tram DO BOD (mg/L)", group="TABLE:ROUND2", role="table_header_or_unit")
    row = evidence(2, "R17 4.93 7.5", group="TABLE:ROUND2", role="table_row")

    wrong_result, wrong_audit = assessed("Tram R17 co DO la 7.5 mg/L.", [header, row])
    correct_result, correct_audit = assessed("Tram R17 co DO la 4.93 mg/L.", [header, row])

    assert wrong_result.abstained is True
    assert wrong_audit["support_status"] in {"CONTRADICTED", "INSUFFICIENT"}
    assert correct_result.abstained is False
    assert correct_audit["support_status"] == "SUPPORTED"


@pytest.mark.parametrize(
    "source",
    [
        "Truong hop duoi 5% do cap xa xu ly, truong hop tu 5% tro len do Chu tich UBND cap tinh quyet dinh.",
        "Truong hop duoi 5% do cap xa xu ly; truong hop tu 5% tro len do Chu tich UBND cap tinh quyet dinh.",
    ],
)
def test_legal_condition_survives_punctuation_and_word_boundary(source):
    item = evidence(1, source, group="LEGAL:ROUND2", role="legal_condition")
    result, audit = assessed(
        "Truong hop tu 5% tro len do Chu tich UBND cap tinh quyet dinh.",
        [item],
    )

    assert result.abstained is False
    assert audit["support_status"] == "SUPPORTED"


def test_legal_body_is_not_assumed_equivalent_to_its_chairperson():
    item = evidence(
        1,
        "Truong hop tu 5% tro len do Chu tich UBND cap tinh quyet dinh.",
        group="LEGAL:ROUND2",
        role="legal_condition",
    )

    result, audit = assessed(
        "Truong hop tu 5% tro len do UBND cap tinh quyet dinh.",
        [item],
    )
    correct_result, correct_audit = assessed(
        "Truong hop tu 5% tro len do Chu tich UBND cap tinh quyet dinh.",
        [item],
    )

    assert result.abstained is True
    assert audit["support_status"] == "INSUFFICIENT"
    assert correct_result.abstained is False
    assert correct_audit["support_status"] == "SUPPORTED"


def test_missing_table_metadata_does_not_infer_column_alignment():
    item = evidence(1, "R99 2.1 8.4")
    result, audit = assessed("Tram R99 co DO 2.1 mg/L.", [item])

    assert result.abstained is True
    assert audit["support_status"] == "INSUFFICIENT"


def test_multiple_claims_require_each_relation_to_be_established():
    item = evidence(1, "Tram R17 co DO 4.93 mg/L va BOD 7.5 mg/L.")
    result, audit = assessed("Tram R17 co DO 4.93 mg/L. Tram R17 co BOD 4.93 mg/L.", [item])

    assert result.abstained is True
    assert [claim["status"] for claim in audit["claim_support"]] == ["SUPPORTED", "CONTRADICTED"]
