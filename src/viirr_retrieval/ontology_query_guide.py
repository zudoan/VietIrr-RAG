"""Lightweight ontology-guided query understanding for VietIRR-RAG.

The guide is deliberately deterministic: it expands aliases and describes the
expected physical dimension, but never supplies an answer value.  All values
must still come from indexed source evidence.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable


def normalize_vietnamese(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("đ", "d").replace("Đ", "D").lower()
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class ParameterSpec:
    canonical: str
    aliases: tuple[str, ...]
    dimension: str
    units: tuple[str, ...]


@dataclass
class QueryIntent:
    entity: str | None = None
    parameter: str | None = None
    aliases: list[str] = field(default_factory=list)
    expected_dimension: str | None = None
    expected_units: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    document_identity: str | None = None
    temporal_scope: str | None = None
    confidence: float = 0.0
    numeric_or_table: bool = False

    def expansion_terms(self) -> list[str]:
        terms: list[str] = []
        if self.entity:
            terms.append(self.entity)
        if self.parameter:
            terms.append(self.parameter)
        terms.extend(self.aliases)
        terms.extend(self.expected_units)
        terms.extend(self.conditions)
        if self.document_identity:
            terms.append(self.document_identity)
        if self.temporal_scope:
            terms.append(self.temporal_scope)
        return list(dict.fromkeys(t for t in terms if t))


PARAMETER_SPECS: tuple[ParameterSpec, ...] = (
    ParameterSpec("mực nước dâng bình thường", ("mndbt", "cao trình dâng bình thường"), "LENGTH", ("m",)),
    ParameterSpec("mực nước chết", ("mnc", "cao trình chết"), "LENGTH", ("m",)),
    ParameterSpec("mực nước lũ thiết kế", ("mnltk", "mnlt", "mực nước thiết kế"), "LENGTH", ("m",)),
    ParameterSpec("mực nước lũ kiểm tra", ("mnlkt", "mnkt"), "LENGTH", ("m",)),
    ParameterSpec("mực nước", ("cao trình", "water level", "mực nước lớn nhất", "mực nước hiện tại"), "LENGTH", ("m", "cm")),
    ParameterSpec("dung tích hữu ích", ("whi", "dung tích hiệu dụng"), "VOLUME", ("triệu m3", "m3")),
    ParameterSpec("dung tích chết", ("wc",), "VOLUME", ("triệu m3", "m3")),
    ParameterSpec("dung tích phòng lũ", ("wpl", "dung tích cắt lũ"), "VOLUME", ("triệu m3", "m3")),
    ParameterSpec("dung tích", ("dung tích hiện tại", "dung tích toàn bộ", "wtb"), "VOLUME", ("triệu m3", "m3", "%")),
    ParameterSpec("lưu lượng xả", ("q xả", "lưu lượng qua tràn", "lưu lượng tràn"), "FLOW_RATE", ("m3/s",)),
    ParameterSpec("lưu lượng đến", ("q đến", "lưu lượng về hồ"), "FLOW_RATE", ("m3/s",)),
    ParameterSpec("lượng mưa", ("lượng mưa lũy tích", "mưa tuần", "rainfall"), "LENGTH", ("mm",)),
    ParameterSpec("diện tích đáp ứng", ("diện tích bảo đảm tưới", "diện tích"), "AREA", ("ha", "km2")),
    ParameterSpec("BOD5", ("bod 5", "nhu cầu oxy sinh hóa"), "CONCENTRATION", ("mg/L",)),
    ParameterSpec("COD", ("nhu cầu oxy hóa học",), "CONCENTRATION", ("mg/L",)),
    ParameterSpec("độ mặn", ("xâm nhập mặn", "salinity"), "CONCENTRATION", ("‰", "g/L", "mg/L")),
)


# Aliases are taken from the existing VietIRR vocabulary and corpus entities.
# They are query cues only, never trusted factual assertions.
ENTITY_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Hòa Bình", ("ho hoa binh",)), ("Sơn La", ("ho son la",)),
    ("Dầu Tiếng", ("ho dau tieng",)), ("Trị An", ("ho tri an",)),
    ("Thác Mơ", ("ho thac mo",)), ("Cần Đơn", ("ho can don",)),
    ("Tả Trạch", ("ho ta trach",)), ("Bình Điền", ("ho binh dien",)),
    ("Hương Điền", ("ho huong dien",)), ("Yên Lập", ("ho yen lap",)),
    ("Cửa Đạt", ("ho cua dat",)), ("Bản Vẽ", ("ho ban ve",)),
    ("Cái Lớn", ("cong cai lon",)), ("Cái Bé", ("cong cai be",)),
    ("Mê Công", ("mekong", "song me cong")),
)


class OntologyQueryGuide:
    """Extract soft retrieval constraints from a Vietnamese technical query."""

    _DOC_RE = re.compile(
        r"\b(?:quyết\s*định|qđ|thông\s*tư|nghị\s*định)?\s*"
        r"(\d{2,5}(?:\s*/\s*[a-zđ0-9-]+)?)\b",
        re.IGNORECASE,
    )
    _DATE_RE = re.compile(
        r"(?:ngày\s*)?\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?"
        r"|(?:năm|tháng|tuần|vụ)\s+[^,.;?]{1,40}",
        re.IGNORECASE,
    )

    def __init__(self, extra_entities: Iterable[str] | None = None) -> None:
        entities = [(canonical, aliases) for canonical, aliases in ENTITY_ALIASES]
        for value in extra_entities or ():
            value = str(value).strip()
            if value:
                entities.append((value, ()))
        # Prefer the longest entity to avoid matching a basin inside a structure.
        self.entities = sorted(entities, key=lambda item: len(item[0]), reverse=True)

    def understand(self, question: str) -> QueryIntent:
        q = str(question or "").strip()
        nq = normalize_vietnamese(q)
        intent = QueryIntent()

        for spec in PARAMETER_SPECS:
            cues = (spec.canonical, *spec.aliases)
            if any(normalize_vietnamese(cue) in nq for cue in cues):
                intent.parameter = spec.canonical
                intent.aliases = list(spec.aliases)
                intent.expected_dimension = spec.dimension
                intent.expected_units = list(spec.units)
                break

        for canonical, aliases in self.entities:
            cues = (canonical, *aliases)
            if any(normalize_vietnamese(cue) in nq for cue in cues):
                intent.entity = canonical
                break

        doc_match = self._DOC_RE.search(q)
        if doc_match:
            intent.document_identity = re.sub(r"\s+", "", doc_match.group(1))

        date_match = self._DATE_RE.search(q)
        if date_match:
            intent.temporal_scope = date_match.group(0).strip()

        conditions = []
        for condition in ("mùa lũ", "mùa kiệt", "mùa cạn", "lũ chính vụ", "dự báo tuần", "hiện tại", "thiết kế"):
            if normalize_vietnamese(condition) in nq:
                conditions.append(condition)
        intent.conditions = conditions

        intent.numeric_or_table = bool(
            intent.parameter
            or re.search(r"\b(bao nhieu|lan luot|chi tieu|gia tri|so lieu)\b", nq)
        )
        resolved = sum(bool(x) for x in (intent.entity, intent.parameter, intent.document_identity, intent.temporal_scope))
        intent.confidence = min(1.0, 0.2 + 0.2 * resolved + (0.2 if intent.numeric_or_table else 0.0))
        return intent

    def expand_query(self, question: str, intent: QueryIntent | None = None) -> str:
        intent = intent or self.understand(question)
        additions = []
        nq = normalize_vietnamese(question)
        for term in intent.expansion_terms():
            if normalize_vietnamese(term) not in nq:
                additions.append(term)
        # Keep expansion compact so aliases do not swamp the original wording.
        return " ".join([question.strip(), *additions[:8]]).strip()

    def build_missing_slot_query(self, question: str, missing_slots: Iterable[str]) -> str:
        intent = self.understand(question)
        slots = {normalize_vietnamese(slot) for slot in missing_slots}
        terms = [question.strip()]
        if intent.entity:
            terms.append(intent.entity)
        if intent.parameter:
            terms.extend([intent.parameter, *intent.aliases[:3]])
        if any("unit" in slot for slot in slots):
            terms.extend(intent.expected_units)
        if any("condition" in slot or "temporal" in slot for slot in slots):
            terms.extend(intent.conditions)
            if intent.temporal_scope:
                terms.append(intent.temporal_scope)
        if any("binding" in slot or "value" in slot or "parameter" in slot for slot in slots):
            terms.extend(("bảng thông số", "giá trị", "đơn vị"))
        if intent.document_identity:
            terms.append(intent.document_identity)
        return " ".join(dict.fromkeys(t for t in terms if t))

