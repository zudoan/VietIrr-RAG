"""Evidence-constrained comparison engine for Stage 2.4.

Implements modular verification checks:
- 6.1 Entity identity (full canonical names, aliases, multi-word jurisdictions).
- 6.2 Technical parameter identity (MNDBT, MNC, MNLTK, MNLKT, Discharge, Storage, etc.).
- 6.3 Numeric value and unit compatibility / conversion (strict tolerance, safe conversion).
- 6.4 Technical conditions (flood frequency, seasonal conditions, operating thresholds).
- 6.5 Legal and governance scope (actor, action, polarity AFFIRMED vs NEGATED).
- 6.6 Provenance identity (doc_id, page_number, evidence_id, multi-region synthesis).
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

from viirr_ontology.domain.classes import HydraulicStructure, TechnicalParameter
from viirr_ontology.domain.ontology_loader import HydraulicOntology
from viirr_ontology.domain.unit_registry import (
    UnitDimension,
    check_unit_compatibility,
    get_unit_dimension,
    normalize_unit_string,
)
from viirr_ontology.schema.claim import ClaimCondition, ClaimPolarity, TechnicalClaim
from viirr_ontology.schema.evidence import EvidenceItem, EvidenceRelation, EvidenceSet
from viirr_ontology.verifier.models import ReasonCode


def strip_accents_lower(s: str) -> str:
    """Strip accents and lower-case for robust phonetic comparison, handling Vietnamese 'đ'/'Đ' and font artifacts."""
    if not s:
        return ""
    # Map Vietnamese 'đ' / 'Đ' to 'd' before unicode decomposition
    s = s.replace("đ", "d").replace("Đ", "d")
    s = s.replace("ç", "o").replace("Ç", "o")  # OCR font artifacts common in VN legal water decrees (e.g. luçng -> luong)
    norm = unicodedata.normalize("NFD", s.lower())
    without_accents = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", without_accents).strip()


# Canonical Parameter Dictionaries for Hydraulic Engineering
CANONICAL_PARAMETERS: dict[str, dict[str, Any]] = {
    "MNDBT": {
        "canonical_name": "Mực nước dâng bình thường",
        "aliases": [
            "mndbt",
            "mực nước dâng bình thường",
            "muc nuoc dang binh thuong",
            "mực nước dâng bt",
            "normal pool level",
            "normal water level",
        ],
        "dimension": UnitDimension.LENGTH,
        "default_unit": "m",
    },
    "MNC": {
        "canonical_name": "Mực nước chết",
        "aliases": [
            "mnc",
            "mực nước chết",
            "muc nuoc chet",
            "dead water level",
            "dead pool level",
        ],
        "dimension": UnitDimension.LENGTH,
        "default_unit": "m",
    },
    "MNLTK": {
        "canonical_name": "Mực nước lũ thiết kế",
        "aliases": [
            "mnltk",
            "mực nước lũ thiết kế",
            "muc nuoc lu thiet ke",
            "design flood level",
        ],
        "dimension": UnitDimension.LENGTH,
        "default_unit": "m",
    },
    "MNLKT": {
        "canonical_name": "Mực nước lũ kiểm tra",
        "aliases": [
            "mnlkt",
            "mực nước lũ kiểm tra",
            "muc nuoc lu kiem tra",
            "check flood level",
        ],
        "dimension": UnitDimension.LENGTH,
        "default_unit": "m",
    },
    "MNTL": {
        "canonical_name": "Mực nước trước lũ",
        "aliases": [
            "mntl",
            "mực nước trước lũ",
            "muc nuoc truoc lu",
            "mực nước cao nhất trước lũ",
        ],
        "dimension": UnitDimension.LENGTH,
        "default_unit": "m",
    },
    "MNDL": {
        "canonical_name": "Mực nước đón lũ",
        "aliases": [
            "mndl",
            "mực nước đón lũ",
            "muc nuoc don lu",
        ],
        "dimension": UnitDimension.LENGTH,
        "default_unit": "m",
    },
    "MUC_NUOC": {
        "canonical_name": "Mực nước",
        "aliases": [
            "mực nước",
            "muc nuoc",
            "myc nuoc",
            "mąc nuoc",
            "cao trình",
            "cao trinh",
            "cao trình mực nước",
            "cao trinh muc nuoc",
            "water level",
        ],
        "dimension": UnitDimension.LENGTH,
        "default_unit": "m",
    },
    "Q_XA_MAX": {
        "canonical_name": "Lưu lượng xả lớn nhất",
        "aliases": [
            "lưu lượng xả lớn nhất",
            "luu luong xa lon nhat",
            "q xả max",
            "qxamax",
            "q_xả_max",
            "lưu lượng xả thiết kế",
        ],
        "dimension": UnitDimension.FLOW_RATE,
        "default_unit": "m3/s",
    },
    "Q_DEN": {
        "canonical_name": "Lưu lượng đến hồ",
        "aliases": [
            "lưu lượng đến",
            "luu luong den",
            "lưu lượng về hồ",
            "q đến",
            "q_đến",
            "qden",
            "inflow",
        ],
        "dimension": UnitDimension.FLOW_RATE,
        "default_unit": "m3/s",
    },
    "DUNG_TICH_TOAN_BO": {
        "canonical_name": "Dung tích toàn bộ",
        "aliases": [
            "dung tích toàn bộ",
            "dung tich toan bo",
            "gross storage",
            "total capacity",
            "w_tb",
            "wtb",
        ],
        "dimension": UnitDimension.VOLUME,
        "default_unit": "million_m3",
    },
    "DUNG_TICH_HUU_ICH": {
        "canonical_name": "Dung tích hữu ích",
        "aliases": [
            "dung tích hữu ích",
            "dung tich huu ich",
            "active storage",
            "useful capacity",
            "w_hi",
            "whi",
        ],
        "dimension": UnitDimension.VOLUME,
        "default_unit": "million_m3",
    },
    "DUNG_TICH_CHET": {
        "canonical_name": "Dung tích chết",
        "aliases": [
            "dung tích chết",
            "dung tich chet",
            "dead storage",
            "w_c",
            "wc",
        ],
        "dimension": UnitDimension.VOLUME,
        "default_unit": "million_m3",
    },
    "DUNG_TICH_PHONG_LU": {
        "canonical_name": "Dung tích phòng lũ",
        "aliases": [
            "dung tích phòng lũ",
            "dung tich phong lu",
            "flood control storage",
            "w_fl",
        ],
        "dimension": UnitDimension.VOLUME,
        "default_unit": "million_m3",
    },
    "Q_XA_MIN": {
        "canonical_name": "Lưu lượng xả nhỏ nhất",
        "aliases": [
            "lưu lượng xả nhỏ nhất",
            "luu luong xa nho nhat",
            "q xả min",
            "q_xả_min",
            "lưu lượng không nhỏ hơn",
            "luu luong khong nho hon",
            "không nhỏ hơn",
            "khong nho hon",
            "xả nước liên tục ngay sau đập với lưu lượng không nhỏ hơn",
            "lưu lượng xả hạ du tối thiểu",
            "lưu lượng duy trì dòng chảy tối thiểu",
        ],
        "dimension": UnitDimension.FLOW_RATE,
        "default_unit": "m3/s",
    },
    "Q_XA": {
        "canonical_name": "Lưu lượng xả",
        "aliases": [
            "lưu lượng xả",
            "luu luong xa",
            "lưu lượng xả xuống hạ du",
            "xả xuống hạ du lưu lượng",
            "xả xuống hạ du",
        ],
        "dimension": UnitDimension.FLOW_RATE,
        "default_unit": "m3/s",
    },
}

# Known Reservoir / Structure Aliases
KNOWN_STRUCTURE_ALIASES: dict[str, list[str]] = {
    "HO_HOA_BINH": ["hồ hòa bình", "hồ thuỷ điện hòa bình", "hồ thủy điện hòa bình", "hòa bình", "hoa binh", "thủy điện hòa bình"],
    "HO_SON_LA": ["hồ sơn la", "hồ thuỷ điện sơn la", "hồ thủy điện sơn la", "sơn la", "son la", "thủy điện sơn la"],
    "HO_LAI_CHAU": ["hồ lai châu", "hồ thuỷ điện lai châu", "lai châu", "lai chau", "thủy điện lai châu"],
    "HO_BAN_CHAT": ["hồ bản chát", "bản chát", "ban chat", "thủy điện bản chát"],
    "HO_HUOI_QUANG": ["hồ huội quảng", "huội quảng", "huoi quang", "thủy điện huội quảng", "hồ hui quång", "hui quång", "hui quang"],
    "HO_THAC_BA": ["hồ thác bà", "thác bà", "thac ba", "thủy điện thác bà"],
    "HO_TUYEN_QUANG": ["hồ tuyên quang", "tuyên quang", "tuyen quang", "thủy điện tuyên quang"],
    "HO_TRI_AN": ["hồ trị an", "trị an", "tri an", "thủy điện trị an"],
    "HO_DAU_TIENG": ["hồ dầu tiếng", "dầu tiếng", "dau tieng"],
    "HO_TA_TRACH": ["hồ tả trạch", "tả trạch", "ta trach", "thủy điện tả trạch"],
    "HO_BINH_DIEN": ["hồ bình điền", "bình điền", "binh dien", "thủy điện bình điền"],
    "HO_HUONG_DIEN": ["hồ hương điền", "hương điền", "huong dien", "thủy điện hương điền"],
    "HO_A_LUOI": ["hồ a lưới", "a lưới", "a luoi", "thủy điện a lưới"],
    "HO_A_VUONG": ["hồ a vương", "a vương", "a vuong", "thủy điện a vương"],
    "HO_SONG_BUNG_4": ["hồ sông bung 4", "sông bung 4", "song bung 4", "thủy điện sông bung 4"],
    "HO_SONG_TRANH_2": ["hồ sông tranh 2", "sông tranh 2", "song tranh 2", "thủy điện sông tranh 2"],
    "HO_DAK_MI_4": ["hồ đak mi 4", "đak mi 4", "dak mi 4", "thủy điện đak mi 4"],
    "HO_SONG_BA_HA": ["hồ sông ba hạ", "sông ba hạ", "song ba ha", "thủy điện sông ba hạ"],
    "HO_SONG_HINH": ["hồ sông hinh", "sông hinh", "song hinh", "thủy điện sông hinh"],
    "HO_KRONG_HNANG": ["hồ krông hnăng", "krông hnăng", "krong hnang", "thủy điện krông hnăng"],
    "HO_AYUN_HA": ["hồ ayun hạ", "ayun hạ", "ayun ha"],
    "HO_THUONG_A_LIN": ["hồ thượng a lin", "thượng a lin", "thuong a lin"],
    "CONG_CAI_LON": ["cống cái lớn", "cái lớn", "cai lon"],
    "CONG_CAI_BE": ["cống cái bé", "cái bé", "cai be"],
}

# Static structural parameters invariant to seasonal conditions or flood frequencies
STATIC_DESIGN_PARAMETERS: set[str] = {
    "MNDBT", "MNC", "V_TOAN_BO", "V_CHET", "V_HUU_ICH",
    "DIEN_TICH_LUU_VUC", "CHIEU_CAO_DAP", "CHIEU_DAI_DAP", "CAO_TRINH_DINH_DAP",
    "muc_nuoc_dang_binh_thuong", "muc_nuoc_chet", "dung_tich_toan_bo", "dung_tich_chet",
    "dung_tich_huu_ich", "dien_tich_luu_vuc", "chieu_cao_dap", "chieu_dai_dap"
}

# Unit Conversion Factors to Canonical Base Unit
UNIT_CONVERSIONS: dict[tuple[str, str], float] = {
    # Length: target "m"
    ("m", "m"): 1.0,
    ("mét", "m"): 1.0,
    ("met", "m"): 1.0,
    ("cm", "m"): 0.01,
    ("mm", "m"): 0.001,
    # Flow Rate: target "m3/s"
    ("m3/s", "m3/s"): 1.0,
    ("m³/s", "m3/s"): 1.0,
    ("m3/giây", "m3/s"): 1.0,
    ("l/s", "m3/s"): 0.001,
    ("lit/s", "m3/s"): 0.001,
    # Volume: target "million_m3" (10^6 m3)
    ("triệu m3", "million_m3"): 1.0,
    ("trieu m3", "million_m3"): 1.0,
    ("million_m3", "million_m3"): 1.0,
    ("10^6 m3", "million_m3"): 1.0,
    ("10^6m3", "million_m3"): 1.0,
    ("$10{m3}$", "million_m3"): 1.0,
    ("10{m3}", "million_m3"): 1.0,
    ("10{m3", "million_m3"): 1.0,
    ("$10{m3$", "million_m3"): 1.0,
    ("$10^m3$", "million_m3"): 1.0,
    ("10^m3", "million_m3"): 1.0,
    ("$10^{6}m3$", "million_m3"): 1.0,
    ("m3", "million_m3"): 1e-6,
    ("m³", "million_m3"): 1e-6,
    ("tỷ m3", "million_m3"): 1000.0,
    ("ty m3", "million_m3"): 1000.0,
    ("billion_m3", "million_m3"): 1000.0,
    ("10^9 m3", "million_m3"): 1000.0,
}


@dataclass
class EvidenceMatchAssessment:
    """Detailed result of comparing a TechnicalClaim against evidence."""

    matched: bool = False
    is_contradiction: bool = False
    is_insufficient: bool = False

    entity_matched: bool = False
    parameter_matched: bool = False
    value_matched: bool = False
    unit_matched: bool = False
    conditions_matched: bool = False
    legal_matched: bool = False
    provenance_valid: bool = False

    supporting_evidence_ids: list[str] = field(default_factory=list)
    conflicting_evidence_ids: list[str] = field(default_factory=list)
    missing_slots: list[str] = field(default_factory=list)
    reason_codes: list[ReasonCode] = field(default_factory=list)
    explanations: list[str] = field(default_factory=list)
    evidence_trace: list[dict[str, Any]] = field(default_factory=list)


class EvidenceMatcher:
    """Compares structured TechnicalClaim objects against EvidenceSet and ontology."""

    def __init__(self, ontology: Optional[HydraulicOntology] = None) -> None:
        self.ontology = ontology

    def _parameter_occurrences(self, evidence_text: str) -> list[tuple[int, int, str]]:
        """Locate canonical parameter mentions for value-to-parameter binding."""
        norm_ev = strip_accents_lower(evidence_text)
        occurrences: list[tuple[int, int, str]] = []
        seen: set[tuple[int, int, str]] = set()
        for key, meta in CANONICAL_PARAMETERS.items():
            aliases = sorted(
                {strip_accents_lower(alias) for alias in meta["aliases"] if alias},
                key=len,
                reverse=True,
            )
            for alias in aliases:
                for match in re.finditer(re.escape(alias), norm_ev):
                    marker = (match.start(), match.end(), key)
                    if marker not in seen:
                        seen.add(marker)
                        occurrences.append(marker)
        return sorted(occurrences, key=lambda row: (row[0], -(row[1] - row[0])))

    def extract_parameter_numeric_bindings(
        self, claim_parameter: str, evidence_text: str, claim_subject: Optional[str] = None
    ) -> list[tuple[str, str]]:
        """Extract numbers locally bound to the claimed parameter, scoped by claim_subject when available."""
        claim_key, _, claim_rc = self.identify_parameter(claim_parameter)
        if claim_rc == ReasonCode.PARAMETER_AMBIGUOUS or not claim_key:
            return []

        norm_ev = strip_accents_lower(evidence_text)
        occurrences = self._parameter_occurrences(evidence_text)
        claim_occurrences = [occ for occ in occurrences if occ[2] == claim_key]
        if claim_key not in CANONICAL_PARAMETERS:
            phrase = strip_accents_lower(claim_parameter)
            claim_occurrences = [
                (match.start(), match.end(), str(claim_key))
                for match in re.finditer(re.escape(phrase), norm_ev)
            ]

        # Entity-aware scoping if claim_subject is provided
        norm_subj = strip_accents_lower(claim_subject) if claim_subject else ""
        subject_aliases: list[str] = [norm_subj] if norm_subj else []
        other_structure_aliases: list[str] = []
        if norm_subj:
            for skey, saliases in KNOWN_STRUCTURE_ALIASES.items():
                if any(strip_accents_lower(a) in norm_subj or norm_subj in strip_accents_lower(a) for a in saliases):
                    subject_aliases.extend([strip_accents_lower(a) for a in saliases])
                    break
            for skey, saliases in KNOWN_STRUCTURE_ALIASES.items():
                if not any(strip_accents_lower(a) in subject_aliases for a in saliases):
                    for a in saliases:
                        na = strip_accents_lower(a)
                        if len(na) >= 4:
                            other_structure_aliases.append(na)

        subject_specific_bindings: list[tuple[str, str]] = []
        generic_bindings: list[tuple[str, str]] = []

        for start, end, _ in claim_occurrences:
            is_subject_bound = False
            # Check nearest preceding entity context if multiple structures exist
            if norm_subj and other_structure_aliases:
                prefix = norm_ev[:start]
                best_sa_pos = -1
                for sa in subject_aliases:
                    pos = prefix.rfind(sa)
                    if pos > best_sa_pos:
                        best_sa_pos = pos + len(sa)

                best_oa_pos = -1
                for oa in other_structure_aliases:
                    pos = prefix.rfind(oa)
                    if pos > best_oa_pos:
                        best_oa_pos = pos + len(oa)

                # Check if multiple column headers exist before this row (table layout)
                all_structs = list(set(subject_aliases + other_structure_aliases))
                col_headers_present = [st for st in all_structs if norm_ev[:start].find(st) != -1]
                is_multi_column_table = len(col_headers_present) >= 2

                # If another structure is strictly closer to this parameter in narrative text, skip it
                if not is_multi_column_table and best_oa_pos > best_sa_pos and (start - best_oa_pos) < 300:
                    continue

                if is_multi_column_table or (best_sa_pos > best_oa_pos and (start - best_sa_pos) < 300):
                    is_subject_bound = True

            later_parameter_starts = [pos for pos, _, _ in occurrences if pos >= end]
            segment_end = min(later_parameter_starts) if later_parameter_starts else len(norm_ev)
            delimiter = re.search(r"[;\n]|\.(?!\d)", norm_ev[end:segment_end])
            if delimiter:
                segment_end = end + delimiter.start()
            segment = norm_ev[end:segment_end]
            unit_pattern = r"(\$10\{?m3\}?\$?|\$10\^?m3\$|\$10\^?\{?6\}?\s*m(?:3|³)\$?|10\{?m3\}?|10\^?\{?6\}?\s*m(?:3|³)|trieu\s*m(?:3|³)|million_m3|ty\s*m(?:3|³)|m(?:3|³)/s|l/s|cm|mm|m|%)"
            unit_m = re.search(unit_pattern, segment)
            row_unit = unit_m.group(1) if unit_m else ""
            unit_spans = [unit_m.span()] if unit_m else []

            raw_candidates = []
            for candidate in re.finditer(r"(?<![\w])[-+]?\d+(?:[\.,]\d+)?", segment):
                c_start, c_end = candidate.span()
                if any(u_s <= c_start and c_end <= u_e for u_s, u_e in unit_spans):
                    continue
                prefix = segment[:candidate.start()]
                suffix = segment[candidate.end():]
                if re.search(r"p\s*=\s*$", prefix) or re.match(r"\s*%", suffix):
                    continue
                # Local unit immediately following number if any
                loc_unit_m = re.match(r"\s*" + unit_pattern, suffix)
                loc_unit = loc_unit_m.group(1) if loc_unit_m else row_unit
                raw_candidates.append((candidate.group(0), loc_unit))

            if not raw_candidates:
                continue

            # If multiple column structures exist before this row, match column order
            bound_col_val = None
            if norm_subj and other_structure_aliases and len(raw_candidates) > 1:
                all_structs = list(set(subject_aliases + other_structure_aliases))
                col_positions = []
                for st in all_structs:
                    p = norm_ev[:start].find(st)
                    if p != -1:
                        col_positions.append((p, st))
                col_positions.sort()
                for c_idx, (_, st) in enumerate(col_positions):
                    if any(sa in st or st in sa for sa in subject_aliases):
                        if c_idx < len(raw_candidates):
                            bound_col_val = raw_candidates[c_idx]
                        break

            if bound_col_val:
                subject_specific_bindings.append(bound_col_val)
            elif is_subject_bound:
                subject_specific_bindings.extend(raw_candidates)
            else:
                generic_bindings.extend(raw_candidates)

        # Prioritize subject-specific bindings if available
        if subject_specific_bindings:
            return subject_specific_bindings
        if generic_bindings:
            return generic_bindings

        # Fallback to un-scoped bindings if entity scoping yielded empty bindings
        if norm_subj and other_structure_aliases:
            return self.extract_parameter_numeric_bindings(claim_parameter, evidence_text, claim_subject=None)

        return []

    # -------------------------------------------------------------------------
    # 6.1 Entity Identity Matching
    # -------------------------------------------------------------------------
    def match_entity(
        self, claim_subject: str, evidence_text: str, claim_val: Optional[str] = None
    ) -> tuple[bool, Optional[str], Optional[ReasonCode]]:
        """Match subject/structure identity preserving multi-word and administrative bounds."""
        if not claim_subject or not claim_subject.strip():
            return False, None, ReasonCode.ENTITY_UNKNOWN

        norm_claim = strip_accents_lower(claim_subject)
        norm_ev = strip_accents_lower(evidence_text)

        # 1. Exact or normalized string containment of claim subject in evidence
        if norm_claim in norm_ev:
            return True, claim_subject, ReasonCode.ENTITY_MATCHED

        # 2. Check structure alias dictionary
        claim_canonical_key = None
        for key, aliases in KNOWN_STRUCTURE_ALIASES.items():
            for alias in aliases:
                if strip_accents_lower(alias) == norm_claim or strip_accents_lower(alias) in norm_claim:
                    claim_canonical_key = key
                    break
            if claim_canonical_key:
                break

        if claim_canonical_key:
            # Check if any alias of the same canonical structure appears in evidence
            for alias in KNOWN_STRUCTURE_ALIASES[claim_canonical_key]:
                if strip_accents_lower(alias) in norm_ev:
                    return True, claim_canonical_key, ReasonCode.ENTITY_MATCHED

            # Check if an incompatible known structure appears in evidence
            # True contradiction ONLY if the claimed value is present in evidence attributed to that other structure
            claim_num = self.parse_numeric_value(claim_val) if claim_val else None
            val_present = False
            if claim_num is not None:
                for n in re.findall(r"(?<![\w])[-+]?\d+(?:[\.,]\d+)?", evidence_text):
                    parsed = self.parse_numeric_value(n)
                    if parsed is not None and math.isclose(parsed, claim_num, rel_tol=1e-4, abs_tol=1e-3):
                        val_present = True
                        break

            for other_key, aliases in KNOWN_STRUCTURE_ALIASES.items():
                if other_key != claim_canonical_key:
                    for alias in aliases:
                        if strip_accents_lower(alias) in norm_ev:
                            if val_present:
                                return False, other_key, ReasonCode.ENTITY_MISMATCH
                            # Otherwise, evidence merely mentions other entities without contradicting this claim
                            return False, None, ReasonCode.ENTITY_UNKNOWN

        # Check multi-word jurisdiction prefix: e.g. "tỉnh Đồng Nai" vs "tỉnh Đồng Tháp"
        if "tinh " in norm_claim or "thanh pho " in norm_claim:
            for j_prefix in ("tinh ", "thanh pho "):
                if j_prefix in norm_ev:
                    # An incompatible alternative jurisdiction is mentioned in evidence
                    return False, None, ReasonCode.ENTITY_MISMATCH
            return False, None, ReasonCode.ENTITY_UNKNOWN

        return False, None, ReasonCode.ENTITY_UNKNOWN

    # -------------------------------------------------------------------------
    # 6.2 Technical Parameter Identity Matching
    # -------------------------------------------------------------------------
    def identify_parameter(self, param_text: str) -> tuple[Optional[str], Optional[dict[str, Any]], Optional[ReasonCode]]:
        """Normalize parameter string to canonical parameter key and metadata.

        Enforces:
        - Rejection of ambiguous multi-parameter phrases (e.g., 'mực nước dâng bình thường và mực nước chết').
        - Exact parameter identity (MNDBT != MNC != MNLTK).
        """
        if not param_text or not param_text.strip():
            return None, None, ReasonCode.PARAMETER_AMBIGUOUS

        norm_param = strip_accents_lower(param_text)

        # Detect ambiguous combination of multiple parameters, filtering subsumed substring aliases
        matched_entries: list[tuple[str, str]] = []  # (key, matched_alias)
        for key, meta in CANONICAL_PARAMETERS.items():
            for alias in meta["aliases"]:
                norm_al = strip_accents_lower(alias)
                if norm_al in norm_param:
                    matched_entries.append((key, norm_al))

        if not matched_entries:
            return norm_param, None, ReasonCode.PARAMETER_MATCHED

        # Filter out aliases that are strict substrings of a longer matched alias from a different key
        surviving_keys: set[str] = set()
        for key, al in matched_entries:
            subsumed = any(al in longer_al and len(longer_al) > len(al) for k2, longer_al in matched_entries if k2 != key)
            if not subsumed:
                surviving_keys.add(key)

        if len(surviving_keys) > 1:
            return None, None, ReasonCode.PARAMETER_AMBIGUOUS

        if len(surviving_keys) == 1:
            key = next(iter(surviving_keys))
            return key, CANONICAL_PARAMETERS[key], ReasonCode.PARAMETER_MATCHED

        return norm_param, None, ReasonCode.PARAMETER_MATCHED

    def match_parameter(
        self, claim_param: str, evidence_text: str, claim_val: Optional[str] = None
    ) -> tuple[bool, Optional[str], Optional[ReasonCode]]:
        """Check if claim's parameter matches evidence text, distinguishing similar concepts."""
        claim_key, claim_meta, claim_rc = self.identify_parameter(claim_param)
        if claim_rc == ReasonCode.PARAMETER_AMBIGUOUS:
            return False, None, ReasonCode.PARAMETER_AMBIGUOUS

        norm_ev = strip_accents_lower(evidence_text)

        if claim_key in CANONICAL_PARAMETERS:
            # Check if claim parameter aliases are in evidence
            for alias in CANONICAL_PARAMETERS[claim_key]["aliases"]:
                if strip_accents_lower(alias) in norm_ev:
                    return True, claim_key, ReasonCode.PARAMETER_MATCHED

            # A different parameter is contradictory only when the claim value is
            # explicitly bound to that recognized parameter. Global number presence
            # is insufficient and is especially unsafe under OCR degradation.
            claim_num = self.parse_numeric_value(claim_val) if claim_val else None
            for other_key, meta in CANONICAL_PARAMETERS.items():
                if other_key != claim_key:
                    for alias in meta["aliases"]:
                        if strip_accents_lower(alias) in norm_ev:
                            if claim_num is not None:
                                other_bindings = self.extract_parameter_numeric_bindings(
                                    meta["canonical_name"], evidence_text
                                )
                                for bound_value, _ in other_bindings:
                                    parsed = self.parse_numeric_value(bound_value)
                                    if parsed is not None and math.isclose(
                                        parsed, claim_num, rel_tol=1e-4, abs_tol=1e-3
                                    ):
                                        return False, other_key, ReasonCode.PARAMETER_MISMATCH

        # Fallback to direct normalized match
        norm_claim = strip_accents_lower(claim_param)
        if norm_claim in norm_ev:
            return True, claim_param, ReasonCode.PARAMETER_MATCHED

        # Parameter is not found in evidence text, but no conflicting parameter is found either
        return False, None, ReasonCode.MISSING_REQUIRED_SLOT

    # -------------------------------------------------------------------------
    # 6.3 Numeric Value & Unit Compatibility / Conversion
    # -------------------------------------------------------------------------
    def parse_numeric_value(self, val_str: str) -> Optional[float]:
        """Parse numeric value handling Vietnamese and English decimal separators."""
        if val_str is None:
            return None
        cleaned = str(val_str).strip()
        if not cleaned:
            return None

        # Pattern: Vietnamese thousands dot and decimal comma: "1.500,5" or standard "117,0"
        if re.search(r"^\d{1,3}(\.\d{3})+(,\d+)?$", cleaned):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned and "." not in cleaned:
            # "117,0" -> "117.0"
            cleaned = cleaned.replace(",", ".")
        elif "," in cleaned and "." in cleaned:
            # "1,500.5" -> standard English
            cleaned = cleaned.replace(",", "")

        try:
            val = float(cleaned)
            if math.isfinite(val):
                return val
        except ValueError:
            pass
        return None

    def convert_value_to_canonical(self, value: float, unit: str, target_unit: str) -> Optional[float]:
        """Convert a numeric value safely to target unit."""
        norm_u = normalize_unit_string(unit)
        norm_tgt = normalize_unit_string(target_unit)

        if norm_u == norm_tgt:
            return value

        strip_u = strip_accents_lower(norm_u)
        strip_tgt = strip_accents_lower(norm_tgt)

        if strip_u == strip_tgt:
            return value

        factor = UNIT_CONVERSIONS.get((norm_u, norm_tgt))
        if factor is not None:
            return value * factor

        # Try reverse factor
        rev_factor = UNIT_CONVERSIONS.get((norm_tgt, norm_u))
        if rev_factor is not None and rev_factor != 0:
            return value / rev_factor

        # Try mapping both to canonical base unit
        for base in ("m", "m3/s", "million_m3"):
            f_u = UNIT_CONVERSIONS.get((norm_u, base))
            if f_u is None:
                for (src, dst), f in UNIT_CONVERSIONS.items():
                    if dst == base and strip_accents_lower(src) == strip_u:
                        f_u = f
                        break
            f_tgt = UNIT_CONVERSIONS.get((norm_tgt, base))
            if f_tgt is None:
                for (src, dst), f in UNIT_CONVERSIONS.items():
                    if dst == base and strip_accents_lower(src) == strip_tgt:
                        f_tgt = f
                        break
            if f_u is not None and f_tgt is not None and f_tgt != 0:
                return (value * f_u) / f_tgt

        return None

    def match_numeric_value_and_unit(
        self,
        claim_val: Optional[str],
        claim_unit: Optional[str],
        ev_val: Optional[str],
        ev_unit: Optional[str],
        param_name: str = "",
        tolerance: float = 1e-3,
    ) -> tuple[bool, Optional[ReasonCode], str]:
        """Compare numeric values and units safely with physical dimension verification."""
        if claim_val is None or ev_val is None:
            return False, ReasonCode.VALUE_CONTRADICTED, "Missing numeric value for comparison"

        num_claim = self.parse_numeric_value(claim_val)
        num_ev = self.parse_numeric_value(ev_val)

        if num_claim is None or num_ev is None:
            return False, ReasonCode.VALUE_CONTRADICTED, f"Could not parse numeric values: '{claim_val}' vs '{ev_val}'"

        # Check unit compatibility with parameter
        if claim_unit and param_name:
            compat, msg = check_unit_compatibility(param_name, claim_unit)
            if not compat:
                return False, ReasonCode.UNIT_INCOMPATIBLE, msg

        # Unit verification
        c_unit = normalize_unit_string(claim_unit or "")
        e_unit = normalize_unit_string(ev_unit or "")

        dim_claim = get_unit_dimension(c_unit) if c_unit else UnitDimension.UNKNOWN
        dim_ev = get_unit_dimension(e_unit) if e_unit else UnitDimension.UNKNOWN

        if dim_claim == UnitDimension.UNKNOWN and c_unit:
            dim_claim = get_unit_dimension(strip_accents_lower(c_unit))
        if dim_ev == UnitDimension.UNKNOWN and e_unit:
            dim_ev = get_unit_dimension(strip_accents_lower(e_unit))

        if dim_claim != UnitDimension.UNKNOWN and dim_ev != UnitDimension.UNKNOWN:
            if dim_claim != dim_ev:
                return (
                    False,
                    ReasonCode.UNIT_INCOMPATIBLE,
                    f"Physical dimension mismatch: claim unit '{claim_unit}' ({dim_claim.value}) "
                    f"vs evidence unit '{ev_unit}' ({dim_ev.value})",
                )

        # Convert to common unit if needed
        converted_claim = num_claim
        if c_unit and e_unit and strip_accents_lower(c_unit) != strip_accents_lower(e_unit):
            conv = self.convert_value_to_canonical(num_claim, c_unit, e_unit)
            if conv is not None:
                converted_claim = conv
            else:
                # Cannot safely convert
                return (
                    False,
                    ReasonCode.UNIT_INCOMPATIBLE,
                    f"Cannot safely convert units between '{claim_unit}' and '{ev_unit}'",
                )

        # Compare values
        diff = abs(converted_claim - num_ev)
        if diff <= tolerance or math.isclose(converted_claim, num_ev, rel_tol=1e-4, abs_tol=tolerance):
            rc = ReasonCode.VALUE_MATCHED
            if strip_accents_lower(c_unit) != strip_accents_lower(e_unit) and c_unit:
                rc = ReasonCode.UNIT_CONVERSION_APPLIED
            return True, rc, f"Value {num_claim} ({claim_unit}) matches evidence {num_ev} ({ev_unit})"

        return (
            False,
            ReasonCode.VALUE_CONTRADICTED,
            f"Value contradiction: claim asserted {num_claim} ({claim_unit}), "
            f"but evidence states {num_ev} ({ev_unit})",
        )

    # -------------------------------------------------------------------------
    # 6.4 Technical Conditions Matching
    # -------------------------------------------------------------------------
    def match_conditions(
        self,
        claim_conditions: list[ClaimCondition],
        evidence_text: str,
        claim_subject: Optional[str] = None,
        claim_parameter: Optional[str] = None,
    ) -> tuple[bool, Optional[ReasonCode], str]:
        """Check whether claimed technical conditions (frequency, season, thresholds) match evidence."""
        if not claim_conditions:
            return True, ReasonCode.CONDITION_MATCHED, "No specific conditions required"

        norm_ev = strip_accents_lower(evidence_text)
        supported_operators = {"EQ", "GE", "GT", "LE", "LT", "BETWEEN"}

        for item_cond in claim_conditions:
            if isinstance(item_cond, str):
                cond = ClaimCondition(operator="EQ", value=item_cond, raw_text=item_cond)
            elif isinstance(item_cond, dict):
                cond = ClaimCondition.from_dict(item_cond)
            else:
                cond = item_cond

            op = (cond.operator or "").strip().upper()
            if op not in supported_operators:
                return (
                    False,
                    ReasonCode.CONDITION_MISSING,
                    f"Unsupported or unrecognized condition operator '{cond.operator}'",
                )

            raw_c = strip_accents_lower(cond.raw_text or f"{cond.operator} {cond.value} {cond.unit}")

            # 1. Flood frequency conditions: e.g. "p=0.01%", "p = 0,1%"
            pct_match = re.search(r"p\s*=\s*([\d,\.]+)\s*%", raw_c)
            if not pct_match and cond.unit == "%":
                pct_match = re.search(r"([\d,\.]+)", str(cond.value))
            if pct_match:
                freq = pct_match.group(1).replace(",", ".")
                ev_pct = re.search(r"p\s*=\s*([\d,\.]+)\s*%", norm_ev)
                if ev_pct:
                    ev_freq = ev_pct.group(1).replace(",", ".")
                    if freq != ev_freq:
                        return (
                            False,
                            ReasonCode.CONDITION_CONTRADICTED,
                            f"Flood frequency conflict: claim condition p={freq}% vs evidence p={ev_freq}%",
                        )
                else:
                    return (
                        False,
                        ReasonCode.CONDITION_MISSING,
                        f"Evidence lacks required flood frequency condition p={freq}%",
                    )
                continue

            # 2. Seasonal conditions: e.g. "mùa lũ", "mùa cạn", "lũ chính vụ"
            seasonal_found = False
            for season in ["mua lu", "mua can", "lu chinh vu", "lu som", "lu muon"]:
                if season in raw_c:
                    seasonal_found = True
                    if season not in norm_ev:
                        conflicting_season = "mua can" if season == "mua lu" else ("mua lu" if season == "mua can" else None)
                        if conflicting_season and conflicting_season in norm_ev:
                            return (
                                False,
                                ReasonCode.CONDITION_CONTRADICTED,
                                f"Season condition conflict: claim is for '{season}' but evidence is for '{conflicting_season}'",
                            )
                        return (
                            False,
                            ReasonCode.CONDITION_MISSING,
                            f"Evidence lacks required seasonal condition '{season}'",
                        )
            if seasonal_found:
                continue

            # 3. BETWEEN operator: requires both lower and upper bounds
            if op == "BETWEEN":
                raw_val = cond.value or cond.raw_text or ""
                cond_nums = re.findall(r"(?<![\w])[-+]?\d+(?:[\.,]\d+)?", raw_val)
                if len(cond_nums) < 2:
                    return (
                        False,
                        ReasonCode.CONDITION_MISSING,
                        "BETWEEN condition requires both lower and upper threshold values",
                    )
                p_low = self.parse_numeric_value(cond_nums[0])
                p_high = self.parse_numeric_value(cond_nums[1])
                if p_low is None or p_high is None:
                    return (
                        False,
                        ReasonCode.CONDITION_MISSING,
                        "Cannot parse numeric range endpoints for BETWEEN condition",
                    )
                low_bound = min(p_low, p_high)
                high_bound = max(p_low, p_high)

                range_located = False
                ev_num_matches = [
                    (m.start(), m.end(), self.parse_numeric_value(m.group(0)))
                    for m in re.finditer(r"(?<![\w])[-+]?\d+(?:[\.,]\d+)?", evidence_text)
                ]
                matching_low = [n for n in ev_num_matches if n[2] is not None and math.isclose(n[2], low_bound, rel_tol=1e-4, abs_tol=1e-3)]
                matching_high = [n for n in ev_num_matches if n[2] is not None and math.isclose(n[2], high_bound, rel_tol=1e-4, abs_tol=1e-3)]

                if matching_low and matching_high:
                    for l_start, l_end, _ in matching_low:
                        for h_start, h_end, _ in matching_high:
                            if abs(h_start - l_end) <= 60 or abs(l_start - h_end) <= 60:
                                span_start = max(0, min(l_start, h_start) - 30)
                                span_end = min(len(evidence_text), max(l_end, h_end) + 30)
                                span_ctx = strip_accents_lower(evidence_text[span_start:span_end])
                                if any(rk in span_ctx for rk in ["den", "trong khoang", "-", "dao dong", "khoang tu", "tu"]):
                                    range_located = True
                                    break
                        if range_located:
                            break

                if not range_located:
                    return (
                        False,
                        ReasonCode.CONDITION_MISSING,
                        f"Evidence lacks required range condition BETWEEN {low_bound} and {high_bound} {cond.unit}",
                    )
                continue

            # 4. Structured threshold conditions (GE, GT, LE, LT, EQ)
            cond_num = self.parse_numeric_value(cond.value)
            if cond_num is None:
                return (
                    False,
                    ReasonCode.CONDITION_MISSING,
                    f"Cannot parse numeric threshold value '{cond.value}' for operator '{op}'",
                )

            threshold_located = False
            boundary_contradiction = False

            # Separate evidence into clauses/sentences to verify structure/subject binding
            ev_clauses = [c.strip() for c in re.split(r"[;\n\.]+", evidence_text) if c.strip()]

            # Determine intended parameter for this condition (if any)
            intended_param_key = None
            norm_c_raw = strip_accents_lower(cond.raw_text or "")
            for p_k, p_meta in CANONICAL_PARAMETERS.items():
                if any(strip_accents_lower(al) in norm_c_raw for al in p_meta["aliases"]):
                    intended_param_key = p_k
                    break
            # A condition may constrain an operating variable other than the
            # asserted parameter (for example MNDBT=117 m *when reservoir
            # level >=85 m*).  Bind it to a parameter only when the condition
            # itself names that parameter; falling back to claim_parameter
            # incorrectly rejects valid operating thresholds.

            for m in re.finditer(r"(?<![\w])[-+]?\d+(?:[\.,]\d+)?", evidence_text):
                num_parsed = self.parse_numeric_value(m.group(0))
                if num_parsed is None or not math.isclose(num_parsed, cond_num, rel_tol=1e-4, abs_tol=1e-3):
                    continue

                m_start, m_end = m.start(), m.end()
                start = max(0, m_start - 40)
                end = min(len(evidence_text), m_end + 40)
                ctx = strip_accents_lower(evidence_text[start:end])

                # Find enclosing clause for subject and parameter binding
                enclosing_clause = ""
                curr_pos = 0
                for cl in ev_clauses:
                    cl_start = evidence_text.find(cl, curr_pos)
                    if cl_start != -1:
                        cl_end = cl_start + len(cl)
                        curr_pos = cl_end
                        if cl_start <= m_start and m_end <= cl_end:
                            enclosing_clause = cl
                            break
                norm_enclosing = strip_accents_lower(enclosing_clause or evidence_text[start:end])

                # Subject Binding: threshold must not belong to a different reservoir/structure
                if claim_subject:
                    norm_subj = strip_accents_lower(claim_subject)
                    diff_struct_found = False
                    for s_key, s_aliases in KNOWN_STRUCTURE_ALIASES.items():
                        is_claim_struct = any(strip_accents_lower(alias) in norm_subj for alias in s_aliases)
                        if not is_claim_struct:
                            for alias in s_aliases:
                                norm_alias = strip_accents_lower(alias)
                                if norm_alias in norm_enclosing and norm_alias not in norm_subj:
                                    diff_struct_found = True
                                    break
                        if diff_struct_found:
                            break
                    if diff_struct_found:
                        continue

                # Physical unit and dimension check: validate unit attached to threshold
                if cond.unit:
                    norm_c_unit = normalize_unit_string(cond.unit)
                    c_dim = get_unit_dimension(norm_c_unit)
                    after_candidate = evidence_text[m_end:min(len(evidence_text), m_end + 25)]
                    u_match = re.search(
                        r"^\s*(trieu\s*m(?:3|³)|million_m3|ty\s*m(?:3|³)|m(?:3|³)/s|m3/giay|l/s|lit/s|cm|mm|m\b|%)",
                        after_candidate,
                        flags=re.IGNORECASE,
                    )
                    if u_match:
                        found_u = normalize_unit_string(u_match.group(1))
                        found_dim = get_unit_dimension(found_u)
                        if c_dim != UnitDimension.UNKNOWN and found_dim != UnitDimension.UNKNOWN and c_dim != found_dim:
                            # Incompatible dimensions (e.g. claim condition unit is m [LENGTH] vs evidence unit m3/s [FLOW_RATE])
                            continue

                # Parameter Binding: threshold must not belong to an incompatible hydraulic parameter
                if intended_param_key:
                    diff_param_found = False
                    for other_k, other_meta in CANONICAL_PARAMETERS.items():
                        if other_k != intended_param_key:
                            for al in other_meta["aliases"]:
                                norm_al = strip_accents_lower(al)
                                if norm_al in norm_enclosing:
                                    intended_in_enclosing = any(
                                        strip_accents_lower(al2) in norm_enclosing
                                        for al2 in CANONICAL_PARAMETERS[intended_param_key]["aliases"]
                                    )
                                    if not intended_in_enclosing:
                                        diff_param_found = True
                                        break
                                    # If both parameters are in enclosing clause, check proximity
                                    al_pos = norm_enclosing.rfind(norm_al, 0, m_start)
                                    int_pos = max([norm_enclosing.rfind(strip_accents_lower(al2), 0, m_start) for al2 in CANONICAL_PARAMETERS[intended_param_key]["aliases"]] + [-1])
                                    if al_pos > int_pos:
                                        diff_param_found = True
                                        break
                            if diff_param_found:
                                break
                    if diff_param_found:
                        continue

                # Incidental vs Applicability check:
                incidental_markers = ["lich su", "do duoc", "quan trac", "thuc te", "ghi nhan", "thong ke", "hien tai"]
                has_incidental = any(inc in ctx for inc in incidental_markers)

                # Required applicability/threshold cues:
                explicit_condition_cues = [
                    "nguong", "khi", "neu", "truong hop", "dieu kien", "voi dieu kien", "ap dung",
                    ">=", "≥", "<=", "≤", ">", "<", "=", "tro len", "tro xuong",
                    "lon hon", "nho hon", "cao hon", "thap hon", "vuot", "duoi", "tren",
                    "tu", "toi thieu", "toi da"
                ]
                has_condition_cue = any(cue in ctx for cue in explicit_condition_cues)

                if has_incidental and not any(kw in ctx for kw in ["nguong", "khi", "neu", "tro len", "tro xuong", ">=", "<="]):
                    continue

                if not has_condition_cue:
                    continue

                # Evidenced direction extraction
                ev_direction = None
                # Check >= (GE) before > (GT)
                if any(kw in ctx for kw in [">=", "≥", "tro len", "lon hon hoac bang", "khong thap hon", "toi thieu"]):
                    ev_direction = "GE"
                # Check <= (LE) before < (LT)
                elif any(kw in ctx for kw in ["<=", "≤", "tro xuong", "nho hon hoac bang", "khong vuot qua", "khong qua", "toi da"]):
                    ev_direction = "LE"
                elif any(kw in ctx for kw in [">", "lon hon", "cao hon", "tren", "vuot"]):
                    ev_direction = "GT"
                elif any(kw in ctx for kw in ["<", "nho hon", "thap hon", "duoi"]):
                    ev_direction = "LT"
                elif any(kw in ctx for kw in ["=", "bang", "dat muc", "chinh xac"]):
                    ev_direction = "EQ"
                elif "tu" in ctx:
                    ev_direction = "GE"

                # Boundary contradiction check
                if op in ("GE", "GT") and ev_direction in ("LT", "LE"):
                    boundary_contradiction = True
                    break
                elif op in ("LE", "LT") and ev_direction in ("GT", "GE"):
                    boundary_contradiction = True
                    break
                elif op == "EQ" and ev_direction in ("LT", "LE", "GT", "GE"):
                    boundary_contradiction = True
                    break

                # Strict operator matching: preserve boundary equality
                # Do NOT silently broaden GE to GT or LE to LT!
                if op == "GE" and ev_direction == "GE":
                    threshold_located = True
                    break
                elif op == "GT" and ev_direction == "GT":
                    threshold_located = True
                    break
                elif op == "LE" and ev_direction == "LE":
                    threshold_located = True
                    break
                elif op == "LT" and ev_direction == "LT":
                    threshold_located = True
                    break
                elif op == "EQ":
                    if ev_direction in ("EQ", None) and has_condition_cue:
                        threshold_located = True
                        break

            if boundary_contradiction:
                return (
                    False,
                    ReasonCode.CONDITION_CONTRADICTED,
                    f"Threshold boundary contradiction: claim requires {op} {cond.value} {cond.unit}, "
                    f"but evidence specifies incompatible boundary direction",
                )

            if not threshold_located:
                return (
                    False,
                    ReasonCode.CONDITION_MISSING,
                    f"Evidence lacks required threshold condition: {op} {cond.value} {cond.unit}",
                )

        return True, ReasonCode.CONDITION_MATCHED, "Conditions verified in evidence"

    # -------------------------------------------------------------------------
    # 6.5 Legal and Governance Scope (P5-KNOWN-01 & P5-KNOWN-02)
    # -------------------------------------------------------------------------
    def match_legal_scope(
        self,
        claim_actor: Optional[str],
        claim_action: Optional[str],
        claim_polarity: ClaimPolarity,
        claim_jurisdiction: Optional[str],
        evidence_text: str,
    ) -> tuple[bool, Optional[ReasonCode], str]:
        """Check legal authority, action, polarity, and multi-word jurisdiction.

        Enforces:
        - Actual evidence required for the claimed action.
        - Actor, action, jurisdiction, and polarity bound together per clause.
        - Action absent -> ACTION_MISMATCH (INSUFFICIENT).
        - Polarity UNKNOWN -> POLARITY_UNKNOWN (INSUFFICIENT).
        - Different actor's negation does NOT contradict the claim actor.
        - Preserves P5-KNOWN-01 (Đồng Nai vs Đồng Tháp) and P5-KNOWN-02 (negation reversal).
        """
        norm_ev = strip_accents_lower(evidence_text)

        # 1. P5-KNOWN-01: Multi-word jurisdiction check
        if claim_jurisdiction:
            norm_jur = strip_accents_lower(claim_jurisdiction)
            known_provinces = [
                "dong nai", "dong thap", "an giang", "long an", "tien giang",
                "ha noi", "hoa binh", "son la", "phu tho", "vinh phuc", "bac ninh",
            ]
            claim_prov = None
            for prov in known_provinces:
                if prov in norm_jur:
                    claim_prov = prov
                    break

            if claim_prov:
                ev_prov = None
                for prov in known_provinces:
                    if prov in norm_ev:
                        ev_prov = prov
                        break

                if ev_prov and ev_prov != claim_prov:
                    return (
                        False,
                        ReasonCode.JURISDICTION_MISMATCH,
                        f"P5-KNOWN-01: Jurisdiction conflict: claim asserts '{claim_jurisdiction}' "
                        f"(province {claim_prov}), but evidence specifies province '{ev_prov}'",
                    )
                if not ev_prov and claim_prov not in norm_ev:
                    return (
                        False,
                        ReasonCode.JURISDICTION_UNKNOWN,
                        f"Jurisdiction '{claim_jurisdiction}' not found in evidence",
                    )
            else:
                if norm_jur not in norm_ev:
                    return (
                        False,
                        ReasonCode.JURISDICTION_UNKNOWN,
                        f"Jurisdiction '{claim_jurisdiction}' not found in evidence",
                    )

        # 2. Polarity requirement: UNKNOWN polarity cannot establish authorization or prohibition
        if claim_action:
            if claim_polarity == ClaimPolarity.UNKNOWN:
                return (
                    False,
                    ReasonCode.POLARITY_UNKNOWN,
                    "Legal claim has UNKNOWN polarity; cannot establish verified authorization or prohibition",
                )

        # 3. Action presence & Actor-Action Clause Binding
        if claim_action:
            norm_action = strip_accents_lower(claim_action)
            norm_actor = strip_accents_lower(claim_actor or "")

            action_terms = [t for t in norm_action.split() if len(t) > 2]
            action_keywords_found = norm_action in norm_ev or (
                len(action_terms) >= 2 and all(term in norm_ev for term in action_terms)
            ) or any(
                phrase in norm_ev
                for phrase in [
                    "quyet dinh xa lu",
                    "quyet dinh phuong an",
                    "phe duyet phuong an",
                    "ban hanh lenh",
                    "dong mo cong",
                    "chi dao cong tac",
                ]
                if phrase in norm_action
            )

            if not action_keywords_found:
                return (
                    False,
                    ReasonCode.ACTION_MISMATCH,
                    f"Claimed legal action '{claim_action}' is not evidenced in text",
                )

            # Split evidence into clauses by punctuation and contrastive conjunctions
            clause_delimiters = r"[;\n\.]+|(?:\s*,\s*|\s+)(?:còn|nhưng|trong khi|tuy nhiên|ngược lại|song)\s+"
            clauses = [c.strip() for c in re.split(clause_delimiters, evidence_text, flags=re.IGNORECASE) if c.strip()]

            # Formal legal prohibition cues (formal legal negation)
            formal_prohibition_cues = [
                "khong duoc", "khong duoc quyen", "khong co tham quyen", "nghiem cam", "cam ",
                "khong thuoc tham quyen", "khong co quyen", "khong duoc phep",
                "khong duoc tu y", "bi cam"
            ]

            # Formal legal authorization cues (explicit legal permission/mandate)
            # MUST NOT include bare action terms like "quyet dinh xa lu"!
            formal_authorization_cues = [
                "duoc quyen", "co quyen", "co tham quyen", "thuoc tham quyen", "duoc phep",
                "duoc quyet dinh", "co trach nhiem ban hanh", "chiu trach nhiem ban hanh",
                "co trach nhiem phe duyet", "chiu trach nhiem phe duyet", "quy dinh tham quyen",
                "giao tham quyen", "duoc giao quyen", "phan cong tham quyen",
                "co trach nhiem", "chiu trach nhiem"
            ]

            # Actual performance / Past action cues (Performance != Legal Authority)
            past_performance_cues = [
                "da quyet dinh", "da ban hanh", "da tien hanh", "da thuc hien",
                "da thuc thi", "vua qua da", "hom qua da", "ngay qua da", "da xa lu"
            ]

            # Pending authorization cues (Pending != Authority & Pending != Prohibition)
            pending_auth_cues = [
                "chua duoc", "chua duoc phep", "chua duoc quyen", "cho phe duyet",
                "dang cho", "chua co tham quyen", "cho y kien", "chua duoc quyet dinh"
            ]

            # Inability cues (Inability != Authority & Inability != Prohibition)
            inability_cues = [
                "khong the", "chua the", "khong co kha nang", "khong du dieu kien"
            ]

            # Advice / recommendation cues (Advice != Authority & Advice != Prohibition)
            advice_cues = [
                "khong nen", "nen ", "khuyen nghi", "de xuat", "kien nghi"
            ]

            # Assignment to study/research/propose (Study != Authority to decide)
            study_assignment_cues = [
                "duoc giao nghien cuu", "giao nghien cuu", "nghien cuu",
                "khao sat", "tham muu", "de xuat phuong an", "bao cao de xuat"
            ]

            illegal_or_investigation_cues = [
                "trai phep", "vi pham", "sai quy dinh", "sai pham", "khong dung tham quyen",
                "dieu tra", "xem xet ve viec", "khoi to", "truy to", "ky luat", "dinh chi",
                "chiu trach nhiem hinh su", "bi co quan dieu tra", "co quan dieu tra xem xet"
            ]

            discussion_cues = [
                "phat bieu tai", "tham du cuoc hop", "trao doi ve", "thao luan ve", "hoi y ve",
                "bao cao ve", "du hop ve", "chu tri cuoc hop"
            ]

            known_actor_roles = [
                "ban chi huy", "ban chi dao", "bo tai nguyen", "bo nong nghiep", "bo cong thuong",
                "tong cuc", "cuc truong", "chu tich ubnd", "ubnd tinh", "ubnd huyen", "ubnd xa",
                "thu tuong", "pho thu tuong", "giam doc", "chu ho", "don vi quan ly",
                "co quan khac", "don vi khac", "to chuc khac", "nguoi khac", "luc luong chuc nang"
            ]

            matching_actor_action_clause_found = False
            polarity_contradicted = False
            diff_actor_clause_detected = False
            diff_actor_name_detected = ""
            illegal_context_detected = False
            ambiguous_context_detected = False
            last_polarity_explanation = ""

            for clause in clauses:
                norm_c = strip_accents_lower(clause)

                clause_has_action = norm_action in norm_c or (
                    len(action_terms) >= 2 and all(term in norm_c for term in action_terms)
                ) or any(
                    phrase in norm_c
                    for phrase in [
                        "quyet dinh xa lu",
                        "quyet dinh phuong an",
                        "phe duyet phuong an",
                        "ban hanh lenh",
                        "dong mo cong",
                        "chi dao cong tac",
                    ]
                    if phrase in norm_action
                )

                if not clause_has_action:
                    continue

                actor_in_clause = False
                if norm_actor and norm_actor in norm_c:
                    actor_in_clause = True
                elif norm_actor:
                    actor_tokens = [tok for tok in norm_actor.split() if len(tok) > 2]
                    if len(actor_tokens) >= 2 and all(tok in norm_c for tok in actor_tokens):
                        actor_in_clause = True
                    elif any(role in norm_c for role in ["bo tai nguyen", "truong ban chi huy", "chu tich ubnd"]) and any(role in norm_actor for role in ["bo tai nguyen", "truong ban chi huy", "chu tich ubnd"]):
                        actor_in_clause = True

                diff_actor = False
                for role in known_actor_roles:
                    if role in norm_c and (not norm_actor or role not in norm_actor):
                        diff_actor = True
                        diff_actor_name_detected = role
                        break

                if diff_actor and not actor_in_clause:
                    diff_actor_clause_detected = True
                    continue

                if not actor_in_clause:
                    continue

                # Both claim actor and action are in this clause!
                matching_actor_action_clause_found = True

                # Check for illegal context or investigation
                if any(icue in norm_c for icue in illegal_or_investigation_cues):
                    illegal_context_detected = True
                    continue

                # Check for assignment to study/research
                if any(scue in norm_c for scue in study_assignment_cues):
                    ambiguous_context_detected = True
                    continue

                # Check for past performance (actual performance != authority)
                is_past_action = any(pcue in norm_c for pcue in past_performance_cues) or bool(
                    re.search(r"\bda\s+(?:quyet dinh|ban hanh|tien hanh|thuc hien|xa lu)\b", norm_c)
                )
                if is_past_action:
                    ambiguous_context_detected = True
                    continue

                # Check for pending authorization (pending != authority & pending != prohibition)
                if any(pcue in norm_c for pcue in pending_auth_cues):
                    ambiguous_context_detected = True
                    continue

                # Check for inability (inability != authority & inability != prohibition)
                if any(icue in norm_c for icue in inability_cues):
                    ambiguous_context_detected = True
                    continue

                # Check for advice / recommendation
                if any(acue in norm_c for acue in advice_cues):
                    ambiguous_context_detected = True
                    continue

                # Check for mere discussion or attendance
                if any(dcue in norm_c for dcue in discussion_cues):
                    ambiguous_context_detected = True
                    continue

                # Evaluate formal modality
                is_prohibition = any(neg in norm_c for neg in formal_prohibition_cues)
                if is_prohibition:
                    has_auth = False
                else:
                    has_auth = any(auth in norm_c for auth in formal_authorization_cues)
                    # Special case: Regulatory decree / statute text (e.g. QĐ 740/QĐ-TTg) stating:
                    # "[Actor] quyet dinh phuong an van hanh / ban hanh lenh..." in present declarative tense
                    # without past or modal markers
                    if not has_auth:
                        declarative_statute_pattern = (
                            r"\b(?:" + re.escape(norm_actor) + r")\s+(?:quyet dinh phuong an|ban hanh lenh|chi dao van hanh)\b"
                        )
                        if re.search(declarative_statute_pattern, norm_c):
                            has_auth = True

                if is_prohibition:
                    clause_polarity = ClaimPolarity.NEGATED
                elif has_auth:
                    clause_polarity = ClaimPolarity.AFFIRMED
                else:
                    ambiguous_context_detected = True
                    continue

                if claim_polarity != clause_polarity:
                    polarity_contradicted = True
                    last_polarity_explanation = (
                        f"P5-KNOWN-02: Legal polarity contradiction: claim is {claim_polarity.value} "
                        f"('{claim_action}'), but evidence establishes {clause_polarity.value}"
                    )
                else:
                    return (
                        True,
                        ReasonCode.POLARITY_MATCHED,
                        f"Legal governance scope and action '{claim_action}' ({claim_polarity.value}) "
                        f"verified for '{claim_actor}'",
                    )

            if polarity_contradicted:
                return (
                    False,
                    ReasonCode.POLARITY_CONTRADICTED,
                    last_polarity_explanation,
                )

            if illegal_context_detected:
                return (
                    False,
                    ReasonCode.ACTION_MISMATCH,
                    f"Action '{claim_action}' is mentioned in context of illegal act, violation, or investigation; cannot establish legal authorization for '{claim_actor}'",
                )

            if ambiguous_context_detected:
                return (
                    False,
                    ReasonCode.ACTION_MISMATCH,
                    f"Action '{claim_action}' is mentioned without explicit legal authorization or prohibition for '{claim_actor}'",
                )

            if not matching_actor_action_clause_found:
                if diff_actor_clause_detected:
                    return (
                        False,
                        ReasonCode.ACTION_MISMATCH,
                        f"Action '{claim_action}' is evidenced only for a different actor ('{diff_actor_name_detected}') in text, not for '{claim_actor}'",
                    )
                return (
                    False,
                    ReasonCode.ACTION_MISMATCH,
                    f"Action '{claim_action}' is not evidenced for '{claim_actor}' in text",
                )

        return True, ReasonCode.POLARITY_MATCHED, "Legal governance scope verified"

    # -------------------------------------------------------------------------
    # Comprehensive Single-Item Comparison
    # -------------------------------------------------------------------------
    def compare_claim_to_evidence_item(
        self, claim: TechnicalClaim, item: EvidenceItem
    ) -> EvidenceMatchAssessment:
        """Compare a structured claim to a single EvidenceItem."""
        assessment = EvidenceMatchAssessment()
        assessment.evidence_trace.append({
            "evidence_id": item.evidence_id,
            "doc_id": item.doc_id,
            "page_number": item.page_number,
            "citation_key": list(item.citation_key()),
            "content_type": item.content_type,
        })

        ev_text = item.text

        # 1. Provenance & Document Scope Check (Exact matching & verified aliases only)
        if claim.document_scope:
            norm_scope = strip_accents_lower(claim.document_scope)
            norm_doc = strip_accents_lower(item.doc_id)
            norm_num = strip_accents_lower(item.document_number or "")
            norm_version = strip_accents_lower(item.document_version or "")

            exact_match = (
                norm_scope == norm_doc
                or (bool(norm_num) and norm_scope == norm_num)
                or (bool(norm_version) and norm_scope == norm_version)
            )

            # Authoritative verified alias pairs (e.g. DOC_740 <-> 740/qd-ttg)
            alias_pairs = {
                ("doc_740", "740/qd-ttg"),
                ("doc_922", "922/qd-ttg"),
            }
            if not exact_match:
                for a, b in alias_pairs:
                    if norm_scope in (a, b) and (norm_doc in (a, b) or norm_num in (a, b)):
                        exact_match = True
                        break

            if not exact_match:
                assessment.is_insufficient = True
                assessment.reason_codes.append(ReasonCode.DOCUMENT_MISMATCH)
                assessment.explanations.append(
                    f"Evidence item {item.evidence_id} belongs to doc '{item.doc_id}', "
                    f"not matching claim scope '{claim.document_scope}'"
                )
                return assessment

        assessment.provenance_valid = True

        # Check claim's own unit dimension compatibility with its parameter first!
        if claim.unit and claim.parameter:
            compat, compat_msg = check_unit_compatibility(claim.parameter, claim.unit)
            if not compat:
                if "not recognized in hydraulic unit registry" in compat_msg or "Unknown physical unit" in compat_msg:
                    assessment.is_insufficient = True
                    assessment.missing_slots.append("ontology_coverage")
                    assessment.reason_codes.append(ReasonCode.MISSING_REQUIRED_SLOT)
                    assessment.explanations.append(f"Domain out of scope: {compat_msg}")
                    return assessment
                else:
                    assessment.is_contradiction = True
                    assessment.conflicting_evidence_ids.append(item.evidence_id)
                    assessment.reason_codes.append(ReasonCode.UNIT_INCOMPATIBLE)
                    assessment.explanations.append(compat_msg)
                    return assessment

        # 2. Entity Matching
        if claim.subject:
            ent_matched, ent_val, ent_rc = self.match_entity(claim.subject, ev_text, claim_val=claim.value)
            if ent_rc == ReasonCode.ENTITY_MISMATCH:
                assessment.is_contradiction = True
                assessment.conflicting_evidence_ids.append(item.evidence_id)
                # If the entity mismatch was due to a province/jurisdiction in the subject, tag both
                norm_subj = strip_accents_lower(claim.subject)
                if any(p in norm_subj for p in ["dong nai", "dong thap"]):
                    assessment.reason_codes.append(ReasonCode.JURISDICTION_MISMATCH)
                assessment.reason_codes.append(ReasonCode.ENTITY_MISMATCH)
                assessment.explanations.append(
                    f"Entity mismatch: claim subject '{claim.subject}' contradicted by evidence entity '{ent_val}'"
                )
                return assessment
            elif ent_rc == ReasonCode.ENTITY_UNKNOWN:
                assessment.is_insufficient = True
                assessment.reason_codes.append(ReasonCode.ENTITY_UNKNOWN)
                assessment.missing_slots.append("subject")
                assessment.explanations.append(f"Subject '{claim.subject}' not evidenced in item {item.evidence_id}")
                return assessment
            assessment.entity_matched = True

        # 3. Parameter Matching
        if claim.parameter:
            param_matched, param_key, param_rc = self.match_parameter(claim.parameter, ev_text, claim_val=claim.value)
            if param_rc == ReasonCode.PARAMETER_MISMATCH:
                assessment.is_contradiction = True
                assessment.conflicting_evidence_ids.append(item.evidence_id)
                assessment.reason_codes.append(ReasonCode.PARAMETER_MISMATCH)
                assessment.explanations.append(
                    f"Parameter mismatch: claim parameter '{claim.parameter}' conflicted with evidence parameter '{param_key}'"
                )
                return assessment
            elif param_rc in (ReasonCode.PARAMETER_AMBIGUOUS, ReasonCode.MISSING_REQUIRED_SLOT):
                assessment.is_insufficient = True
                assessment.reason_codes.append(param_rc)
                assessment.missing_slots.append("parameter")
                assessment.explanations.append(f"Parameter '{claim.parameter}' not verified in evidence item {item.evidence_id}")
                return assessment
            assessment.parameter_matched = True

        # 4. Conditions and time are applicability gates. Different scope makes an
        # item irrelevant; it does not contradict the claim.
        if claim.conditions:
            cond_ok, cond_rc, cond_msg = self.match_conditions(
                claim.conditions, ev_text, claim_subject=claim.subject, claim_parameter=claim.parameter
            )
            if not cond_ok:
                assessment.is_insufficient = True
                assessment.missing_slots.append("conditions")
                assessment.reason_codes.append(cond_rc or ReasonCode.CONDITION_MISSING)
                assessment.explanations.append(cond_msg)
                return assessment
            assessment.conditions_matched = True
            assessment.reason_codes.append(ReasonCode.CONDITION_MATCHED)
        else:
            norm_ev_conditions = strip_accents_lower(ev_text)
            has_frequency = re.search(r"p\s*=\s*[\d,\.]+\s*%", norm_ev_conditions)
            has_season = any(
                season in norm_ev_conditions
                for season in ["mua lu", "mua can", "lu chinh vu", "lu som", "lu muon"]
            )
            # Static design parameters (MNDBT, MNC, storage volumes, dam height) are structural constants
            # and do not require seasonal conditions unless the claim specifically addresses flood operation.
            is_static_param = False
            if claim.parameter:
                param_key, _, _ = self.identify_parameter(claim.parameter)
                norm_p = strip_accents_lower(claim.parameter)
                if param_key in STATIC_DESIGN_PARAMETERS or any(
                    sp in norm_p for sp in ["mndbt", "mnc", "dung tich toan bo", "dung tich chet", "muc nuoc chet", "muc nuoc dang binh thuong"]
                ):
                    is_static_param = True

            # A flood-frequency qualifier always changes applicability, even
            # for a static design parameter.  Seasonal context can be omitted
            # only for genuinely static parameters.
            if has_frequency or (has_season and not is_static_param):
                assessment.is_insufficient = True
                assessment.missing_slots.append("claim_conditions")
                assessment.reason_codes.append(ReasonCode.CONDITION_MISSING)
                assessment.explanations.append(
                    f"Evidence item {item.evidence_id} is condition-specific but the claim has no application condition"
                )
                return assessment

        if claim.temporal_scope:
            norm_time = strip_accents_lower(claim.temporal_scope)
            if norm_time not in strip_accents_lower(ev_text):
                assessment.is_insufficient = True
                assessment.missing_slots.append("temporal_scope")
                assessment.reason_codes.append(ReasonCode.TEMPORAL_SCOPE_MISMATCH)
                assessment.explanations.append(
                    f"Evidence item {item.evidence_id} does not establish temporal scope '{claim.temporal_scope}'"
                )
                return assessment

        # 5. Numeric value and unit must be bound to the exact parameter.
        if claim.value is not None:
            bindings = self.extract_parameter_numeric_bindings(claim.parameter, ev_text, claim_subject=claim.subject)
            if not bindings:
                assessment.is_insufficient = True
                assessment.missing_slots.append("parameter_value_binding")
                assessment.reason_codes.append(ReasonCode.MISSING_REQUIRED_SLOT)
                assessment.explanations.append(
                    f"No value is explicitly bound to parameter '{claim.parameter}' in evidence item {item.evidence_id}"
                )
                return assessment

            matching_bindings: list[tuple[str, str]] = []
            conflicting_bindings: list[tuple[str, str]] = []
            best_conflict_rc = ReasonCode.VALUE_CONTRADICTED
            best_conflict_explanation = ""
            for raw_ev_val, ev_unit in bindings:
                if not claim.unit:
                    param_key, meta, _ = self.identify_parameter(claim.parameter)
                    if meta and "dimension" in meta:
                        assessment.is_insufficient = True
                        assessment.missing_slots.append("unit")
                        assessment.reason_codes.append(ReasonCode.MISSING_REQUIRED_SLOT)
                        assessment.explanations.append(
                            f"Physical parameter '{claim.parameter}' requires an explicit measurement unit in claim"
                        )
                        return assessment

                if claim.unit and not ev_unit:
                    assessment.is_insufficient = True
                    assessment.missing_slots.append("unit")
                    assessment.reason_codes.append(ReasonCode.MISSING_REQUIRED_SLOT)
                    assessment.explanations.append(
                        f"Unit for parameter '{claim.parameter}' is ambiguous in evidence item {item.evidence_id}"
                    )
                    return assessment
                val_ok, val_rc, val_msg = self.match_numeric_value_and_unit(
                    claim.value, claim.unit, raw_ev_val, ev_unit, param_name=claim.parameter
                )
                if val_ok:
                    matching_bindings.append((raw_ev_val, ev_unit))
                    assessment.reason_codes.append(val_rc or ReasonCode.VALUE_MATCHED)
                else:
                    conflicting_bindings.append((raw_ev_val, ev_unit))
                    if val_rc == ReasonCode.UNIT_INCOMPATIBLE:
                        best_conflict_rc = ReasonCode.UNIT_INCOMPATIBLE
                    best_conflict_explanation = val_msg

            if matching_bindings:
                assessment.value_matched = True
                assessment.unit_matched = True
            elif best_conflict_rc == ReasonCode.UNIT_INCOMPATIBLE:
                assessment.is_contradiction = True
                assessment.conflicting_evidence_ids.append(item.evidence_id)
                assessment.reason_codes.append(ReasonCode.UNIT_INCOMPATIBLE)
                assessment.explanations.append(best_conflict_explanation)
                return assessment
            elif assessment.entity_matched and assessment.parameter_matched:
                assessment.is_contradiction = True
                assessment.conflicting_evidence_ids.append(item.evidence_id)
                assessment.reason_codes.append(ReasonCode.VALUE_CONTRADICTED)
                assessment.explanations.append(
                    f"Value contradiction for {claim.subject} - {claim.parameter}: "
                    f"claim={claim.value}, bound evidence values={bindings}"
                )
                return assessment
            else:
                assessment.is_insufficient = True
                assessment.reason_codes.append(ReasonCode.VALUE_CONTRADICTED)
                assessment.explanations.append(best_conflict_explanation or "Bound numeric value not matched")
                return assessment

        # 6. Legal / Governance Scope (P5-KNOWN-01 & P5-KNOWN-02)
        norm_claim_text = strip_accents_lower(claim.claim_text or "")
        legal_keywords = [
            "quyet dinh", "tham quyen", "duoc quyen", "khong duoc", "phe duyet", "ban hanh",
            "ubnd", "ban chi huy", "chu tich", "bo truong", "bo tai nguyen", "bo nong nghiep",
            "ban chi dao", "uy ban nhan dan"
        ]
        is_legal_claim = bool(
            claim.action
            or claim.jurisdiction
            or claim.polarity != ClaimPolarity.UNKNOWN
            or (not claim.parameter and not claim.value and any(kw in norm_claim_text for kw in legal_keywords))
        )

        if is_legal_claim:
            if not claim.action or not claim.action.strip():
                # Incomplete structured legal claim: missing mandatory 'action' slot
                assessment.is_insufficient = True
                assessment.missing_slots.append("action")
                assessment.reason_codes.append(ReasonCode.INCOMPLETE_CLAIM_EXTRACTION)
                assessment.reason_codes.append(ReasonCode.MISSING_REQUIRED_SLOT)
                assessment.explanations.append(
                    "Structured legal claim is incomplete: missing required 'action' field to verify authorization"
                )
                return assessment

            leg_ok, leg_rc, leg_msg = self.match_legal_scope(
                claim.subject, claim.action, claim.polarity, claim.jurisdiction, ev_text
            )
            if not leg_ok:
                if leg_rc in (ReasonCode.POLARITY_CONTRADICTED, ReasonCode.JURISDICTION_MISMATCH):
                    assessment.is_contradiction = True
                    assessment.conflicting_evidence_ids.append(item.evidence_id)
                else:
                    assessment.is_insufficient = True
                    if leg_rc == ReasonCode.JURISDICTION_UNKNOWN:
                        assessment.missing_slots.append("jurisdiction")
                    elif leg_rc == ReasonCode.ACTION_MISMATCH:
                        assessment.missing_slots.append("action")
                    elif leg_rc == ReasonCode.POLARITY_UNKNOWN:
                        assessment.missing_slots.append("polarity")
                assessment.reason_codes.append(leg_rc or ReasonCode.ACTION_MISMATCH)
                assessment.explanations.append(leg_msg)
                return assessment
            assessment.legal_matched = True
            assessment.reason_codes.append(leg_rc or ReasonCode.POLARITY_MATCHED)

        # If we got here, all claimed slots are satisfied!
        assessment.matched = True
        assessment.supporting_evidence_ids.append(item.evidence_id)
        assessment.reason_codes.append(ReasonCode.EVIDENCE_MATCH_EXACT)
        assessment.explanations.append(f"Claim successfully matched by evidence item {item.evidence_id}")
        return assessment

    # -------------------------------------------------------------------------
    # Complementary Multi-Region Synthesis
    # -------------------------------------------------------------------------
    def synthesize_multi_region_evidence(
        self, claim: TechnicalClaim, items: list[EvidenceItem], relations: list[EvidenceRelation]
    ) -> EvidenceMatchAssessment:
        """Combine only provenance-compatible items connected by verified relations."""
        composite_assessment = EvidenceMatchAssessment()
        by_id = {item.evidence_id: item for item in items}
        valid_relations = [
            rel for rel in relations
            if rel.verified
            and rel.relation_type != "unknown"
            and rel.source_id in by_id
            and rel.target_id in by_id
            and by_id[rel.source_id].doc_id == by_id[rel.target_id].doc_id
        ]
        if not valid_relations:
            composite_assessment.is_insufficient = True
            composite_assessment.missing_slots.append("verified_evidence_relation")
            composite_assessment.reason_codes.append(ReasonCode.EVIDENCE_RELATION_MISSING)
            composite_assessment.explanations.append(
                "Multi-region support requires an explicit verified relation within one document"
            )
            return composite_assessment

        adjacency: dict[str, set[str]] = {item_id: set() for item_id in by_id}
        for rel in valid_relations:
            adjacency[rel.source_id].add(rel.target_id)
            adjacency[rel.target_id].add(rel.source_id)

        visited: set[str] = set()
        for root in by_id:
            if root in visited or not adjacency[root]:
                continue
            stack = [root]
            component_ids: list[str] = []
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                component_ids.append(current)
                stack.extend(adjacency[current] - visited)

            component = [by_id[item_id] for item_id in component_ids]
            header_targets = {
                rel.target_id for rel in valid_relations
                if rel.relation_type == "table_row_to_header"
                and rel.source_id in component_ids and rel.target_id in component_ids
            }
            original_order = {item.evidence_id: idx for idx, item in enumerate(items)}
            component.sort(
                key=lambda item: (0 if item.evidence_id in header_targets else 1, original_order[item.evidence_id])
            )
            first_item = component[0]
            synthetic_item = EvidenceItem(
                evidence_id=f"SYNTHETIC_COMBO_{'_'.join(it.evidence_id for it in component)}",
                doc_id=first_item.doc_id,
                page_id=first_item.page_id,
                page_number=first_item.page_number,
                content_type="text",
                text=" ".join(item.text for item in component),
                source=first_item.source,
                document_number=first_item.document_number,
                document_version=first_item.document_version,
            )
            single_res = self.compare_claim_to_evidence_item(claim, synthetic_item)
            if single_res.matched:
                composite_assessment.matched = True
                composite_assessment.supporting_evidence_ids = [it.evidence_id for it in component]
                composite_assessment.reason_codes.append(ReasonCode.EVIDENCE_MULTI_REGION_MATCH)
                composite_assessment.explanations.append(
                    f"Verified multi-region synthesis across {len(component)} related items: "
                    f"{[it.evidence_id for it in component]}"
                )
                composite_assessment.evidence_trace = [
                    {
                        "evidence_id": it.evidence_id,
                        "doc_id": it.doc_id,
                        "page_number": it.page_number,
                        "citation_key": list(it.citation_key()),
                    }
                    for it in component
                ]
                return composite_assessment
            if single_res.is_contradiction:
                return single_res

        composite_assessment.is_insufficient = True
        composite_assessment.missing_slots.append("linked_supporting_evidence")
        composite_assessment.reason_codes.append(ReasonCode.EVIDENCE_RELATION_MISSING)
        composite_assessment.explanations.append(
            "No verified relation-connected component establishes every required claim slot"
        )
        return composite_assessment
