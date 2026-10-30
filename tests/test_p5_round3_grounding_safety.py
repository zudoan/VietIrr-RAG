from __future__ import annotations

import json

import pytest

from viirr_rag.pipeline import Evidence, build_context, enforce_citation_grounding, parse_generation


def evidence(block: int, text: str, *, group: str = "", role: str = "") -> Evidence:
    return Evidence(
        rank=block,
        evidence_id=f"ROUND3_P0001_B{block:03d}",
        doc_id="ROUND3",
        page_id="PAGE_ROUND3_0001",
        page_number=1,
        unit_type="TEXT_REGION",
        score=1.0,
        text=text,
        source="synthetic_p5_round3",
        context_group=group,
        context_role=role,
    )


def assessed(answer: str, items: list[Evidence]):
    generation = parse_generation(
        json.dumps(
            {
                "answer": answer,
                "citations": [
                    {"doc_id": item.doc_id, "page_number": item.page_number, "evidence_id": item.evidence_id}
                    for item in items
                ],
                "abstained": False,
                "abstention_reason": "",
                "evidence_supported": True,
            }
        )
    )
    return enforce_citation_grounding(generation, build_context(items, 500))


@pytest.mark.parametrize(
    ("items", "wrong_answer", "correct_answer"),
    [
        (
            [evidence(1, "Tram X31 co DO 3.2 mg/L va BOD 6.8 mg/L.")],
            "Tram X31 co DO 3.2 mg/L va BOD 3.2 mg/L.",
            "Tram X31 co DO 3.2 mg/L va BOD 6.8 mg/L.",
        ),
        (
            [
                evidence(1, "Tram DO BOD (mg/L)", group="TABLE:ROUND3", role="table_header_or_unit"),
                evidence(2, "X31 3.2 6.8", group="TABLE:ROUND3", role="table_row"),
            ],
            "Tram X31 co DO 3.2 mg/L va BOD 3.2 mg/L.",
            "Tram X31 co DO 3.2 mg/L va BOD 6.8 mg/L.",
        ),
        (
            [evidence(1, "Nam 2031 tram X31 co DO 3.2 mg/L va nam 2032 co DO 6.8 mg/L.")],
            "Nam 2031 tram X31 co DO 3.2 mg/L va nam 2032 co DO 3.2 mg/L.",
            "Nam 2031 tram X31 co DO 3.2 mg/L va nam 2032 co DO 6.8 mg/L.",
        ),
        (
            [evidence(1, "Tram X31 co DO 3.2 mg/L, trong khi tram X32 co DO 6.8 mg/L.")],
            "Tram X31 co DO 3.2 mg/L va tram X32 co DO 3.2 mg/L.",
            "Tram X31 co DO 3.2 mg/L va tram X32 co DO 6.8 mg/L.",
        ),
    ],
)
def test_multifact_aggregation_requires_every_relation(items, wrong_answer, correct_answer):
    wrong_result, wrong_audit = assessed(wrong_answer, items)
    correct_result, correct_audit = assessed(correct_answer, items)

    assert wrong_result.abstained is True
    assert wrong_audit["support_status"] == "CONTRADICTED"
    assert any(item["status"] == "CONTRADICTED" for item in wrong_audit["claim_support"][0]["detectors"][0]["relation_verdicts"])
    assert correct_result.abstained is False
    assert correct_audit["support_status"] == "SUPPORTED"


@pytest.mark.parametrize(
    ("source", "opposite_answer", "matching_answer"),
    [
        (
            "Tram X31 khong dat DO 3.2 mg/L.",
            "Tram X31 dat DO 3.2 mg/L.",
            "Tram X31 khong dat DO 3.2 mg/L.",
        ),
        (
            "Tram X31 chua dat DO 3.2 mg/L.",
            "Tram X31 dat DO 3.2 mg/L.",
            "Tram X31 chua dat DO 3.2 mg/L.",
        ),
        (
            "Tram X31 dat DO 3.2 mg/L.",
            "Tram X31 khong dat DO 3.2 mg/L.",
            "Tram X31 dat DO 3.2 mg/L.",
        ),
    ],
)
def test_factual_negation_is_part_of_relation(source, opposite_answer, matching_answer):
    item = evidence(1, source)
    opposite_result, opposite_audit = assessed(opposite_answer, [item])
    matching_result, matching_audit = assessed(matching_answer, [item])

    assert opposite_result.abstained is True
    assert opposite_audit["support_status"] == "CONTRADICTED"
    assert matching_result.abstained is False
    assert matching_audit["support_status"] == "SUPPORTED"


def test_ambiguous_negation_without_a_numeric_relation_is_insufficient():
    item = evidence(1, "Tram X31 chua cong bo ket qua quan trac.")
    result, audit = assessed("Tram X31 khong dat DO 3.2 mg/L.", [item])

    assert result.abstained is True
    assert audit["support_status"] == "INSUFFICIENT"


@pytest.mark.parametrize(
    ("wrong_answer", "correct_answer"),
    [
        (
            "Truong hop tu 5% tro len do Chu tich UBND cap tinh khong quyet dinh tai tinh Alpha.",
            "Truong hop tu 5% tro len do Chu tich UBND cap tinh quyet dinh tai tinh Alpha.",
        ),
        (
            "Truong hop tu 5% tro len do Chu tich UBND cap tinh phe duyet tai tinh Alpha.",
            "Truong hop tu 5% tro len do Chu tich UBND cap tinh quyet dinh tai tinh Alpha.",
        ),
        (
            "Truong hop tu 5% tro len do Chu tich UBND cap tinh quyet dinh tai tinh Beta.",
            "Truong hop tu 5% tro len do Chu tich UBND cap tinh quyet dinh tai tinh Alpha.",
        ),
    ],
)
def test_legal_relation_binds_action_polarity_and_jurisdiction(wrong_answer, correct_answer):
    item = evidence(
        1,
        "Truong hop tu 5% tro len do Chu tich UBND cap tinh quyet dinh tai tinh Alpha.",
        group="LEGAL:ROUND3",
        role="legal_condition",
    )
    wrong_result, wrong_audit = assessed(wrong_answer, [item])
    correct_result, correct_audit = assessed(correct_answer, [item])

    assert wrong_result.abstained is True
    assert wrong_audit["support_status"] == "CONTRADICTED"
    assert correct_result.abstained is False
    assert correct_audit["support_status"] == "SUPPORTED"


def test_legal_relation_requires_action_and_jurisdiction_when_evidence_has_them():
    item = evidence(
        1,
        "Truong hop tu 5% tro len do Chu tich UBND cap tinh quyet dinh tai tinh Alpha.",
        group="LEGAL:ROUND3",
        role="legal_condition",
    )
    result, audit = assessed("Truong hop tu 5% tro len do Chu tich UBND cap tinh.", [item])

    assert result.abstained is True
    assert audit["support_status"] == "INSUFFICIENT"
