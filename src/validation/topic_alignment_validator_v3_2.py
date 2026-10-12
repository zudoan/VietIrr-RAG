"""Independent V3.2 question-topic/answer/evidence alignment validator."""

from __future__ import annotations

from dataclasses import dataclass
import re

from src.structure.semantic_table_parser import fold


@dataclass(frozen=True)
class TopicSpec:
    name: str
    question_cues: tuple[str, ...]
    support_cues: tuple[str, ...]


TOPICS = (
    TopicSpec("SALINITY", ("xam nhap man", "do man"), ("xam nhap man", "do man", "man dao dong", "nong do man")),
    TopicSpec("DISCHARGE", ("luu luong",), ("luu luong", "tong luong dong chay", "dong chay mua lu")),
    TopicSpec("DAM_SAFETY", ("an toan dap", "an toan ho chua"), ("an toan dap", "an toan ho chua", "an toan cong trinh dau moi")),
    TopicSpec("RESERVOIR_OPERATION", ("van hanh ho chua", "van hanh lien ho", "dieu tiet ho"), ("van hanh ho chua", "van hanh lien ho", "quy trinh van hanh", "qtvh lien ho", "dieu tiet", "xa lu", "mo cong", "dong cong")),
    # Cao trinh is an elevation concept.  It must not be accepted as evidence
    # for a question asking about water level unless the source explicitly
    # identifies the elevation as a water-surface/water-level elevation.
    TopicSpec("WATER_LEVEL", ("muc nuoc",), ("muc nuoc", "cao trinh muc nuoc", "cao trinh mat nuoc")),
    TopicSpec("ELEVATION", ("cao trinh", "cao do"), ("cao trinh", "cao do")),
    TopicSpec("RAINFALL", ("luong mua",), ("luong mua",)),
    TopicSpec("STORAGE", ("dung tich", "tru luong"), ("dung tich", "tru luong", "dttk")),
    TopicSpec("WATER_QUALITY", ("chat luong nuoc", "wqi", "bod", "cod", "tss", "oxy hoa tan"), ("chat luong nuoc", "wqi", "bod", "cod", "tss", "oxy hoa tan", "do dam bao", "do duc")),
    TopicSpec("WATER_SUPPLY", ("cap nuoc",), ("cap nuoc", "cung cap nuoc", "lay nuoc")),
    TopicSpec("IRRIGATION_AGRICULTURE", ("tuoi va san xuat nong nghiep", "tuoi", "san xuat nong nghiep"), ("tuoi", "san xuat nong nghiep", "tuoi tieu", "gieo trong", "gieo cay")),
    TopicSpec("AREA", ("dien tich",), ("dien tich",)),
    TopicSpec("WATER_SOURCE", ("nguon nuoc", "ke hoach su dung nuoc"), ("nguon nuoc", "dung tich", "muc nuoc", "luong mua", "luu luong", "dong chay", "cap nuoc", "thieu nuoc", "su dung nuoc", "tich nuoc")),
    TopicSpec("DISASTER_PREVENTION", ("phong chong thien tai",), ("phong chong thien tai", "ung pho thien tai", "bao dam an toan", "phong chong bao lu")),
    TopicSpec("DROUGHT_SHORTAGE", ("han han", "thieu nuoc"), ("han han", "thieu nuoc", "kho han")),
    TopicSpec("FLOOD", ("ngap ung", "lu lut", "lu lon"), ("ngap ung", "lu lut", "lu lon", "ngap lut")),
)


def _norm(value: str) -> str:
    """Fold accents and make punctuation irrelevant to phrase matching."""
    return re.sub(r"[^a-z0-9%+/-]+", " ", fold(value).lower()).strip()


def _contains(value: str, cues: tuple[str, ...]) -> bool:
    padded = f" {_norm(value)} "
    return any(f" {_norm(cue)} " in padded for cue in cues)


