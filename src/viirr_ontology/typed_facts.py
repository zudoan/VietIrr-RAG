"""Source-Grounded Typed Facts for VietIRR-RAG Ontology Verification.

Implements typed facts inspired by W3C SOSA/SSN, OWL-Time, QUDT, and PROV-O standards:
- ObservationFact: Instantaneous or periodic point observation (FeatureOfInterest, ObservableProperty, Time, Unit).
- DesignSpecificationFact: Fixed regulatory design/operating thresholds (MNDBT, MNC, MNLTK, MNLKT, W_hi...).
- DocumentRegulationFact: Legal decree, jurisdiction, action, polarity, effective date, and scope.
- ProvenanceMetadata: Strict 5-level provenance tracking (doc_id, page_number, region_id, table_id, cell coordinates, hash).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from viirr_ontology.domain.unit_registry import UnitDimension, get_unit_dimension, normalize_unit_string
from viirr_ontology.schema.evidence import EvidenceItem


class FactType(str, Enum):
    OBSERVATION = "OBSERVATION"
    DESIGN_SPECIFICATION = "DESIGN_SPECIFICATION"
    DOCUMENT_REGULATION = "DOCUMENT_REGULATION"


class ObservationType(str, Enum):
    ACTUAL_OBSERVED = "ACTUAL_OBSERVED"
    DESIGN_CAPACITY = "DESIGN_CAPACITY"
    FORECAST_ESTIMATE = "FORECAST_ESTIMATE"
    ALERT_THRESHOLD = "ALERT_THRESHOLD"


@dataclass(frozen=True)
class ProvenanceMetadata:
    """Strict 5-level provenance tracking conforming to W3C PROV-O."""
    document_id: str
    document_number: Optional[str] = None
    document_version: Optional[str] = None
    page_number: int = 1
    region_id: Optional[str] = None
    table_id: Optional[str] = None
    row_idx: Optional[int] = None
    col_idx: Optional[int] = None
    source_content_hash: Optional[str] = None
    exact_text_snippet: str = ""

    def citation_key(self) -> Tuple[str, int, str]:
        return self.document_id, self.page_number, self.region_id or f"P{self.page_number:04d}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ObservationFact:
    """Hydrological point observation (SOSA/SSN Observation + OWL-Time + QUDT)."""
    fact_id: str
    entity_id: str
    canonical_entity_name: str
    parameter_id: str
    canonical_parameter_name: str
    observation_type: ObservationType
    numeric_value: float
    raw_value_str: str
    unit: str
    unit_dimension: UnitDimension
    observation_time: Optional[str] = None
    reporting_period: Optional[str] = None
    provenance: ProvenanceMetadata = field(default_factory=lambda: ProvenanceMetadata(document_id="UNKNOWN"))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["unit_dimension"] = self.unit_dimension.value
        d["observation_type"] = self.observation_type.value
        return d


@dataclass(frozen=True)
class DesignSpecificationFact:
    """Fixed normative design or operational specification parameter."""
    fact_id: str
    entity_id: str
    canonical_entity_name: str
    parameter_id: str
    canonical_parameter_name: str
    numeric_value: float
    raw_value_str: str
    unit: str
    unit_dimension: UnitDimension
    condition: Optional[str] = None
    document_authority: str = ""
    article_reference: str = ""
    provenance: ProvenanceMetadata = field(default_factory=lambda: ProvenanceMetadata(document_id="UNKNOWN"))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["unit_dimension"] = self.unit_dimension.value
        return d


@dataclass(frozen=True)
class DocumentRegulationFact:
    """Legal decree, administrative jurisdiction, action, polarity, and applicability scope."""
    fact_id: str
    document_id: str
    document_number: str
    article: str
    jurisdiction: str
    action: str
    polarity: str  # AFFIRMED vs NEGATED
    effective_date: Optional[str] = None
    applicable_scope: List[str] = field(default_factory=list)
    amends_document_id: Optional[str] = None
    provenance: ProvenanceMetadata = field(default_factory=lambda: ProvenanceMetadata(document_id="UNKNOWN"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# NORMALIZATION & EXTRACTION HELPERS
# =============================================================================

def strip_accents_lower(s: str) -> str:
    """Strip accents and lower-case for robust phonetic comparison."""
    if not s:
        return ""
    s = s.replace("đ", "d").replace("Đ", "d")
    s = s.replace("ç", "o").replace("Ç", "o")
    norm = unicodedata.normalize("NFD", s.lower())
    without = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", without).strip()


def parse_vietnamese_number(val_str: Any) -> Optional[float]:
    """Parse numeric values supporting Vietnamese comma decimal separator and signed numbers (-3, −3)."""
    if val_str is None:
        return None
    s = str(val_str).strip()
    if not s:
        return None

    # Normalize Unicode minus sign (\u2212) to standard ASCII minus (-)
    s = s.replace("\u2212", "-")

    # Handle range or compound numbers: e.g. "117,0 - 118,0" -> take first
    # Only split on range separator if preceded by a digit, or on words 'đến', 'den'
    range_parts = re.split(r"(?<=\d)\s*[-–—~]\s*(?=[-+]?\d)|đến|den", s, maxsplit=1)
    if range_parts:
        s = range_parts[0].strip()

    # Vietnamese decimal comma vs thousand dot (e.g., "117,0" -> 117.0, "12.000" -> 12000.0)
    match_vnd_comma = re.search(r"[-+]?\d+(?:,\d+)", s)
    match_dot_thousand = re.search(r"[-+]?\d{1,3}(?:\.\d{3})+(?:,\d+)?", s)

    if match_dot_thousand:
        # e.g. 12.000,5 -> 12000.5 or 12.000 -> 12000
        clean = s.replace(".", "").replace(",", ".")
    elif match_vnd_comma:
        # e.g. 117,0 -> 117.0
        clean = s.replace(",", ".")
    else:
        # Standard float representation
        clean = s

    # Extract first valid floating-point number, preserving sign
    m = re.search(r"[-+]?\d*\.?\d+", clean)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def extract_atomic_claims(
    text: str,
    default_entity: str = "",
    default_parameter: str = "",
    default_unit: str = "",
    citations: Optional[List[Any]] = None,
    qa_id: str = "QA",
) -> List[Any]:
    """Deterministically extracts atomic TechnicalClaims from answer text and question context.
    Strictly preserves polarity, sign (-3, −3), observation type (OBSERVED vs FORECAST vs DESIGN),
    and maps actual citations.
    """
    from viirr_ontology.schema.claim import ClaimPolarity, EvidenceCitation, TechnicalClaim

    claims: List[TechnicalClaim] = []
    if not text:
        return claims
    t_lower = text.lower()
    if any(k in t_lower for k in ["không đủ bằng chứng", "từ chối khẳng định", "chưa đủ dữ liệu", "không thể trả lời"]):
        return claims

    # Normalize unicode minus
    text_norm = text.replace("\u2212", "-")
    inherited_citations = citations or []
    claim_counter = 0

    # -------------------------------------------------------------------------
    # Special Handling: Vietnamese "lần lượt là" (respective enumeration)
    # Pattern: "... kỳ ngày X, ngày Y và ngày Z lần lượt là A, B và C"
    # -------------------------------------------------------------------------
    if re.search(r"\blần lượt là\b|\blan luot la\b", text_norm, flags=re.IGNORECASE):
        parts = re.split(r"\blần lượt là\b|\blan luot la\b", text_norm, flags=re.IGNORECASE, maxsplit=1)
        left, right = parts[0], parts[1]

        # Extract dates from left
        date_matches = list(re.finditer(
            r"(?:ngày\s+)?(\d{1,2})\s*(?:tháng|[/-])\s*(\d{1,2})(?:\s*(?:năm|[/-])\s*(\d{4}))?",
            left,
            re.IGNORECASE,
        ))
        dates: List[str] = []
        for dm in date_matches:
            iso = extract_iso_date(dm.group(0))
            if iso:
                dates.append(iso)

        # Extract measurements from right
        num_matches = [
            m.group(0)
            for m in re.finditer(
                r"([-+]?\d+(?:[,\.]\d+)?)\s*(m3/s|m³/s|triệu m3|tỷ m3|ha|m3|m³|cm|mm|m|%)?",
                right,
                re.IGNORECASE,
            )
            if m.group(1)
        ]

        ent_res = resolve_canonical_entity(left)
        param_res = resolve_canonical_parameter(left)
        ent_name = ent_res[1] if ent_res else default_entity
        param_name = param_res[1] if param_res else default_parameter

        left_lower = left.lower()
        if any(k in left_lower for k in ["dự báo", "du bao", "dự kiến", "du kien", "kỳ dự báo"]):
            obs_type = "FORECAST_ESTIMATE"
        elif any(k in left_lower for k in ["thực đo", "thuc do", "quan trắc", "quan trac", "hiện tại"]):
            obs_type = "ACTUAL_OBSERVED"
        elif any(k in left_lower for k in ["thiết kế", "thiet ke", "mndbt", "mnc"]):
            obs_type = "DESIGN_SPECIFICATION"
        else:
            obs_type = "UNKNOWN"

        if dates and len(dates) == len(num_matches):
            for d_idx, (d_iso, raw_num) in enumerate(zip(dates, num_matches)):
                p_parts = raw_num.strip().split()
                val_str = p_parts[0]
                u_str = p_parts[1] if len(p_parts) > 1 else default_unit
                claim_counter += 1
                claims.append(
                    TechnicalClaim(
                        claim_id=f"{qa_id}_C{claim_counter}",
                        claim_text=f"{ent_name} {param_name} ngày {d_iso} là {val_str} {u_str}",
                        subject=ent_name,
                        parameter=param_name,
                        value=val_str,
                        unit=u_str,
                        temporal_scope=d_iso,
                        observation_type=obs_type,
                        polarity=ClaimPolarity.AFFIRMED,
                        evidence_citations=inherited_citations,
                        extraction_status="CLAUSE_BOUND",
                    )
                )
            return claims

    # -------------------------------------------------------------------------
    # General Sub-Clause Splitting & Local Relation-Aware Binding
    # Split primary text by sentence boundaries (period, newline, semicolon)
    # -------------------------------------------------------------------------
    sentences = [
        s.strip()
        for s in re.split(r"[\r\n]+|(?<=\S)[;]\s*|(?<=\D)\.\s+|(?<=\d{4})\.\s+", text_norm)
        if s.strip()
    ]

    ctx_entity = default_entity
    ctx_parameter = default_parameter
    ctx_obs_type = "UNKNOWN"

    for sent_idx, sent in enumerate(sentences):
        # Coordinate clause segmentation (conjunctions, contrastive markers, list markers, parameter shifts)
        clause_splits = re.split(
            r",?\s+(?:còn|trong khi|đồng thời)\s+|;\s*|"
            r",\s*(?=(?:và\s+)?(?:dự báo|thực đo)\s+ngày|tại\s+[A-Z]|(?:lưu lượng|mực nước|dung tích|cao trình)\s+(?:xả|hồ|trạm|thiết kế|đạt|là|của)\b)|"
            r"\s+và\s+(?=(?:mực nước|lưu lượng|dung tích|cao trình)\b|"
            r"(?:dự báo|thực đo)\s+ngày\b|"
            r"ngày\s+\d{1,2}|"
            r"[A-ZĐÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ][a-zđàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵA-Z0-9_\s]+\s+(?:là|đạt|có)\b)",
            sent,
            flags=re.IGNORECASE,
        )

        for c_idx, clause in enumerate(clause_splits):
            c_str = clause.strip()
            if not c_str:
                continue

            # Local Date Resolution (Clause Scope)
            date_iso = extract_iso_date(c_str)

            # Local Entity Resolution (Preserve antecedent if coordinate clause has no new entity)
            ent_res = resolve_canonical_entity(c_str)
            if ent_res:
                ctx_entity = ent_res[1]
            else:
                # Check for proper noun subject before predicate (e.g. "Long Hiệp là -2 m")
                pn_match = re.match(
                    r"^([A-ZĐÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ][a-zđàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵA-Z0-9_\s]+?)\s+(?:là|đạt|có)\b",
                    c_str,
                )
                if pn_match:
                    ctx_entity = pn_match.group(1).strip()
            ent_name = ctx_entity

            # Local Parameter Resolution (Preserve antecedent if coordinate clause has no new param)
            param_res = resolve_canonical_parameter(c_str)
            if param_res:
                ctx_parameter = param_res[1]
            param_name = ctx_parameter

            # Local Observation Type Resolution
            c_lower = c_str.lower()
            if any(k in c_lower for k in ["dự báo", "du bao", "dự kiến", "du kien", "kỳ dự báo"]):
                local_obs = "FORECAST_ESTIMATE"
            elif any(k in c_lower for k in ["thực đo", "thuc do", "quan trắc", "quan trac", "hiện tại"]):
                local_obs = "ACTUAL_OBSERVED"
            elif any(k in c_lower for k in ["thiết kế", "thiet ke", "mndbt", "mnc", "cao trình đáy"]):
                local_obs = "DESIGN_SPECIFICATION"
            elif ctx_obs_type != "UNKNOWN":
                local_obs = ctx_obs_type
            else:
                local_obs = "UNKNOWN"
            ctx_obs_type = local_obs

            # Local Inline Citations (e.g. "[EVID_01]" or "[TAB_01_R001_C002]")
            c_cits: List[EvidenceCitation] = []
            bracketed_cits = re.findall(r"\[([A-Za-z0-9_]+)\]", c_str)
            if bracketed_cits:
                default_doc = inherited_citations[0].doc_id if inherited_citations else "DOC_INLINE"
                default_page = inherited_citations[0].page_number if inherited_citations else 1
                for bc in bracketed_cits:
                    c_cits.append(EvidenceCitation(doc_id=default_doc, page_number=default_page, evidence_id=bc))
            else:
                c_cits = inherited_citations

            # Mask bracketed citations (e.g. "[EVID_01]") so citation IDs are never treated as numbers
            clause_clean = re.sub(r"\[.*?\]", "", c_str)

            # Mask date strings so calendar day/month/year integers are not parsed as measurements
            clause_clean = re.sub(
                r"(?:ngày\s+)?\d{1,2}\s*(?:tháng|[/-])\s*\d{1,2}(?:\s*(?:năm|[/-])\s*\d{4})?",
                "",
                clause_clean,
                flags=re.IGNORECASE,
            )
            clause_clean = re.sub(r"\b(19\d\d|20\d\d)\b", "", clause_clean)
            # Mask alphanumeric tokens (e.g. station codes VB2, X31, P0003, R006) without touching units like m3, m2
            clause_clean = re.sub(
                r"\b(?!(?:m3|m2|cm3|mm3)\b)[A-Za-z]+[0-9]+[A-Za-z0-9_]*\b",
                "",
                clause_clean,
                flags=re.IGNORECASE,
            )

            # Look for signed numbers with optional units
            num_matches = [
                m.group(0)
                for m in re.finditer(
                    r"([-+]?\d+(?:[,\.]\d+)?)\s*(m3/s|m³/s|triệu m3|tỷ m3|ha|m3|m³|cm|mm|m|%)?",
                    clause_clean,
                    re.IGNORECASE,
                )
                if m.group(1)
            ]
            if not num_matches:
                continue

            # Polarity check
            polarity = ClaimPolarity.AFFIRMED
            if any(neg in c_str.lower() for neg in ["không ", "khong ", "chưa ", "chua "]):
                polarity = ClaimPolarity.NEGATED

            for m_idx, raw_match in enumerate(num_matches):
                parts = raw_match.strip().split()
                val_str = parts[0]
                unit_str = parts[1] if len(parts) > 1 else default_unit

                claim_counter += 1
                claim_id = f"{qa_id}_C{claim_counter}"
                claims.append(
                    TechnicalClaim(
                        claim_id=claim_id,
                        claim_text=c_str,
                        subject=ent_name,
                        parameter=param_name,
                        value=val_str,
                        unit=unit_str,
                        temporal_scope=date_iso,
                        observation_type=local_obs,
                        polarity=polarity,
                        evidence_citations=c_cits,
                        extraction_status="CLAUSE_BOUND",
                    )
                )

    return claims



def extract_iso_date(text: str) -> Optional[str]:
    """Extract and normalize dates into ISO-8601 (yyyy-mm-dd) format."""
    if not text:
        return None
    t = text.strip()

    # Pattern: yyyy-mm-dd
    m_iso = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        return f"{y:04d}-{m:02d}-{d:02d}"

    # Pattern: ngày dd tháng mm năm yyyy or dd/mm/yyyy
    m_vn = re.search(r"(?:ngày\s+)?(\d{1,2})\s*(?:tháng|[/-])\s*(\d{1,2})\s*(?:năm|[/-])\s*(\d{4})", t, re.IGNORECASE)
    if m_vn:
        d, m, y = int(m_vn.group(1)), int(m_vn.group(2)), int(m_vn.group(3))
        return f"{y:04d}-{m:02d}-{d:02d}"

    # Pattern: dd/mm or dd tháng mm
    m_short = re.search(r"(?:ngày\s+)?(\d{1,2})\s*(?:tháng|[/-])\s*(\d{1,2})\b", t, re.IGNORECASE)
    if m_short:
        d, m = int(m_short.group(1)), int(m_short.group(2))
        return f"XXXX-{m:02d}-{d:02d}"

    return None


# =============================================================================
# CANONICAL CATALOGUE DEFINITIONS
# =============================================================================

KNOWN_STRUCTURES: Dict[str, Dict[str, Any]] = {
    "HO_HOA_BINH": {
        "canonical_name": "Hồ Hòa Bình",
        "aliases": ["hồ hòa bình", "ho hoa binh", "thủy điện hòa bình", "hòa bình"],
        "basin": "Sông Hồng",
        "type": "Reservoir",
    },
    "HO_SON_LA": {
        "canonical_name": "Hồ Sơn La",
        "aliases": ["hồ sơn la", "ho son la", "thủy điện sơn la", "sơn la"],
        "basin": "Sông Hồng",
        "type": "Reservoir",
    },
    "HO_THAC_BA": {
        "canonical_name": "Hồ Thác Bà",
        "aliases": ["hồ thác bà", "ho thac ba", "thủy điện thác bà", "thác bà"],
        "basin": "Sông Hồng",
        "type": "Reservoir",
    },
    "HO_TUYEN_QUANG": {
        "canonical_name": "Hồ Tuyên Quang",
        "aliases": ["hồ tuyên quang", "ho tuyen quang", "thủy điện tuyên quang", "tuyên quang"],
        "basin": "Sông Hồng",
        "type": "Reservoir",
    },
    "HO_LAI_CHAU": {
        "canonical_name": "Hồ Lai Châu",
        "aliases": ["hồ lai châu", "ho lai chau", "thủy điện lai châu", "lai châu"],
        "basin": "Sông Hồng",
        "type": "Reservoir",
    },
    "HO_BAN_CHAT": {
        "canonical_name": "Hồ Bản Chát",
        "aliases": ["hồ bản chát", "ho ban chat", "thủy điện bản chát", "bản chát"],
        "basin": "Sông Hồng",
        "type": "Reservoir",
    },
    "HO_HUOI_QUANG": {
        "canonical_name": "Hồ Huội Quảng",
        "aliases": ["hồ huội quảng", "ho huoi quang", "thủy điện huội quảng", "huội quảng"],
        "basin": "Sông Hồng",
        "type": "Reservoir",
    },
    "HO_TA_TRACH": {
        "canonical_name": "Hồ Tả Trạch",
        "aliases": ["hồ tả trạch", "ho ta trach", "tả trạch"],
        "basin": "Sông Hương",
        "type": "Reservoir",
    },
    "HO_BINH_DIEN": {
        "canonical_name": "Hồ Bình Điền",
        "aliases": ["hồ bình điền", "ho binh dien", "bình điền"],
        "basin": "Sông Hương",
        "type": "Reservoir",
    },
    "HO_HUONG_DIEN": {
        "canonical_name": "Hồ Hương Điền",
        "aliases": ["hồ hương điền", "ho huong dien", "hương điền"],
        "basin": "Sông Bồ",
        "type": "Reservoir",
    },
    "HO_TRI_AN": {
        "canonical_name": "Hồ Trị An",
        "aliases": ["hồ trị an", "ho tri an", "trị an"],
        "basin": "Sông Đồng Nai",
        "type": "Reservoir",
    },
    "HO_SUOI_MO": {
        "canonical_name": "Hồ Suối Mỡ",
        "aliases": ["hồ suối mỡ", "ho suoi mo", "suối mỡ"],
        "basin": "Sông Thương",
        "type": "Reservoir",
    },
    "HO_DAI_LAI": {
        "canonical_name": "Hồ Đại Lải",
        "aliases": ["hồ đại lải", "ho dai lai", "đại lải"],
        "basin": "Sông Cà Lồ",
        "type": "Reservoir",
    },
    "HO_DAP_TROI": {
        "canonical_name": "Hồ Đập Trời",
        "aliases": ["hồ đập trời", "ho dap troi", "đập trời"],
        "basin": "Sông Lục Nam",
        "type": "Reservoir",
    },
    # Monitoring Stations (SIWRP & National Network)
    "TRAM_VB2": {
        "canonical_name": "VB2",
        "aliases": ["vb2", "trạm vb2", "tram vb2"],
        "basin": "ĐBSCL",
        "type": "MonitoringStation",
    },
    "TRAM_VB3": {
        "canonical_name": "VB3",
        "aliases": ["vb3", "trạm vb3", "tram vb3"],
        "basin": "ĐBSCL",
        "type": "MonitoringStation",
    },
    "TRAM_VB4": {
        "canonical_name": "VB4",
        "aliases": ["vb4", "trạm vb4", "tram vb4"],
        "basin": "ĐBSCL",
        "type": "MonitoringStation",
    },
    "TRAM_TAN_HONG": {
        "canonical_name": "Tân Hồng",
        "aliases": ["tân hồng", "tan hong", "trạm tân hồng"],
        "basin": "ĐBSCL",
        "type": "MonitoringStation",
    },
    "TRAM_TRUONG_XUAN": {
        "canonical_name": "Trường Xuân",
        "aliases": ["trường xuân", "truong xuan", "trạm trường xuân"],
        "basin": "ĐBSCL",
        "type": "MonitoringStation",
    },
    "TRAM_TRI_TON": {
        "canonical_name": "Tri Tôn",
        "aliases": ["tri tôn", "tri ton", "trạm tri tôn"],
        "basin": "ĐBSCL",
        "type": "MonitoringStation",
    },
    "TRAM_TAN_HUNG": {
        "canonical_name": "Tân Hưng",
        "aliases": ["tân hưng", "tan hung", "trạm tân hưng"],
        "basin": "ĐBSCL",
        "type": "MonitoringStation",
    },
    "TRAM_VINH_DIEU": {
        "canonical_name": "Vĩnh Điều",
        "aliases": ["vĩnh điều", "vinh dieu", "trạm vĩnh điều"],
        "basin": "ĐBSCL",
        "type": "MonitoringStation",
    },
    "TRAM_AN_LONG": {
        "canonical_name": "An Long",
        "aliases": ["an long", "trạm an long"],
        "basin": "ĐBSCL",
        "type": "MonitoringStation",
    },
    "TRAM_BAC_TRANG": {
        "canonical_name": "Bắc Trang",
        "aliases": ["bắc trang", "bac trang", "trạm bắc trang"],
        "basin": "ĐBSCL",
        "type": "MonitoringStation",
    },
    "TRAM_HAM_GIANG": {
        "canonical_name": "Hàm Giang",
        "aliases": ["hàm giang", "ham giang", "trạm hàm giang"],
        "basin": "ĐBSCL",
        "type": "MonitoringStation",
    },
    "TRAM_TRA_VINH": {
        "canonical_name": "Trà Vinh",
        "aliases": ["trà vinh", "tra vinh", "trạm trà vinh"],
        "basin": "ĐBSCL",
        "type": "MonitoringStation",
    },
    "TRAM_XEO_RO": {
        "canonical_name": "Xẻo Rô",
        "aliases": ["xẻo rô", "xeo ro", "trạm xẻo rô"],
        "basin": "ĐBSCL",
        "type": "MonitoringStation",
    },
    "TRAM_DA_NANG": {
        "canonical_name": "Đà Nẵng",
        "aliases": ["đà nẵng", "da nang", "trạm đà nẵng"],
        "basin": "Vu Gia - Thu Bồn",
        "type": "MonitoringStation",
    },
    "CONG_XA": {
        "canonical_name": "Cống",
        "aliases": ["cống", "cong", "cống xả", "cống lấy nước", "đáy cống"],
        "basin": "Toàn quốc",
        "type": "Sluice",
    },
    "CONG_LONG_HIEP": {
        "canonical_name": "Long Hiệp",
        "aliases": ["long hiệp", "long hiep", "cống long hiệp", "trạm long hiệp"],
        "basin": "Nam Măng Thít",
        "type": "Sluice",
    },
    "CONG_BONG_BOT": {
        "canonical_name": "Bông Bót",
        "aliases": ["bông bót", "bong bot", "cống bông bót", "trạm bông bót"],
        "basin": "Nam Măng Thít",
        "type": "Sluice",
    },
}

KNOWN_PARAMETERS: Dict[str, Dict[str, Any]] = {
    "MNDBT": {
        "canonical_name": "Mực nước dâng bình thường",
        "aliases": ["mndbt", "mực nước dâng bình thường", "muc nuoc dang binh thuong", "normal pool level"],
        "dimension": UnitDimension.LENGTH,
        "default_unit": "m",
        "fact_type": FactType.DESIGN_SPECIFICATION,
    },
    "MNC": {
        "canonical_name": "Mực nước chết",
        "aliases": ["mnc", "mực nước chết", "muc nuoc chet", "dead water level"],
        "dimension": UnitDimension.LENGTH,
        "default_unit": "m",
        "fact_type": FactType.DESIGN_SPECIFICATION,
    },
    "MNLTK": {
        "canonical_name": "Mực nước lũ thiết kế",
        "aliases": ["mnltk", "mực nước lũ thiết kế", "muc nuoc lu thiet ke", "design flood level"],
        "dimension": UnitDimension.LENGTH,
        "default_unit": "m",
        "fact_type": FactType.DESIGN_SPECIFICATION,
    },
    "MNLKT": {
        "canonical_name": "Mực nước lũ kiểm tra",
        "aliases": ["mnlkt", "mực nước lũ kiểm tra", "muc nuoc lu kiem tra", "check flood level"],
        "dimension": UnitDimension.LENGTH,
        "default_unit": "m",
        "fact_type": FactType.DESIGN_SPECIFICATION,
    },
    "MNTL": {
        "canonical_name": "Mực nước trước lũ",
        "aliases": ["mntl", "mực nước trước lũ", "muc nuoc truoc lu", "mực nước cao nhất trước lũ"],
        "dimension": UnitDimension.LENGTH,
        "default_unit": "m",
        "fact_type": FactType.DESIGN_SPECIFICATION,
    },
    "MNDL": {
        "canonical_name": "Mực nước đón lũ",
        "aliases": ["mndl", "mực nước đón lũ", "muc nuoc don lu"],
        "dimension": UnitDimension.LENGTH,
        "default_unit": "m",
        "fact_type": FactType.DESIGN_SPECIFICATION,
    },
    "MUC_NUOC": {
        "canonical_name": "Mực nước",
        "aliases": ["mực nước", "muc nuoc", "cao trình", "cao trinh", "water level"],
        "dimension": UnitDimension.LENGTH,
        "default_unit": "m",
        "fact_type": FactType.OBSERVATION,
    },
    "Q_VE": {
        "canonical_name": "Lưu lượng về hồ",
        "aliases": ["lưu lượng về hồ", "luu luong ve ho", "lưu lượng đến hồ", "q về", "qve"],
        "dimension": UnitDimension.FLOW_RATE,
        "default_unit": "m3/s",
        "fact_type": FactType.OBSERVATION,
    },
    "Q_XA": {
        "canonical_name": "Lưu lượng xả",
        "aliases": ["lưu lượng xả", "luu luong xa", "q xả", "qxa", "tổng lưu lượng xả"],
        "dimension": UnitDimension.FLOW_RATE,
        "default_unit": "m3/s",
        "fact_type": FactType.OBSERVATION,
    },
    "Q_XA_MAX": {
        "canonical_name": "Lưu lượng xả lớn nhất",
        "aliases": ["lưu lượng xả lớn nhất", "luu luong xa lon nhat", "q xả max", "qxamax"],
        "dimension": UnitDimension.FLOW_RATE,
        "default_unit": "m3/s",
        "fact_type": FactType.DESIGN_SPECIFICATION,
    },
    "W_TOAN_BO": {
        "canonical_name": "Dung tích toàn bộ",
        "aliases": ["dung tích toàn bộ", "dung tich toan bo", "v toàn bộ", "total storage"],
        "dimension": UnitDimension.VOLUME,
        "default_unit": "triệu m3",
        "fact_type": FactType.DESIGN_SPECIFICATION,
    },
    "W_HUU_ICH": {
        "canonical_name": "Dung tích hữu ích",
        "aliases": ["dung tích hữu ích", "dung tich huu ich", "v hữu ích", "active storage"],
        "dimension": UnitDimension.VOLUME,
        "default_unit": "triệu m3",
        "fact_type": FactType.DESIGN_SPECIFICATION,
    },
    "W_CHET": {
        "canonical_name": "Dung tích chết",
        "aliases": ["dung tích chết", "dung tich chet", "v chết", "dead storage"],
        "dimension": UnitDimension.VOLUME,
        "default_unit": "triệu m3",
        "fact_type": FactType.DESIGN_SPECIFICATION,
    },
    "W_PHONG_LU": {
        "canonical_name": "Dung tích phòng lũ",
        "aliases": ["dung tích phòng lũ", "dung tich phong lu", "dung tích cắt lũ", "flood control volume"],
        "dimension": UnitDimension.VOLUME,
        "default_unit": "triệu m3",
        "fact_type": FactType.DESIGN_SPECIFICATION,
    },
    "W_DUNG_TICH": {
        "canonical_name": "Dung tích",
        "aliases": ["dung tích", "dung tich", "dung tích hồ", "dung tich ho", "storage", "reservoir storage"],
        "dimension": UnitDimension.VOLUME,
        "default_unit": "triệu m3",
        "fact_type": FactType.DESIGN_SPECIFICATION,
    },
    "CAO_TRINH_DAY": {
        "canonical_name": "Cao trình đáy",
        "aliases": ["cao trình đáy", "cao trinh day", "đáy cống", "cao trình đáy cống"],
        "dimension": UnitDimension.LENGTH,
        "default_unit": "m",
        "fact_type": FactType.DESIGN_SPECIFICATION,
    },
}


def resolve_canonical_entity(text: str) -> Optional[Tuple[str, str, str]]:
    """Resolve raw entity text into (entity_id, canonical_name, basin)."""
    norm = strip_accents_lower(text)
    sorted_structures = sorted(
        KNOWN_STRUCTURES.items(),
        key=lambda kv: (kv[0] == "CONG_XA", -max(len(strip_accents_lower(a)) for a in [kv[1]["canonical_name"]] + kv[1]["aliases"])),
    )
    for ent_id, meta in sorted_structures:
        canonical_norm = strip_accents_lower(meta["canonical_name"])
        if len(canonical_norm) <= 4:
            if re.search(r"\b" + re.escape(canonical_norm) + r"\b", norm):
                return ent_id, meta["canonical_name"], meta["basin"]
        elif canonical_norm in norm:
            return ent_id, meta["canonical_name"], meta["basin"]

        for alias in meta["aliases"]:
            norm_alias = strip_accents_lower(alias)
            if len(norm_alias) <= 4:
                if re.search(r"\b" + re.escape(norm_alias) + r"\b", norm):
                    return ent_id, meta["canonical_name"], meta["basin"]
            elif norm_alias in norm:
                return ent_id, meta["canonical_name"], meta["basin"]
    return None


def resolve_canonical_parameter(text: str) -> Optional[Tuple[str, str, UnitDimension, str, FactType]]:
    """Resolve raw parameter text into (parameter_id, canonical_name, dimension, default_unit, fact_type)."""
    norm = strip_accents_lower(text)
    # Check specific compound parameters first (e.g. MNDBT before MUC_NUOC)
    sorted_params = sorted(KNOWN_PARAMETERS.items(), key=lambda kv: len(kv[1]["canonical_name"]), reverse=True)
    for param_id, meta in sorted_params:
        if strip_accents_lower(meta["canonical_name"]) in norm:
            return param_id, meta["canonical_name"], meta["dimension"], meta["default_unit"], meta["fact_type"]
        for alias in meta["aliases"]:
            if strip_accents_lower(alias) in norm:
                return param_id, meta["canonical_name"], meta["dimension"], meta["default_unit"], meta["fact_type"]
    return None


# =============================================================================
# FACT EXTRACTOR ENGINE
# =============================================================================

class TypedFactExtractor:
    """Extracts standardized ObservationFact, DesignSpecificationFact, and DocumentRegulationFact from evidence."""

    @staticmethod
    def extract_facts_from_evidence_item(item: EvidenceItem) -> List[Any]:
        """Extract typed facts from a single EvidenceItem (text paragraph, table row/cell, or legal clause)."""
        facts: List[Any] = []
        raw_text = item.text or ""
        doc_id = item.doc_id
        page_num = item.page_number
        reg_id = item.region_id or item.evidence_id

        # Determine provenance
        prov = ProvenanceMetadata(
            document_id=doc_id,
            document_number=item.document_number,
            document_version=item.document_version,
            page_number=page_num,
            region_id=reg_id,
            source_content_hash=item.provenance_metadata.get("source_content_hash"),
            exact_text_snippet=raw_text[:200],
        )

        # Check if item is a structured table cell evidence
        cell_meta = item.provenance_metadata.get("cell_metadata")
        if cell_meta and isinstance(cell_meta, dict):
            row_label = str(cell_meta.get("row_label", ""))
            col_label = str(cell_meta.get("column_label", ""))
            cell_val = str(cell_meta.get("cell_value", ""))
            cell_unit = str(cell_meta.get("unit", ""))

            # Resolve entity from row or table caption
            ent_res = resolve_canonical_entity(row_label) or resolve_canonical_entity(item.source)
            param_res = resolve_canonical_parameter(col_label) or resolve_canonical_parameter(row_label)

            num_val = parse_vietnamese_number(cell_val)
            if ent_res and param_res and num_val is not None:
                ent_id, ent_name, _ = ent_res
                p_id, p_name, dim, def_u, f_type = param_res
                u = normalize_unit_string(cell_unit) or def_u

                table_prov = ProvenanceMetadata(
                    document_id=doc_id,
                    document_number=item.document_number,
                    document_version=item.document_version,
                    page_number=page_num,
                    region_id=reg_id,
                    table_id=cell_meta.get("table_id"),
                    row_idx=cell_meta.get("row_idx"),
                    col_idx=cell_meta.get("col_idx"),
                    exact_text_snippet=f"{row_label} | {col_label} | {cell_val}",
                )

                if f_type == FactType.DESIGN_SPECIFICATION:
                    facts.append(
                        DesignSpecificationFact(
                            fact_id=f"FACT_SPEC_{item.evidence_id}",
                            entity_id=ent_id,
                            canonical_entity_name=ent_name,
                            parameter_id=p_id,
                            canonical_parameter_name=p_name,
                            numeric_value=num_val,
                            raw_value_str=cell_val,
                            unit=u,
                            unit_dimension=dim,
                            provenance=table_prov,
                        )
                    )
                else:
                    facts.append(
                        ObservationFact(
                            fact_id=f"FACT_OBS_{item.evidence_id}",
                            entity_id=ent_id,
                            canonical_entity_name=ent_name,
                            parameter_id=p_id,
                            canonical_parameter_name=p_name,
                            observation_type=ObservationType.ACTUAL_OBSERVED,
                            numeric_value=num_val,
                            raw_value_str=cell_val,
                            unit=u,
                            unit_dimension=dim,
                            provenance=table_prov,
                        )
                    )
                return facts

        # Direct extraction for structured [Ô BẢNG NGUỒN] cell format
        if "[Ô BẢNG NGUỒN]" in raw_text:
            m_cell = re.search(
                r"\[Ô BẢNG NGUỒN\]\s*Thực thể:\s*(.*?);\s*Thông số:\s*(.*?);\s*Giá trị:\s*([^;.]+)(?:;\s*điều kiện/cột:\s*(.*?))?(?:\.|\n|$)",
                raw_text,
                re.IGNORECASE,
            )
            if m_cell:
                cell_ent = m_cell.group(1).strip()
                cell_param = m_cell.group(2).strip()
                cell_val = m_cell.group(3).strip()
                cell_cond = (m_cell.group(4) or "").strip()

                ent_res = resolve_canonical_entity(cell_ent)
                param_res = resolve_canonical_parameter(cell_param) or resolve_canonical_parameter(cell_cond)
                num_val = parse_vietnamese_number(cell_val)

                if ent_res and param_res and num_val is not None:
                    ent_id, ent_name, _ = ent_res
                    p_id, p_name, dim, def_u, f_type = param_res
                    u = def_u
                    m_u = re.search(r"\b(m3/s|m³/s|triệu m3|tỷ m3|ha|m3|m³|cm|mm|m|%)\b", cell_val, re.IGNORECASE)
                    if m_u:
                        u = normalize_unit_string(m_u.group(1)) or def_u

                    date_iso = extract_iso_date(cell_param) or extract_iso_date(cell_cond)
                    is_forecast = any(k in (cell_param + " " + cell_cond).lower() for k in ["dự báo", "du bao", "kỳ dự báo"])
                    obs_type = ObservationType.FORECAST_ESTIMATE if is_forecast else ObservationType.ACTUAL_OBSERVED

                    cell_prov = ProvenanceMetadata(
                        document_id=doc_id,
                        document_number=item.document_number,
                        page_number=page_num,
                        region_id=item.evidence_id,
                        exact_text_snippet=raw_text[:200],
                    )

                    if f_type == FactType.DESIGN_SPECIFICATION:
                        facts.append(
                            DesignSpecificationFact(
                                fact_id=f"FACT_SPEC_{item.evidence_id}",
                                entity_id=ent_id,
                                canonical_entity_name=ent_name,
                                parameter_id=p_id,
                                canonical_parameter_name=p_name,
                                numeric_value=num_val,
                                raw_value_str=cell_val,
                                unit=u,
                                unit_dimension=dim,
                                provenance=cell_prov,
                            )
                        )
                    else:
                        facts.append(
                            ObservationFact(
                                fact_id=f"FACT_OBS_{item.evidence_id}",
                                entity_id=ent_id,
                                canonical_entity_name=ent_name,
                                parameter_id=p_id,
                                canonical_parameter_name=p_name,
                                observation_type=obs_type,
                                numeric_value=num_val,
                                raw_value_str=cell_val,
                                unit=u,
                                unit_dimension=dim,
                                observation_time=date_iso,
                                provenance=cell_prov,
                            )
                        )
                    return facts

        # Pipe-delimited table grid extraction via TableAwareEvidenceResolver
        if ("|" in raw_text and "\n" in raw_text) or item.content_type in ["table", "TABLE_REGION", "table_cell"]:
            from viirr_retrieval.table_aware import TableAwareEvidenceResolver
            tbl_facts = TableAwareEvidenceResolver.parse_table_unit({
                "raw_text": raw_text,
                "index_text": raw_text,
                "evidence_id": item.evidence_id,
                "table_id": getattr(item, "table_id", item.evidence_id),
                "doc_id": doc_id,
                "page_number": page_num,
                "page_id": item.page_id,
            })
            for tf in tbl_facts:
                ent_res = resolve_canonical_entity(tf.entity)
                param_res = resolve_canonical_parameter(tf.parameter)
                if ent_res and param_res and tf.numeric_value is not None:
                    ent_id, ent_name, _ = ent_res
                    p_id, p_name, dim, def_u, f_type = param_res
                    u = normalize_unit_string(tf.unit) or def_u
                    date_iso = extract_iso_date(tf.row_text) or extract_iso_date(tf.condition or "") or extract_iso_date(tf.parameter or "")

                    cell_prov = ProvenanceMetadata(
                        document_id=doc_id,
                        document_number=item.document_number,
                        page_number=page_num,
                        region_id=tf.evidence_id,
                        table_id=tf.table_id,
                        exact_text_snippet=tf.row_text[:200],
                    )

                    if f_type == FactType.DESIGN_SPECIFICATION:
                        facts.append(
                            DesignSpecificationFact(
                                fact_id=f"FACT_SPEC_{tf.evidence_id}",
                                entity_id=ent_id,
                                canonical_entity_name=ent_name,
                                parameter_id=p_id,
                                canonical_parameter_name=p_name,
                                numeric_value=tf.numeric_value,
                                raw_value_str=tf.raw_value,
                                unit=u,
                                unit_dimension=dim,
                                provenance=cell_prov,
                            )
                        )
                    else:
                        is_forecast = any(k in (tf.header_text + " " + tf.row_text + " " + (tf.condition or "") + " " + (tf.parameter or "")).lower() for k in ["dự báo", "du bao", "kỳ dự báo"])
                        obs_type = ObservationType.FORECAST_ESTIMATE if is_forecast else ObservationType.ACTUAL_OBSERVED
                        facts.append(
                            ObservationFact(
                                fact_id=f"FACT_OBS_{tf.evidence_id}",
                                entity_id=ent_id,
                                canonical_entity_name=ent_name,
                                parameter_id=p_id,
                                canonical_parameter_name=p_name,
                                observation_type=obs_type,
                                numeric_value=tf.numeric_value,
                                raw_value_str=tf.raw_value,
                                unit=u,
                                unit_dimension=dim,
                                observation_time=date_iso,
                                provenance=cell_prov,
                            )
                        )
            if facts:
                return facts

        # Otherwise: Text or Legal clause extraction
        # Segment raw text by semicolon, newline, or sentence period for multi-entity binding
        segments = [s.strip() for s in re.split(r"[\n;]+|(?<=\S)\.\s+", raw_text) if s.strip()]
        if not segments:
            segments = [raw_text]

        last_known_param = resolve_canonical_parameter(raw_text)
        last_known_ent = resolve_canonical_entity(raw_text)

        for seg_idx, seg in enumerate(segments):
            ent_res = resolve_canonical_entity(seg) or last_known_ent
            param_res = resolve_canonical_parameter(seg) or last_known_param
            date_iso = extract_iso_date(seg)

            if ent_res:
                last_known_ent = ent_res
            if param_res:
                last_known_param = param_res

            # Look for signed numbers with attached units in this segment
            num_patterns = re.findall(
                r"([-+−]?\d+(?:[,\.]\d+)?)\s*(m3/s|m³/s|triệu m3|tỷ m3|ha|m3|m³|cm|mm|m|%)\b",
                seg,
                re.IGNORECASE,
            )

            if ent_res and param_res:
                ent_id, ent_name, _ = ent_res
                p_id, p_name, dim, def_u, f_type = param_res

                for raw_n, raw_u in num_patterns:
                    parsed_n = parse_vietnamese_number(raw_n)
                    if parsed_n is not None:
                        norm_u = normalize_unit_string(raw_u) or def_u
                        u_dim = get_unit_dimension(norm_u)

                        if u_dim == dim or u_dim == UnitDimension.UNKNOWN:
                            if f_type == FactType.DESIGN_SPECIFICATION:
                                facts.append(
                                    DesignSpecificationFact(
                                        fact_id=f"FACT_SPEC_{item.evidence_id}_{ent_id}_{p_id}_{seg_idx}",
                                        entity_id=ent_id,
                                        canonical_entity_name=ent_name,
                                        parameter_id=p_id,
                                        canonical_parameter_name=p_name,
                                        numeric_value=parsed_n,
                                        raw_value_str=raw_n,
                                        unit=norm_u,
                                        unit_dimension=dim,
                                        document_authority=item.document_number or "",
                                        provenance=prov,
                                    )
                                )
                            else:
                                is_forecast = any(k in seg.lower() for k in ["dự báo", "du bao", "kỳ dự báo"])
                                obs_type = (
                                    ObservationType.FORECAST_ESTIMATE
                                    if is_forecast
                                    else ObservationType.ACTUAL_OBSERVED
                                )
                                facts.append(
                                    ObservationFact(
                                        fact_id=f"FACT_OBS_{item.evidence_id}_{ent_id}_{p_id}_{seg_idx}",
                                        entity_id=ent_id,
                                        canonical_entity_name=ent_name,
                                        parameter_id=p_id,
                                        canonical_parameter_name=p_name,
                                        observation_type=obs_type,
                                        numeric_value=parsed_n,
                                        raw_value_str=raw_n,
                                        unit=norm_u,
                                        unit_dimension=dim,
                                        observation_time=date_iso,
                                        provenance=prov,
                                    )
                                )

        # Check for legal scope / decree regulation (e.g., QĐ 740, QĐ 922)
        if any(kw in raw_text.lower() for kw in ["quyết định số 740", "quyết định 740", "qd 740", "740/qđ-ttg"]):
            facts.append(
                DocumentRegulationFact(
                    fact_id=f"FACT_REG_{item.evidence_id}_740",
                    document_id=doc_id,
                    document_number="740/QĐ-TTg",
                    article="Điều 1",
                    jurisdiction="Thủ tướng Chính phủ",
                    action="ban_hanh_quy_trinh",
                    polarity="AFFIRMED",
                    effective_date="2019-06-17",
                    applicable_scope=["HO_SON_LA", "HO_HOA_BINH", "HO_THAC_BA", "HO_TUYEN_QUANG", "HO_LAI_CHAU", "HO_BAN_CHAT", "HO_HUOI_QUANG"],
                    provenance=prov,
                )
            )

        if any(kw in raw_text.lower() for kw in ["quyết định số 922", "quyết định 922", "qd 922", "922/qđ-ttg"]):
            facts.append(
                DocumentRegulationFact(
                    fact_id=f"FACT_REG_{item.evidence_id}_922",
                    document_id=doc_id,
                    document_number="922/QĐ-TTg",
                    article="Điều 1",
                    jurisdiction="Thủ tướng Chính phủ",
                    action="sua_doi_bo_sung",
                    polarity="AFFIRMED",
                    effective_date="2025-05-14",
                    applicable_scope=["HO_SON_LA", "HO_HOA_BINH", "HO_THAC_BA", "HO_TUYEN_QUANG", "HO_LAI_CHAU", "HO_BAN_CHAT", "HO_HUOI_QUANG"],
                    amends_document_id="740/QĐ-TTg",
                    provenance=prov,
                )
            )

        return facts
