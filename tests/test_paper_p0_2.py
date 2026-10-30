from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_paper_p0_audit as audit  # noqa: E402
import build_paper_p0_2_artifacts as p02  # noqa: E402
import compute_p0_2_iaa as iaa  # noqa: E402


@pytest.mark.parametrize(
    ("accented", "plain"),
    [
        ("Bảng mực nước hồ chứa", "bang muc nuoc ho chua"),
        ("Mâu thuẫn nguồn", "mau thuan nguon"),
        ("Quyết định số 922/QĐ-TTg", "quyet dinh so 922 qd ttg"),
        ("đập Đáy", "dap day"),
    ],
)
def test_vietnamese_diacritic_folding(accented: str, plain: str):
    assert audit.fold_vietnamese(accented) == audit.fold_vietnamese(plain)


def test_modality_does_not_use_question_keyword():
    row = {"question": "Bảng scan này ghi gì?", "evidence": [{"doc_id": "D1"}]}
    modality, reasons = p02.source_aware_modality(row, {})
    assert modality == "UNKNOWN"
    assert reasons == ["insufficient_source_metadata_and_pdf_signal"]


def test_accented_source_metadata_detects_table_scan():
    row = {
        "generation_method": "Đọc BẢNG theo hàng và cột",
        "joint_audit_08_09": "OCR_SCAN_NUMERIC_UNSAFE",
        "evidence": [{"doc_id": "D1", "source_locator": "Bảng 2, hàng CL3, cột Max"}],
    }
    modality, reasons = p02.source_aware_modality(row, {})
    assert modality == "TABLE_SCAN"
    assert "explicit_source_table_metadata" in reasons
    assert "explicit_scan_or_numeric_unsafe_metadata" in reasons


def test_anchor_classes_are_not_collapsed_to_manual_confirmation():
    page_text = {("D1", 2): "Muc nuoc ho la 24,00 m."}
    actual, _ = p02.evidence_anchor_class(
        {"doc_id": "D1", "pdf_page": 2, "source_anchor": "Mực nước hồ"}, page_text)
    machine, _ = p02.evidence_anchor_class(
        {"doc_id": "D1", "pdf_page": 3, "source_anchor": "khác", "anchor_found_on_page": True}, page_text)
    visual, _ = p02.evidence_anchor_class(
        {"doc_id": "D1", "pdf_page": 3, "locator_patch_status": "VISUALLY_CONFIRMED_APPLIED"}, page_text)
    missing, _ = p02.evidence_anchor_class({"doc_id": "D1", "pdf_page": 3}, page_text)
    assert actual == "ACTUAL_TEXT_MATCH"
    assert machine == "EXISTING_MACHINE_FLAG"
    assert visual == "VERIFIED_VISUAL_LOCATOR"
    assert missing == "UNVERIFIED"


def test_risks_use_competency_and_source_metadata_with_accents():
    row = {
        "competency": "INSUFFICIENT_EVIDENCE_DETECTION",
        "review_flags": ["MÂU THUẪN NGUỒN"],
        "evidence": [{"doc_id": "D1", "source_document_title": "Quyết định vận hành"}],
    }
    manifest = {"D1": {"source_title": "Quyết định số 1 sửa đổi quy trình"}}
    assert p02.source_risks(row, manifest) == {
        "LEGAL_VERSION_TEMPORAL", "ABSTENTION", "SOURCE_CONFLICT"}


def test_blinded_packet_omits_internal_judgements():
    source = {
        "candidate_id": "CG-20261016-001", "question": "Câu hỏi?", "answer": "Đáp án",
        "review_status": "REVIEW_REQUIRED", "review_flags": ["X"], "difficulty": "HARD",
        "evidence": [{"doc_id": "D1", "pdf_page": 1, "source_anchor": "neo"}],
    }
    packet = p02.blinded_record(source, "P02-A-001")
    serialized = json.dumps(packet, ensure_ascii=False)
    for forbidden in ("review_status", "review_flags", "difficulty", "machine_supported", "audit"):
        assert forbidden not in serialized.casefold()


def test_iaa_metrics_and_empty_mses_guard():
    pairs = [("PASS", "PASS"), ("PASS", "FAIL"), ("FAIL", "FAIL")]
    assert iaa.percent_agreement(pairs) == pytest.approx(2 / 3)
    assert iaa.cohens_kappa(pairs) is not None
    assert iaa.krippendorff_alpha_nominal(pairs) is not None
    assert iaa.best_set_jaccard([frozenset({"E1", "E2"})], [frozenset({"E2", "E3"})]) == pytest.approx(1 / 3)
    with pytest.raises(ValueError, match="Empty MSES"):
        iaa.normalized_mses([[]])


def test_annotation_schema_forbids_automatic_empty_mses_success():
    schema = p02.annotation_schema()
    assert schema["x_constraints"]["empty_mses_is_not_success"] is True
    assert schema["x_constraints"]["unanswerable_requires_negative_evidence_search"] is True
    assert schema["x_constraints"]["machine_flag_is_not_human_confirmation"] is True
    decision_enum = schema["properties"]["annotation"]["properties"]["decision"]["enum"]
    assert "RECOMMEND_ACCEPT" in decision_enum
    assert "ACCEPT_GOLD" not in decision_enum
