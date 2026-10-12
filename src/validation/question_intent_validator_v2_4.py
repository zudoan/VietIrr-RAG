import re

# Minimal supported intents
INTENTS = [
    "VALUE_LOOKUP",
    "COMPARISON",
    "TEMPORAL_STATUS",
    "FORECAST",
    "CAUSE",
    "EXPLANATION",
    "RECOMMENDATION",
    "OPERATIONAL_RULE",
    "OPERATIONAL_ACTION",
    "THRESHOLD",
    "REGULATION_LOOKUP",
    "MULTI_COMPONENT"
]

# Allowed evidence roles
ALLOWED_ROLES = [
    "VALUE",
    "REFERENCE_VALUE",
    "STATUS",
    "FORECAST",
    "CAUSE",
    "EXPLANATION",
    "RECOMMENDATION",
    "OPERATIONAL_RULE",
    "OPERATIONAL_ACTION",
    "THRESHOLD",
    "REGULATION",
    "TEMPORAL_CONTEXT",
    "UNKNOWN"
]

# Intent ↔ Role compatibility matrix
INTENT_ROLE_COMPAT = {
    "VALUE_LOOKUP": {"VALUE", "REFERENCE_VALUE", "THRESHOLD"},
    "COMPARISON": {"VALUE", "REFERENCE_VALUE", "STATUS"},
    "TEMPORAL_STATUS": {"STATUS", "TEMPORAL_CONTEXT", "VALUE"},
    "FORECAST": {"FORECAST"},
    "CAUSE": {"CAUSE", "EXPLANATION"},
    "EXPLANATION": {"EXPLANATION", "CAUSE", "STATUS"},
    "RECOMMENDATION": {"RECOMMENDATION"},
    "OPERATIONAL_RULE": {"OPERATIONAL_RULE", "REGULATION"},
    "OPERATIONAL_ACTION": {"OPERATIONAL_ACTION", "OPERATIONAL_RULE"},
    "THRESHOLD": {"THRESHOLD", "VALUE"},
    "REGULATION_LOOKUP": {"REGULATION", "OPERATIONAL_RULE"},
}

# Strict gate: words indicating operational directives/solutions
DIRECTIVE_KEYWORDS = [
    "chỉ đạo", "yêu cầu vận hành", "giải pháp", "biện pháp", 
    "kiến nghị", "định hướng", "quy định vận hành", "ứng phó kỹ thuật"
]

# Words indicating forecasts
FORECAST_KEYWORDS = [
    "dự báo", "dự kiến", "triển vọng", "khả năng mưa", "có thể sẽ có mưa", "xu thế"
]