def extract_question_topic(question: str) -> dict:
    normalized = _norm(question)
    matches = []
    for spec in TOPICS:
        for cue in spec.question_cues:
            cue = _norm(cue)
            for found in re.finditer(rf"(?<![a-z0-9]){re.escape(cue)}(?![a-z0-9])", normalized):
                position = found.start()
                before = normalized[max(0, position - 55):position]
                after = normalized[found.end():found.end() + 45]
                score = 10
                # These frames are generated question intent, not document-title prose.
                if re.search(r"(?:^| )ve $", before):
                    score += 90
                if re.search(r"(?:van de|lien quan den|thong tin nao ve|noi dung nao ve) $", before):
                    score += 130
                if re.search(r"(?:thong tin|noi dung)[a-z ]{0,30} ve $", before):
                    score += 115
                if re.search(r"(?:chi tieu|du lieu) [a-z0-9%+/ -]{0,45}$", before):
                    score += 105
                if re.search(r"^(?: cua [a-z0-9 ]+ )?(?:duoc|la bao nhieu|nhu the nao)", after):
                    score += 75
                if position < 12 and normalized.startswith("ve "):
                    score += 150
                # A phrase embedded in a named report/bulletin is weaker than an
                # explicit target frame elsewhere in the same question.
                if re.search(r"(?:bao cao|ban tin|tai lieu|giam sat|du bao)[a-z0-9 /-]{0,45}$", before):
                    score -= 30
                matches.append((score, position, len(cue), spec, cue))
    if not matches:
        return {"primary_topic": "UNKNOWN", "topic_cue": None, "confidence": 0.0,
                "entity": None, "metric_or_concept": None}
    score, position, _, spec, cue = max(matches, key=lambda item: (item[0], item[1], item[2]))
    return {
        "primary_topic": spec.name,
        "topic_cue": cue,
        "topic_position": position,
        "topic_selection_score": score,
        "confidence": 0.98 if score >= 80 else 0.8,
        "entity": _extract_entity(question),
        "metric_or_concept": cue,
    }


def _extract_entity(question: str) -> str | None:
    """Extract only high-confidence entity frames; absence is not a failure."""
    value = unicase = question.strip()
    patterns = (
        r"\bcủa\s+([^?,]+?)\s+(?:là bao nhiêu|được ghi nhận)",
        r"\bđối với\s+([^?,]+?)\s+và\s+",
        r"\btrạng thái của\s+([^?,]+?)\s+và\s+",
    )
    for pattern in patterns:
        match = re.search(pattern, unicase, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def extract_requested_relation(question: str) -> str:
    value = fold(question)
    if "bao nhieu" in value or "lan luot la" in value:
        return "QUANTITATIVE_VALUE"
    if any(cue in value for cue in ("nguyen nhan", "vi sao", "giai thich")):
        return "EXPLANATION"
    if any(cue in value for cue in ("khuyen nghi", "de nghi", "can lam gi")):
        return "RECOMMENDATION"
    if any(cue in value for cue in ("bien phap", "hanh dong", "thuc hien gi")):
        return "ACTION"
    if "du bao" in value:
        return "FORECAST_OR_REPORTED_STATE"
    return "REPORTED_INFORMATION"


def validate_topic_alignment(question: str, answer: str, evidence_texts: list[str]) -> dict:
    topic = extract_question_topic(question)
    requested = extract_requested_relation(question)
    errors = []
    answer_support = False
    evidence_support = False
    if topic["primary_topic"] == "UNKNOWN":
        errors.append("QUESTION_TOPIC_UNRESOLVED")
    else:
        spec = next(item for item in TOPICS if item.name == topic["primary_topic"])
        evidence_support = any(_contains(text, spec.support_cues) for text in evidence_texts)
        answer_support = _contains(answer, spec.support_cues)
        # Compact table answers often contain only value+unit.  In that case the
        # semantic metric is carried by the mapped source cell, not repeated in
        # the surface answer.
        if requested == "QUANTITATIVE_VALUE" and any(ch.isdigit() for ch in answer) and evidence_support:
            answer_support = True
        if not answer_support:
            errors.append("QUESTION_ANSWER_TOPIC_MISMATCH")
        if not evidence_support:
            errors.append("QUESTION_EVIDENCE_TOPIC_MISMATCH")
    if requested == "QUANTITATIVE_VALUE" and not any(ch.isdigit() for ch in answer):
        errors.append("QUANTITATIVE_ANSWER_MISSING_VALUE")
    return {
        **topic, "requested_relation": requested,
        "answer_topic_support": answer_support, "evidence_topic_support": evidence_support,
        "status": "PASS" if not errors else ("UNCERTAIN" if errors == ["QUESTION_TOPIC_UNRESOLVED"] else "FAIL"),
        "errors": errors, "validation_basis": "question topic independently matched against answer and source evidence",
    }
