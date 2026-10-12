import re

GENERIC_ENTITIES = {
    "hồ", "trạm", "sông", "kênh", "đập", "cống", "công trình",
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
    "tt", "stt", "tổng", "cộng", "tbnn", "trung bình", "max", "min",
    "t&ng", "tổng cộng", "tbng c9ng, tb", "tan2 con2", "tfing"
}

DATE_PATTERNS = [
    r'^\d{1,2}/\d{1,2}$',
    r'^\d{1,2}/\d{1,2}/\d{4}$',
    r'^\d{4}-\d{2}-\d{2}$',
    r'^\d{4}$',
    r'^(?:ngày|tháng|năm)\s*\d+',
    r'^\d{1,2}-\d{1,2}$',
    r'^\d{1,2}/\d{1,2}\s*[-–]\s*\d{1,2}/\d{1,2}'
]

GARBLED_CHARS_PAT = re.compile(r'[~^\\;`|]|\b(?:tir|di~n|ho:;ich|san xufrt|to~rn|d~n|d1;1·|dBn|vlj|cimg)\b', re.IGNORECASE)

DOMAIN_METRICS = ["độ mặn", "lượng mưa", "mực nước", "lưu lượng", "dung tích", "diện tích", "nhu cầu", "hmax", "ph", "do", "tọa độ"]

class TableSemanticValidatorV24:
    """
    V2.4 Strict Table and OCR Validator.
    Blocks corrupted OCR, invalid entities, date-as-metric, and untraceable tables.
    Returns: PASS | FAIL | SKIP_NOT_APPLICABLE | UNCERTAIN
    """
    def __init__(self):
        pass

    def is_date_like(self, text):
        if not text:
            return False
        s = str(text).strip()
        for pat in DATE_PATTERNS:
            if re.match(pat, s, re.I):
                return True
        if s.lower() in ["ngày dự báo", "ngày thực đo", "ngày"]:
            return True
        return False

    def is_numeric_sequence(self, text):
        if not text:
            return False
        s = str(text).strip()
        return bool(re.match(r'^[\d\s.,\-]+$', s) and len(s) > 1 and ' ' in s)

    def is_roman_numeral(self, text):
        if not text:
            return False
        s = str(text).strip().lower()
        return bool(re.match(r'^[ivxlcdm]+$', s))

    def is_garbled_ocr(self, text):
        if not text:
            return False
        s = str(text).strip()
        return bool(GARBLED_CHARS_PAT.search(s))

    def is_invalid_entity(self, text):
        if not text:
            return True, "EMPTY_ENTITY"
        s = str(text).strip()
        if len(s) < 2:
            return True, "TOO_SHORT_ENTITY"
        if self.is_date_like(s):
            return True, f"DATE_AS_ENTITY: '{s}'"
        if self.is_numeric_sequence(s):
            return True, f"NUMERIC_SEQUENCE_AS_ENTITY: '{s}'"
        if self.is_roman_numeral(s):
            return True, f"ROMAN_NUMERAL_AS_ENTITY: '{s}'"
        if s.lower() in GENERIC_ENTITIES:
            return True, f"GENERIC_ENTITY: '{s}'"
        # Check if entity is just a metric e.g. "Mực nước (m)"
        if s.lower().startswith("mực nước (m)"):
            return True, f"METRIC_AS_ENTITY: '{s}'"
        if self.is_garbled_ocr(s):
            return True, f"GARBLED_OCR_ENTITY: '{s}'"
        if re.match(r'^(?:hồ|trạm|sông|kênh)\s+[0-9ivx]+$', s, re.I):
            return True, f"GENERIC_NUMBERED_ENTITY: '{s}'"
        return False, None

    def is_invalid_metric(self, text):
        if not text:
            return True, "EMPTY_METRIC"
        s = str(text).strip()
        if len(s) < 2:
            return True, "TOO_SHORT_METRIC"
        if self.is_date_like(s):
            # If contains domain metric keywords, it is a qualified metric (e.g. Độ mặn Max ...)
            if not any(dm in s.lower() for dm in DOMAIN_METRICS):
                return True, f"DATE_AS_METRIC: '{s}'"
        if self.is_numeric_sequence(s):
            return True, f"NUMERIC_SEQUENCE_AS_METRIC: '{s}'"
        if s.lower() in GENERIC_ENTITIES:
            return True, f"GENERIC_METRIC_HEADER: '{s}'"
        if self.is_garbled_ocr(s):
            return True, f"GARBLED_OCR_METRIC: '{s}'"
        return False, None

    def validate_table_qa(self, qa_record):
        gold_evidence = qa_record.get("gold_evidence", [])
        table_evs = [e for e in gold_evidence if e.get("region_type") == "table"]

        if not table_evs:
            return {
                "status": "SKIP_NOT_APPLICABLE",
                "reasons": []
            }

        reasons = []
        for ev in table_evs:
            t_id = ev.get("table_id")
            p_no = ev.get("page_number")
            prov = ev.get("table_cell_provenance")
            if isinstance(prov, str):
                try:
                    prov = eval(prov)
                except Exception:
                    prov = None

            if not t_id:
                reasons.append("MISSING_TABLE_ID")
            if not p_no:
                reasons.append("MISSING_PAGE_ID")
            if not prov:
                reasons.append("MISSING_CELL_PROVENANCE")
                continue

            row_label = str(prov.get("row_label", "")).strip()
            col_label = str(prov.get("column_label", "")).strip()
            raw_cell = str(prov.get("raw_cell", "")).strip()

            ent_invalid, ent_reason = self.is_invalid_entity(row_label)
            if ent_invalid:
                reasons.append(ent_reason)

            met_invalid, met_reason = self.is_invalid_metric(col_label)
            if met_invalid:
                reasons.append(met_reason)

            if not raw_cell or raw_cell in ["", "-", "--", "---", "x", "X", "N/A", "null", "None"]:
                reasons.append(f"EMPTY_CELL_VALUE: '{raw_cell}'")

            ans = qa_record.get("answer", "")
            if raw_cell and raw_cell not in ans:
                clean_raw = re.sub(r'[^\d.,]', '', raw_cell)
                clean_ans = re.sub(r'[^\d.,]', '', ans)
                if not (clean_raw and clean_raw in clean_ans):
                    reasons.append(f"VALUE_MISALIGNMENT: cell '{raw_cell}' not found in answer")

        status = "FAIL" if reasons else "PASS"
        return {
            "status": status,
            "reasons": reasons
        }