class QuestionIntentValidatorV24:
    def __init__(self):
        pass

    def clean_question_body(self, question_text):
        """
        Strip document title enclosed in single or double quotes to avoid
        false positives from the title name itself (e.g., 'Bản tin dự báo...').
        """
        cleaned = re.sub(r"['\"][^'\"]*['\"]", "", question_text)
        return cleaned.strip()

    def extract_intent(self, question_text):
        """
        Extract question intent from actual wording of question body.
        """
        q_body = self.clean_question_body(question_text).lower()
        q_full = question_text.lower()
        intents = []

        # Check for multi-clause / compound questions
        has_numbered_clauses = bool(re.search(r'\([1-4]\)', q_full))
        has_compound = any(w in q_body for w in ["kèm theo", "đồng thời", "và nội dung", "với giải pháp", "cùng nội dung"])
        
        # Check specific intent types
        if any(w in q_body for w in ["so sánh", "chênh lệch", "cao hơn", "thấp hơn", "tăng hay giảm", "so với cùng kỳ"]):
            intents.append("COMPARISON")
        
        if any(w in q_body for w in ["nguyên nhân", "do đâu", "tại sao", "lý do vì sao"]):
            intents.append("CAUSE")

        if any(w in q_body for w in ["chỉ đạo", "yêu cầu vận hành", "giải pháp", "biện pháp", "phương án", "nhiệm vụ", "ứng phó"]):
            intents.append("OPERATIONAL_ACTION")

        if any(w in q_body for w in ["quy trình vận hành", "quy định vận hành", "quy định", "tiêu chuẩn", "quy chuẩn", "nghị định", "thông tư", "quyết định"]):
            if any(w in q_body for w in ["quy trình", "nguyên tắc", "yêu cầu"]):
                intents.append("OPERATIONAL_RULE")
            else:
                intents.append("REGULATION_LOOKUP")

        if any(w in q_body for w in ["kiến nghị", "đề xuất", "khuyến cáo"]):
            intents.append("RECOMMENDATION")

        if any(w in q_body for w in ["ngưỡng", "báo động", "giới hạn", "cao trình thiết kế"]):
            intents.append("THRESHOLD")

        if any(w in q_body for w in ["dự báo là gì", "dự báo như thế nào", "dự báo đạt mức nào", "dự kiến đạt", "khả năng diễn biến"]):
            intents.append("FORECAST")

        if any(w in q_body for w in ["diễn biến", "hiện trạng", "tình hình", "trạng thái", "xu thế"]):
            intents.append("TEMPORAL_STATUS")

        if any(w in q_body for w in ["giá trị", "bao nhiêu", "đạt mức nào", "mức nào", "chỉ số", "thông số", "đạt giá trị", "mực nước", "lưu lượng", "lượng mưa", "dung tích", "độ mặn"]):
            intents.append("VALUE_LOOKUP")

        # Only classify as EXPLANATION if asking to explain/analyze, not just table column name "giá trị Đánh giá ... đạt mức nào"
        if any(w in q_body for w in ["hãy giải thích", "giải thích vì sao", "hãy phân tích", "phân tích nguyên nhân"]):
            intents.append("EXPLANATION")

        if has_numbered_clauses or (has_compound and len(intents) >= 2):
            intents.insert(0, "MULTI_COMPONENT")

        if not intents:
            intents.append("VALUE_LOOKUP")

        return intents

    def extract_evidence_role(self, evidence_item):
        """
        Extract role from evidence source semantics.
        Allowed roles: VALUE, REFERENCE_VALUE, STATUS, FORECAST, CAUSE, EXPLANATION,
        RECOMMENDATION, OPERATIONAL_RULE, OPERATIONAL_ACTION, THRESHOLD, REGULATION,
        TEMPORAL_CONTEXT, UNKNOWN.
        """
        exact = evidence_item.get("exact_content", "").strip()
        reg_type = evidence_item.get("region_type", "")
        cell_prov = evidence_item.get("table_cell_provenance")
        declared_role = evidence_item.get("role", "")

        # 1. Table evidence
        if reg_type == "table" or cell_prov:
            exact_lower = exact.lower()
            if "qcvn" in exact_lower or "ngưỡng" in exact_lower or "giới hạn" in exact_lower:
                return "THRESHOLD"
            if "tbnn" in exact_lower or "cùng kỳ" in exact_lower or "thiết kế" in exact_lower:
                return "REFERENCE_VALUE"
            return "VALUE"

        # 2. Text evidence
        text_lower = exact.lower()

        # Check for operational action / directive
        if any(w in text_lower for w in ["chỉ đạo", "yêu cầu các đơn vị", "thực hiện phương án", "triển khai biện pháp", "cần thực hiện"]):
            return "OPERATIONAL_ACTION"

        # Check for recommendations
        if any(w in text_lower for w in ["khuyến cáo", "đề nghị", "kiến nghị"]):
            return "RECOMMENDATION"

        # Check for regulations / operational rules
        if any(w in text_lower for w in ["quy định", "quy trình vận hành", "theo quy chuẩn", "qcvn", "nghiêm cấm"]):
            return "REGULATION"

        # Check for forecast
        if any(w in text_lower for w in ["dự báo", "dự kiến", "có thể sẽ có mưa", "lượng mưa từ", "xu thế giảm", "xu thế tăng", "khả năng"]):
            return "FORECAST"

        # Check for status / current situation
        if any(w in text_lower for w in ["hiện tại", "hiện trạng", "tính đến ngày", "thời điểm hiện tại", "diễn biến"]):
            return "STATUS"

        # Check for cause / explanation
        if any(w in text_lower for w in ["do ảnh hưởng", "nguyên nhân", "bởi vì"]):
            return "CAUSE"

        if len(text_lower) > 30:
            return "EXPLANATION"

        return "UNKNOWN"

    def check_alignment(self, question, answer, gold_evidence):
        """
        Strict alignment check:
        Question asks X
        Answer provides X
        Evidence explicitly supports X
        """
        reasons = []
        q_body = self.clean_question_body(question).lower()
        a_lower = answer.lower()
        intents = self.extract_intent(question)

        # 1. Known bad pattern: Forecast vs Directive
        asks_directive = any(kw in q_body for kw in DIRECTIVE_KEYWORDS)
        
        evidence_roles = [self.extract_evidence_role(ev) for ev in gold_evidence]
        has_real_directive_ev = any(r in {"OPERATIONAL_ACTION", "OPERATIONAL_RULE", "REGULATION", "RECOMMENDATION"} for r in evidence_roles)
        all_ev_are_forecast_or_value = all(r in {"FORECAST", "STATUS", "VALUE", "REFERENCE_VALUE", "UNKNOWN"} for r in evidence_roles)

        if asks_directive and all_ev_are_forecast_or_value:
            reasons.append("QUESTION_INTENT_MISMATCH: asks directive/solution but evidence only has forecast/value")

        # 2. Check for each intent if compatible evidence role exists
        for it in intents:
            if it == "MULTI_COMPONENT":
                continue
            allowed_roles = INTENT_ROLE_COMPAT.get(it, set())
            if not allowed_roles:
                continue
            matched = any(r in allowed_roles for r in evidence_roles)
            if not matched:
                reasons.append(f"ROLE_MISMATCH: intent '{it}' has no compatible evidence role in {evidence_roles}")

        # 3. Check question asking for numbers vs answer & evidence overlap
        ans_numbers = set(re.findall(r'\d+(?:[.,]\d+)?', a_lower))
        ev_text = " ".join(ev.get("exact_content", "") for ev in gold_evidence).lower()
        ev_numbers = set(re.findall(r'\d+(?:[.,]\d+)?', ev_text))

        if "VALUE_LOOKUP" in intents and ans_numbers:
            overlap = ans_numbers & ev_numbers
            if not overlap:
                reasons.append("ANSWER_NOT_DERIVABLE: numerical values in answer not found in evidence")

        # 4. Empty / garbage evidence
        for ev in gold_evidence:
            txt = ev.get("exact_content", "").strip()
            if len(txt) < 3 or txt in ["-", "--", "x", "X", "N/A"]:
                reasons.append(f"OCR_CORRUPTION: empty or garbage evidence in {ev.get('evidence_id')}")

        status = "PASS" if not reasons else "REJECT"
        return {
            "status": status,
            "intents": intents,
            "evidence_roles": evidence_roles,
            "reasons": reasons
        }
