from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


REFUSAL_TEXT = "Không đủ bằng chứng trong ngữ cảnh được cung cấp để trả lời đáng tin cậy."


@dataclass(frozen=True)
class Evidence:
    rank: int
    evidence_id: str
    doc_id: str
    page_id: str
    page_number: int
    unit_type: str
    score: float
    text: str
    source: str
    truncated: bool = False
    context_group: str = ""
    context_role: str = ""
    doc_title: str = ""

    def citation_key(self) -> tuple[str, int, str]:
        return self.doc_id, self.page_number, self.evidence_id

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContextBuild:
    text: str
    evidence: list[Evidence]
    estimated_tokens: int
    budget_tokens: int
    truncated: bool
    omitted_evidence_count: int


@dataclass(frozen=True)
class GenerationResult:
    answer: str
    citations: list[dict[str, Any]]
    abstained: bool
    abstention_reason: str
    evidence_supported: bool
    parse_error: str
    raw_response: str


SYSTEM_PROMPT = """Bạn là trợ lý tra cứu tài liệu thủy lợi Việt Nam.
Trả lời bằng tiếng Việt tự nhiên, ngắn gọn, mạch lạc và đi thẳng vào câu hỏi.
Không trộn dự báo với quan trắc; không đổi thời điểm, phiên bản pháp lý hoặc đơn vị đo.
Với mỗi số liệu kỹ thuật, luôn nêu rõ đối tượng/công trình, mốc thời gian và đơn vị đo.
Tránh các cụm từ máy móc như 'Theo E1...', 'Căn cứ theo tài liệu cung cấp...'.
Với mọi khẳng định dựa trên EVIDENCE, chỉ dùng nội dung được cung cấp và trích đúng doc_id, page_number, evidence_id hỗ trợ trực tiếp.
Không chép nguyên bảng OCR vào câu trả lời. Nếu EVIDENCE có nhưng không đủ để kết luận, giải thích ngắn gọn phần có thể xác nhận và phần chưa thể xác nhận, đặt abstained=true. Nếu câu hỏi mơ hồ hoặc chưa thành câu hỏi hoàn chỉnh, lịch sự hướng dẫn người dùng làm rõ nội dung cần tra cứu.
Nếu EVIDENCE trống, đây là baseline LLM-only: citations=[] và evidence_supported=false. Không bịa nguồn hay tạo citation giả.

Chỉ trả về một JSON object hợp lệ với đúng các khóa:
answer (string), citations (array object gồm doc_id, page_number, evidence_id),
abstained (boolean), abstention_reason (string), evidence_supported (boolean)."""
SYSTEM_PROMPT += (
    "\nTrả lời từ 1 đến 3 câu hoàn chỉnh. Nếu EVIDENCE không trống và câu hỏi có đủ bằng chứng, hãy đưa các citation thực sự chứng minh câu trả lời; không liệt kê citation dư thừa."
)


def estimate_tokens(text: str) -> int:
    """Conservative model-independent estimate for Vietnamese UTF-8 text."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 2))


def _clean_table_text(text: str) -> str:
    if "|" not in text:
        return text
    lines = text.splitlines()
    cleaned: list[str] = []
    for line in lines:
        line_s = line.strip()
        if not line_s:
            continue
        if "|" in line_s:
            cells = [" ".join(c.split()) for c in line_s.split("|")]
            cells = ["" if c.lower() == "none" else c for c in cells]
            cleaned.append(" | ".join(cells))
        else:
            cleaned.append(" ".join(line_s.split()))
    return "\n".join(cleaned)


def _format_evidence(item: Evidence, text: str | None = None) -> str:
    body = item.text if text is None else text
    structure = ""
    if item.context_group:
        structure = f" | context_group={item.context_group} | context_role={item.context_role or 'context'}"
    if item.context_role == "legal_condition":
        markers = sorted(_condition_markers(body))
        if markers:
            structure += f" | condition_markers={','.join(markers)}"
    title_part = f' | doc_title="{item.doc_title}"' if item.doc_title else ""
    return (
        f"[E{item.rank}] doc_id={item.doc_id}{title_part} | page_number={item.page_number} | "
        f"page_id={item.page_id} | evidence_id={item.evidence_id} | "
        f"unit_type={item.unit_type}{structure}\n{_clean_table_text(body.strip())}"
    )


def build_context(evidence: Iterable[Evidence], budget_tokens: int = 5000) -> ContextBuild:
    if budget_tokens <= 0:
        raise ValueError("budget_tokens must be positive")
    selected: list[Evidence] = []
    blocks: list[str] = []
    used = 0
    omitted = 0
    was_truncated = False
    seen_ids: set[str] = set()
    items = list(evidence)
    for index, item in enumerate(items):
        normalized_text = " ".join(item.text.split())
        if not normalized_text or item.evidence_id in seen_ids:
            omitted += 1
            continue
        seen_ids.add(item.evidence_id)
        header = _format_evidence(item, "")
        header_tokens = estimate_tokens(header)
        remaining = budget_tokens - used - header_tokens
        if remaining <= 0:
            omitted += len(items) - index
            break
        body_tokens = estimate_tokens(normalized_text)
        if body_tokens > remaining:
            max_chars = max(0, remaining * 2)
            normalized_text = normalized_text[:max_chars].rstrip()
            item = Evidence(**{**item.to_dict(), "text": normalized_text, "truncated": True})
            was_truncated = True
        block = _format_evidence(item)
        block_tokens = estimate_tokens(block)
        if used + block_tokens > budget_tokens:
            omitted += len(items) - index
            break
        selected.append(item)
        blocks.append(block)
        used += block_tokens
        if item.truncated:
            omitted += len(items) - index - 1
            break
    return ContextBuild(
        text="\n\n".join(blocks),
        evidence=selected,
        estimated_tokens=used,
        budget_tokens=budget_tokens,
        truncated=was_truncated or omitted > 0,
        omitted_evidence_count=omitted,
    )


def _evidence_block_number(evidence_id: str) -> int:
    match = re.search(r"_B(\d+)$", evidence_id)
    return int(match.group(1)) if match else 10**9


def _looks_tabular(text: str, unit_type: str) -> bool:
    folded = _ascii_fold(text)
    numeric_count = len(re.findall(r"(?<!\w)\d+(?:[.,]\d+)?", folded))
    return (
        unit_type.upper() in {"TABLE", "TABLE_ROW", "TABLE_REGION"}
        or "bang " in f"{folded} "
        or numeric_count >= 3
        or bool(re.search(r"\b(?:mt|bhh|ox|dl)\d+\b", folded))
        or any(unit in folded for unit in ("mg/l", "mpn/", "muc nuoc ho (m)", "don vi"))
    )


def _looks_legal(text: str) -> bool:
    folded = _ascii_fold(text)
    legal_terms = (
        "dieu ", "khoan ", "diem ", "quyet dinh", "nghi dinh", "thong tu",
        "qd ", "quy dinh", "truong hop", "tham quyen", "chu tich uy ban",
    )
    condition_terms = (
        "duoi ", "tu ", "tro len", "khong vuot", "khong duoc", "tru truong hop",
        "neu ", "hoac bi chet", "khong", "%",
    )
    return any(term in folded for term in legal_terms) and any(
        term in folded for term in condition_terms
    )


def _structure_role(item: Evidence) -> str:
    folded = _ascii_fold(item.text)
    if "bang " in f"{folded} ":
        return "table_caption"
    if any(term in folded for term in ("don vi", "mg/l", "mpn/", "tt tram", "tt kh vi tri")):
        return "table_header_or_unit"
    if re.search(r"\b(?:mt|bhh|ox|dl)\d+\b", folded):
        return "table_row"
    if _looks_legal(item.text):
        return "legal_condition"
    return "supporting_context"


def select_context_evidence(
    question: str,
    evidence: Iterable[Evidence],
    max_anchors: int = 16,
) -> list[Evidence]:
    """Select context anchors by retrieval rank and question coverage.

    This does not change B3 retrieval. It removes the former per-page quota so
    complementary rows or legal conditions on one page can survive together.
    """
    items = list(evidence)
    if max_anchors <= 0:
        return []
    question_tokens = _content_tokens(question)
    question_numbers = _numbers(question)

    def priority(item: Evidence) -> tuple[float, int, str]:
        item_tokens = _content_tokens(item.text)
        token_overlap = len(question_tokens & item_tokens) / max(1, len(question_tokens))
        number_overlap = len(question_numbers & _numbers(item.text)) / max(1, len(question_numbers))
        structure_bonus = 0.08 if _looks_tabular(item.text, item.unit_type) or _looks_legal(item.text) else 0.0
        value = (1.0 / (item.rank + 3)) + (0.9 * token_overlap) + (0.25 * number_overlap) + structure_bonus
        return value, -item.rank, item.evidence_id

    seeds = items[: min(6, max_anchors)]
    selected_ids = {item.evidence_id for item in seeds}
    ranked = sorted(
        (item for item in items if item.evidence_id not in selected_ids),
        key=priority,
        reverse=True,
    )
    selected = seeds + ranked[: max(0, max_anchors - len(seeds))]
    selected.sort(key=priority, reverse=True)
    return [
        Evidence(**{**item.to_dict(), "rank": rank})
        for rank, item in enumerate(selected, 1)
    ]


def expand_grounded_evidence(
    evidence: Iterable[Evidence],
    page_evidence: Iterable[Evidence],
    question: str,
    table_scan: int = 16,
    table_after: int = 3,
    legal_radius: int = 2,
) -> list[Evidence]:
    """Bundle table structure and complete legal conditions around anchors."""
    selected = list(evidence)
    selected_by_id = {item.evidence_id: item for item in selected}
    document_items: dict[str, list[Evidence]] = {}
    page_items: dict[str, list[Evidence]] = {}
    for item in page_evidence:
        document_items.setdefault(item.doc_id, []).append(item)
        page_items.setdefault(item.page_id, []).append(item)
    ordering = lambda item: (item.page_number, _evidence_block_number(item.evidence_id), item.evidence_id)
    for items in document_items.values():
        items.sort(key=ordering)
    for items in page_items.values():
        items.sort(key=ordering)

    output: list[Evidence] = []
    seen: set[str] = set()

    def append(item: Evidence, group: str, role: str | None = None) -> None:
        if item.evidence_id in seen:
            return
        seen.add(item.evidence_id)
        source = selected_by_id.get(item.evidence_id, item)
        output.append(
            Evidence(
                **{
                    **source.to_dict(),
                    "source": source.source if item.evidence_id in selected_by_id else "structured_context_neighbor",
                    "context_group": group,
                    "context_role": role or _structure_role(item),
                }
            )
        )

    for anchor in selected:
        if _looks_legal(anchor.text) or _looks_legal(question):
            items = document_items.get(anchor.doc_id, [])
            positions = {item.evidence_id: index for index, item in enumerate(items)}
            position = positions.get(anchor.evidence_id)
            if position is not None:
                start = max(0, position - legal_radius)
                end = min(len(items), position + legal_radius + 1)
                group = f"LEGAL:{anchor.doc_id}:P{anchor.page_number:04d}"
                first_page = min((item.page_number for item in items), default=anchor.page_number)
                identity_items = [
                    item
                    for item in items
                    if item.page_number == first_page
                    and re.search(r"\d", item.text)
                    and any(
                        term in _ascii_fold(item.text)
                        for term in ("qd", "quyet dinh", "so ", "ngay ")
                    )
                ][:3]
                for item in identity_items:
                    append(item, group, "legal_identity")
                for item in items[start:end]:
                    append(item, group, "legal_condition")
                continue
        if _looks_tabular(anchor.text, anchor.unit_type):
            items = page_items.get(anchor.page_id, [])
            positions = {item.evidence_id: index for index, item in enumerate(items)}
            position = positions.get(anchor.evidence_id)
            if position is not None:
                start = max(0, position - 2)
                lower = max(0, position - table_scan)
                for index in range(position - 1, lower - 1, -1):
                    folded = _ascii_fold(items[index].text)
                    if "bang " in f"{folded} ":
                        start = index
                        break
                    if any(term in folded for term in ("don vi", "tt tram", "tt kh vi tri")):
                        start = index
                end = min(len(items), position + table_after + 1)
                group = f"TABLE:{anchor.page_id}:{_evidence_block_number(anchor.evidence_id):03d}"
                for item in items[start:end]:
                    append(item, group)
                continue
        append(anchor, f"TEXT:{anchor.page_id}")

    return [
        Evidence(**{**item.to_dict(), "rank": rank})
        for rank, item in enumerate(output, 1)
    ]


def expand_table_evidence(
    evidence: Iterable[Evidence],
    page_evidence: Iterable[Evidence],
    neighbor_before: int = 2,
    neighbor_after: int = 2,
    header_scan: int = 12,
) -> list[Evidence]:
    """Keep table captions, headers, labels, values and units adjacent in context.

    Retrieval scores and selected pages remain unchanged. The function only adds
    same-page neighboring evidence units and preserves every original provenance ID.
    """
    selected = list(evidence)
    selected_by_id = {item.evidence_id: item for item in selected}
    pages: dict[str, list[Evidence]] = {}
    for item in page_evidence:
        pages.setdefault(item.page_id, []).append(item)
    for items in pages.values():
        items.sort(key=lambda item: (_evidence_block_number(item.evidence_id), item.evidence_id))

    output: list[Evidence] = []
    seen: set[str] = set()

    def append(item: Evidence) -> None:
        if item.evidence_id in seen:
            return
        seen.add(item.evidence_id)
        output.append(selected_by_id.get(item.evidence_id, item))

    for anchor in selected:
        page_items = pages.get(anchor.page_id, [])
        positions = {item.evidence_id: index for index, item in enumerate(page_items)}
        position = positions.get(anchor.evidence_id)
        if position is None or not _looks_tabular(anchor.text, anchor.unit_type):
            append(anchor)
            continue
        start = max(0, position - neighbor_before)
        end = min(len(page_items), position + neighbor_after + 1)
        lower_bound = max(0, position - header_scan)
        for index in range(position - 1, lower_bound - 1, -1):
            folded = _ascii_fold(page_items[index].text)
            if "bang " in f"{folded} ":
                start = index
                break
            if any(unit in folded for unit in ("don vi", "mg/l", "mpn/", "muc nuoc ho (m)")):
                start = index
        for item in page_items[start:end]:
            if item.evidence_id in selected_by_id:
                append(item)
            else:
                append(
                    Evidence(
                        **{
                            **item.to_dict(),
                            "score": anchor.score,
                            "source": "table_context_neighbor",
                        }
                    )
                )
    return [
        Evidence(**{**item.to_dict(), "rank": rank})
        for rank, item in enumerate(output, 1)
    ]


def build_prompt(question: str, context: ContextBuild) -> list[dict[str, str]]:
    evidence_text = context.text or "(không có EVIDENCE được cung cấp)"
    user_prompt = f"""QUESTION:
{question.strip()}

EVIDENCE:
{evidence_text}

Hãy trả lời theo JSON schema đã yêu cầu. Nếu từ chối, dùng câu: \"{REFUSAL_TEXT}\"."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


P5_GROUNDED_INSTRUCTIONS = """
Quy tắc grounding bắt buộc:
1. Với bảng, chỉ ghép giá trị sau khi đã xác định đúng caption, đơn vị, header, tên hàng/trạm và cột trong cùng context_group. Nếu thiếu một mắt xích thì không suy đoán.
2. Với văn bản pháp lý, giữ nguyên số văn bản/phiên bản, chủ thể, điều kiện, ngoại lệ, ngưỡng và chiều so sánh. Phân biệt nghiêm ngặt "dưới 5%" với "từ 5% trở lên".
   Với tình huống có số cụ thể, đối chiếu số đó với từng nhánh điều kiện theo đúng dấu so sánh trước khi kết luận; không được đổi "đáp ứng" thành "không đáp ứng".
   Nếu câu hỏi so sánh hai thủ tục hoặc hai nhóm đối tượng, phải nêu rõ nhánh áp dụng và thẩm quyền của từng nhánh, đồng thời trích evidence cho từng điều kiện.
   Nếu answer nêu số hoặc phiên bản văn bản, phải citation cả evidence nhận diện văn bản đó; không dựa riêng vào doc_id.
3. Mỗi citation phải trực tiếp góp phần chứng minh ít nhất một khẳng định trong answer. Nếu một khẳng định cần header và hàng dữ liệu hoặc cần hai điều kiện, hãy trích tất cả evidence cần thiết.
4. Không trích evidence chỉ vì cùng tài liệu hoặc có ID hợp lệ. Không tự tạo citation. Nếu không có đủ evidence trực tiếp hỗ trợ toàn bộ câu trả lời, hãy từ chối có lý do.
5. Trước khi trả lời, tự kiểm tra lại số liệu, đơn vị, thời điểm, phủ định và phép tính; không trình bày bước suy luận nội bộ.
""".strip()


def classify_question_type(question: str) -> str:
    """Classify irrigation questions using lightweight deterministic rules."""
    q_clean = question.strip()
    q_lower = q_clean.lower()

    # Check for incomplete or ambiguous queries (phrases starting with Theo / Về / Bản tin or lacking interrogatives)
    has_question_punct = q_clean.endswith("?")
    has_interrogative = any(k in q_lower for k in [
        "bao nhiêu", "mấy", "gì", "nào", "thế nào", "như thế nào", "sao", "ở đâu", "khi nào",
        "ai", "được không", "có ... không", "quy định gì", "xử lý ra sao", "hãy cho biết",
        "liệt kê", "so sánh", "xác định", "đạt bao nhiêu"
    ])
    starts_incomplete = any(q_lower.startswith(prefix) for prefix in [
        "theo ", "về ", "bản tin ", "dự báo ", "báo cáo ", "tình hình "
    ])
    if starts_incomplete and not has_question_punct and not has_interrogative:
        return "INCOMPLETE_OR_AMBIGUOUS"

    if any(k in q_lower for k in [
        "bao nhiêu", "mấy", "mndbt", "mnc", "dung tích", "lưu lượng", "lượng mưa",
        "cao trình", "cột nước", "thông số", "trị số", "giá trị", "diện tích", "công suất", "độ mặn"
    ]):
        return "NUMERIC_TABLE"
    if any(k in q_lower for k in [
        "quy trình", "quy định", "quyết định", "điều ", "khoản ", "thẩm quyền",
        "nhiệm vụ", "trách nhiệm", "nguyên tắc", "phương án", "lệnh", "nghiêm cấm"
    ]):
        return "REGULATORY_CONDITION"
    if (" và " in q_lower and "dự báo" in q_lower) or "so với" in q_lower or "đồng thời" in q_lower:
        return "MULTI_EVIDENCE"
    return "DESCRIPTIVE"


def build_grounded_prompt(question: str, context: ContextBuild) -> list[dict[str, str]]:
    q_type = classify_question_type(question)
    if q_type == "NUMERIC_TABLE":
        type_instruction = (
            "HƯỚNG DẪN TRẢ LỜI SỐ LIỆU KỸ THUẬT:\n"
            "1. Xác định đúng đối tượng (hồ chứa, trạm quan trắc) và thông số kỹ thuật được hỏi.\n"
            "2. Trình bày câu trả lời tự nhiên, rõ ràng, nêu rõ tên đối tượng, thông số, thời điểm và giá trị kèm đơn vị đo (ví dụ: 'Lượng mưa tại trạm Ninh Bình trong tháng 5/2019 là 239 mm'). Tuyệt đối không trả lời cộc lốc một con số đơn lẻ.\n"
            "3. Trích xuất chính xác giá trị số và đơn vị đo từ [EVIDENCE] đã cung cấp, không tự suy đoán hoặc làm tròn.\n"
            "4. CHỈ trích dẫn đúng đơn vị bằng chứng trực tiếp chứa thông số được hỏi; không liệt kê thêm các ô/cột lân cận không liên quan.\n"
            "5. Ưu tiên trích xuất trực tiếp các trường Thực thể–Thông số–Giá trị–Đơn vị trong [Ô BẢNG NGUỒN]; không chọn số ở hàng hoặc cột khác.\n"
            "6. Nếu câu hỏi hỏi nhiều công trình hoặc nhiều thông số, trình bày rõ từng công trình với giá trị tương ứng."
        )
    elif q_type == "REGULATORY_CONDITION":
        type_instruction = (
            "HƯỚNG DẪN TRẢ LỜI QUY TRÌNH/QUY ĐỊNH PHÁP LÝ:\n"
            "1. Nêu rõ điều khoản, văn bản pháp lý (số hiệu quyết định, quy trình vận hành liên hồ) được quy định trong [EVIDENCE].\n"
            "2. Trình bày chính xác điều kiện áp dụng (mùa lũ, mùa cạn, tình huống khẩn cấp) và thẩm quyền thực thi.\n"
            "3. Giữ nguyên nội dung nguyên văn từ tài liệu nguồn, diễn đạt mạch lạc."
        )
    elif q_type == "MULTI_EVIDENCE":
        type_instruction = (
            "HƯỚNG DẪN TRẢ LỜI ĐA BẰNG CHỨNG:\n"
            "1. Câu hỏi yêu cầu nhiều thông tin. Hãy kết hợp đầy đủ các phần thông tin từ các đoạn [EVIDENCE].\n"
            "2. Đảm bảo trả lời trọn vẹn cả hai vế (ví dụ: số liệu hiện tại và nội dung dự báo).\n"
            "3. Trích dẫn đầy đủ các đơn vị bằng chứng tương ứng."
        )
    elif q_type == "INCOMPLETE_OR_AMBIGUOUS":
        type_instruction = (
            "HƯỚNG DẪN XỬ LÝ CÂU HỎI CHƯA RÕ Ý ĐỊNH HOẶC CHƯA HOÀN CHỈNH:\n"
            "1. Câu hỏi là một tiêu đề hoặc cụm từ chưa nêu rõ yêu cầu cụ thể (ví dụ: thiếu thông số cần hỏi như dung tích, mực nước, diện tích hay khuyến cáo).\n"
            "2. Hãy tóm tắt ngắn gọn bối cảnh tài liệu có trong [EVIDENCE] (1-2 câu ngắn), sau đó lịch sự hướng dẫn người dùng nêu rõ thông số hoặc nội dung cần tra cứu cụ thể.\n"
            "3. Với câu hỏi chưa hoàn chỉnh này, hãy đặt abstained=true, abstention_reason='CẦN_LÀM_RÕ_CÂU_HỎI', citations=[] và evidence_supported=false. Không tự ý bịa thêm số liệu hay phán đoán điều chưa được hỏi."
        )
    else:
        type_instruction = (
            "HƯỚNG DẪN TRẢ LỜI:\n"
            "1. Trả lời trực tiếp vào trọng tâm câu hỏi dựa trên các đoạn [EVIDENCE].\n"
            "2. Trả lời bằng tiếng Việt tự nhiên, ngắn gọn và mạch lạc. Không thêm thắt thông tin ngoài tài liệu."
        )

    messages = build_prompt(question, context)
    system_content = f"{messages[0]['content']}\n\nLOẠI CÂU HỎI: {q_type}\n{type_instruction}\n\n{P5_GROUNDED_INSTRUCTIONS}"
    return [
        {"role": "system", "content": system_content},
        messages[1],
    ]



def prompt_text(messages: list[dict[str, str]]) -> str:
    return "\n\n".join(f"{row['role'].upper()}:\n{row['content']}" for row in messages)


def parse_generation(raw_response: str) -> GenerationResult:
    parse_error = ""
    try:
        value = json.loads(raw_response)
        if not isinstance(value, dict):
            raise TypeError("top-level JSON is not an object")
    except (json.JSONDecodeError, TypeError) as exc:
        value = {}
        parse_error = f"{type(exc).__name__}: {exc}"
    answer = str(value.get("answer") or "").strip()
    citations = value.get("citations")
    if not isinstance(citations, list):
        citations = []
        parse_error = "; ".join(part for part in (parse_error, "citations is not an array") if part)
    clean_citations: list[dict[str, Any]] = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        try:
            clean_citations.append(
                {
                    "doc_id": str(citation.get("doc_id") or ""),
                    "page_number": int(citation.get("page_number")),
                    "evidence_id": str(citation.get("evidence_id") or ""),
                }
            )
        except (TypeError, ValueError):
            continue
    abstained = bool(value.get("abstained", False))
    reason = str(value.get("abstention_reason") or "").strip()
    evidence_supported = bool(value.get("evidence_supported", False))
    if not answer:
        answer = REFUSAL_TEXT if abstained else raw_response.strip()
    return GenerationResult(
        answer=answer,
        citations=clean_citations,
        abstained=abstained,
        abstention_reason=reason,
        evidence_supported=evidence_supported,
        parse_error=parse_error,
        raw_response=raw_response,
    )


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).casefold()
    return " ".join(re.findall(r"\w+|\d+(?:[.,]\d+)?%?", text, flags=re.UNICODE))


def _ascii_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.casefold())
    folded = "".join(character for character in normalized if unicodedata.category(character) != "Mn")
    folded = folded.replace("đ", "d")
    return " ".join(
        re.findall(
            r"\w+|\d+(?:[.,]\d+)?%?",
            folded,
            flags=re.UNICODE,
        )
    )


def _tokens(text: str) -> list[str]:
    return _normalize(text).split()


def _content_tokens(text: str) -> set[str]:
    stopwords = {
        "và", "là", "của", "có", "không", "được", "trong", "cho", "với",
        "theo", "tại", "một", "các", "để", "khi", "này", "đó", "thì",
        "về", "do", "từ", "trên", "những", "phải", "cần", "như",
    }
    return {token for token in _tokens(text) if len(token) > 1 and token not in stopwords}


def token_f1(reference: str, prediction: str) -> float:
    reference_tokens = _tokens(reference)
    prediction_tokens = _tokens(prediction)
    if not reference_tokens or not prediction_tokens:
        return 0.0
    reference_counts = {token: reference_tokens.count(token) for token in set(reference_tokens)}
    prediction_counts = {token: prediction_tokens.count(token) for token in set(prediction_tokens)}
    overlap = sum(min(reference_counts.get(token, 0), count) for token, count in prediction_counts.items())
    if overlap == 0:
        return 0.0
    precision = overlap / len(prediction_tokens)
    recall = overlap / len(reference_tokens)
    return 2 * precision * recall / (precision + recall)


def content_recall(reference: str, prediction: str) -> float:
    reference_tokens = _content_tokens(reference)
    if not reference_tokens:
        return 1.0
    return len(reference_tokens & _content_tokens(prediction)) / len(reference_tokens)


def _numbers(text: str) -> set[str]:
    values = set()
    for value in re.findall(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?%?", text):
        values.add(value.replace(",", "."))
    return values


def numeric_recall(reference: str, prediction: str) -> float:
    reference_values = _numbers(reference)
    if not reference_values:
        return 1.0
    return len(reference_values & _numbers(prediction)) / len(reference_values)


def _character_ngram_dice(reference: str, prediction: str, size: int = 3) -> float:
    def ngrams(text: str) -> set[str]:
        value = _ascii_fold(text).replace(" ", "_")
        return {value[index:index + size] for index in range(max(0, len(value) - size + 1))}

    reference_ngrams = ngrams(reference)
    prediction_ngrams = ngrams(prediction)
    if not reference_ngrams or not prediction_ngrams:
        return 0.0
    return 2 * len(reference_ngrams & prediction_ngrams) / (
        len(reference_ngrams) + len(prediction_ngrams)
    )


def _answer_stance(text: str) -> str:
    folded = _ascii_fold(text)
    first_clause = re.split(r"[.!?;]", folded, maxsplit=1)[0].strip()
    if first_clause.startswith(("khong", "chua", "khong the", "khong duoc")):
        return "NEGATIVE"
    if first_clause.startswith(("co ", "co the", "duoc", "dung")):
        return "POSITIVE"
    if any(
        phrase in folded
        for phrase in ("khong the", "khong duoc", "khong hoan toan", "khong nhat quan", "mau thuan")
    ):
        return "NEGATIVE"
    if any(phrase in folded for phrase in ("nhat quan", "phu hop", "co the coi", "co the ap")):
        return "POSITIVE"
    if any(token in folded.split() for token in ("phai", "yeu", "can")):
        return "DIRECTIVE"
    return "NEUTRAL"


def _semantic_assessment(
    reference: str,
    prediction: str,
    content_recall_score: float,
    numeric_recall_score: float,
    lexical_f1: float,
) -> dict[str, Any]:
    reference_tokens = _content_tokens(reference)
    prediction_tokens = _content_tokens(prediction)
    overlap = reference_tokens & prediction_tokens
    content_precision = len(overlap) / max(1, len(prediction_tokens))
    char_dice = _character_ngram_dice(reference, prediction)
    reference_stance = _answer_stance(reference)
    prediction_stance = _answer_stance(prediction)
    stance_alignment = (
        "ALIGNED"
        if reference_stance == prediction_stance and reference_stance != "NEUTRAL"
        else "CONTRADICTED"
        if {reference_stance, prediction_stance} <= {"NEGATIVE", "POSITIVE"}
        and reference_stance != prediction_stance
        else "NOT_DECISIVE"
    )
    reference_folded = _ascii_fold(reference)
    prediction_folded = _ascii_fold(prediction)
    obligation_denied = (
        any(marker in reference_folded.split() for marker in ("phai", "yeu"))
        and any(
            phrase in prediction_folded
            for phrase in ("khong co quy dinh", "khong co yeu cau", "khong co quy tac")
        )
    )
    decisive_reference_without_matching_stance = (
        reference_stance in {"NEGATIVE", "POSITIVE"}
        and prediction_stance == "NEUTRAL"
    )
    if obligation_denied or stance_alignment == "CONTRADICTED" or decisive_reference_without_matching_stance:
        semantic_correctness = "MISMATCH"
    elif lexical_f1 >= 0.55 and content_recall_score >= 0.55 and numeric_recall_score == 1.0:
        semantic_correctness = "MATCH"
    elif (
        stance_alignment == "ALIGNED"
        and (content_precision >= 0.15 or content_recall_score >= 0.15 or char_dice >= 0.20)
    ) or content_recall_score >= 0.40 or char_dice >= 0.42:
        semantic_correctness = "SEMANTIC_MATCH"
    elif content_recall_score >= 0.25 or char_dice >= 0.25:
        semantic_correctness = "PARTIAL"
    else:
        semantic_correctness = "MISMATCH"
    if content_recall_score >= 0.55 and numeric_recall_score == 1.0:
        content_completeness = "COMPLETE"
    elif content_recall_score >= 0.25 and numeric_recall_score >= 0.5:
        content_completeness = "PARTIAL"
    elif semantic_correctness in {"MATCH", "SEMANTIC_MATCH"}:
        content_completeness = "CORE_ONLY"
    else:
        content_completeness = "INCOMPLETE"
    return {
        "semantic_correctness": semantic_correctness,
        "content_completeness": content_completeness,
        "semantic_similarity": round(char_dice, 6),
        "content_precision": round(content_precision, 6),
        "reference_stance": reference_stance,
        "prediction_stance": prediction_stance,
        "stance_alignment": stance_alignment,
        "semantic_contradiction": (
            obligation_denied
            or stance_alignment == "CONTRADICTED"
            or decisive_reference_without_matching_stance
        ),
    }


def _claim_support(claim: str, evidence: list[Evidence]) -> tuple[bool, float, list[str]]:
    claim_tokens = _content_tokens(claim)
    claim_numbers = _numbers(claim)
    best_overlap = 0.0
    best_ids: list[str] = []
    for item in evidence:
        evidence_tokens = _content_tokens(item.text)
        overlap = len(claim_tokens & evidence_tokens) / max(1, len(claim_tokens))
        if overlap > best_overlap:
            best_overlap = overlap
            best_ids = [item.evidence_id]
        elif overlap == best_overlap and overlap > 0:
            best_ids.append(item.evidence_id)
    all_evidence_text = " ".join(item.text for item in evidence)
    numbers_supported = not claim_numbers or claim_numbers <= _numbers(all_evidence_text)
    return bool(evidence) and best_overlap >= 0.20 and numbers_supported, best_overlap, best_ids


def _answer_claims(answer: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"(?<=[.!?;])\s+|\n+", answer) if part.strip()]
    return [part for part in parts if len(_content_tokens(part)) >= 2]


def _condition_markers(text: str) -> set[str]:
    folded = _ascii_fold(text)
    markers: set[str] = set()
    if re.search(r"\bduoi\b|<", folded):
        markers.add("BELOW")
    if re.search(r"\btu\b.{0,30}\btro len\b|>=", folded):
        markers.add("AT_LEAST")
    if re.search(r"\btru\b|ngoai tru", folded):
        markers.add("EXCEPTION")
    if re.search(r"\bkhong\b|\bkhong duoc\b", folded):
        markers.add("NEGATION")
    return markers


def _semantic_assertions(text: str) -> dict[str, set[str]]:
    folded = _ascii_fold(text)
    assertions: dict[str, set[str]] = {}

    obligation_denials = (
        r"\bkhong\s+(?:can|phai|bat buoc)\b",
        r"\bkhong\s+co\s+(?:nghia vu|yeu cau)\b",
        r"\bkhong\s+duoc\s+yeu cau\b",
    )
    obligation_masked = folded
    if any(re.search(pattern, folded) for pattern in obligation_denials):
        assertions.setdefault("OBLIGATION", set()).add("NOT_REQUIRED")
        for pattern in obligation_denials:
            obligation_masked = re.sub(pattern, " ", obligation_masked)
    if re.search(r"\b(?:phai|bat buoc)\b|\bco nghia vu\b|\bduoc yeu cau\b", obligation_masked):
        assertions.setdefault("OBLIGATION", set()).add("REQUIRED")

    consistency_denials = (
        r"\bkhong\s+nhat quan\b",
        r"\bkhong\s+(?:phu hop|trung khop)\b",
        r"\bmau thuan\b",
    )
    consistency_masked = folded
    if any(re.search(pattern, folded) for pattern in consistency_denials):
        assertions.setdefault("CONSISTENCY", set()).add("INCONSISTENT")
        for pattern in consistency_denials:
            consistency_masked = re.sub(pattern, " ", consistency_masked)
    if re.search(r"\bnhat quan\b|\bphu hop(?:\s+nhau)?\b|\btrung khop\b", consistency_masked):
        assertions.setdefault("CONSISTENCY", set()).add("CONSISTENT")

    different_patterns = (
        r"\bkhac nhau\b",
        r"\bchenh lech\b",
        r"\bkhong\s+giong nhau\b",
        r"\bhai muc rieng\b",
    )
    same_patterns = (
        r"\bgiong nhau\b",
        r"\bbang nhau\b",
        r"\btrung nhau\b",
        r"\bcung mot muc\b",
        r"\bkhong\s+khac nhau\b",
    )
    equality_masked = folded
    if any(re.search(pattern, folded) for pattern in different_patterns):
        assertions.setdefault("EQUALITY", set()).add("DIFFERENT")
        for pattern in different_patterns:
            equality_masked = re.sub(pattern, " ", equality_masked)
    if any(re.search(pattern, equality_masked) for pattern in same_patterns):
        assertions.setdefault("EQUALITY", set()).add("SAME")
    return assertions


def _semantic_relation(claim: str, evidence_text: str) -> tuple[str, dict[str, Any]]:
    claim_assertions = _semantic_assertions(claim)
    evidence_assertions = _semantic_assertions(evidence_text)
    aligned: list[str] = []
    contradicted: list[str] = []
    unverified: list[str] = []
    for dimension, claim_values in claim_assertions.items():
        evidence_values = evidence_assertions.get(dimension, set())
        if len(claim_values) != 1 or len(evidence_values) != 1:
            unverified.append(dimension)
        elif claim_values == evidence_values:
            aligned.append(dimension)
        else:
            contradicted.append(dimension)
    if contradicted:
        relation = "CONTRADICTED"
    elif unverified:
        relation = "UNVERIFIED"
    elif aligned:
        relation = "ALIGNED"
    else:
        relation = "NOT_APPLICABLE"
    return relation, {
        "claim_assertions": {key: sorted(values) for key, values in claim_assertions.items()},
        "evidence_assertions": {key: sorted(values) for key, values in evidence_assertions.items()},
        "aligned_dimensions": aligned,
        "contradicted_dimensions": contradicted,
        "unverified_dimensions": unverified,
    }


@dataclass(frozen=True)
class _NumericMention:
    value: Decimal
    unit: str
    raw: str
    is_year: bool = False


@dataclass(frozen=True)
class _Condition:
    operator: str
    value: Decimal
    unit: str
    raw: str


@dataclass(frozen=True)
class _EvidenceScope:
    text: str
    evidence_ids: tuple[str, ...]
    kind: str
    group: str = ""
    row_text: str = ""
    shared_text: str = ""


@dataclass(frozen=True)
class _FactRelation:
    entity: frozenset[str]
    attribute: str
    value: _NumericMention
    temporal: frozenset[str]
    polarity: str
    provenance: str


_MEASUREMENT_TERMS = {
    "bao dong", "cao trinh", "cao trinh day", "chat luong", "chi so", "dien tich", "do", "dung tich",
    "gia tri", "ham luong", "luu luong", "muc", "muc nuoc", "nong do",
    "phan tram", "tan suat", "the tich", "trung binh", "wqi",
}
_ATTRIBUTE_PHRASES = tuple(
    sorted(
        {
            *_MEASUREMENT_TERMS,
            "do trung binh",
            "dung tich phong lu",
            "dung tich huu ich",
            "muc nuoc bao dong",
            "bod",
            "cod",
        },
        key=lambda value: (-len(value.split()), -len(value)),
    )
)
_RELATION_GENERIC_TOKENS = {
    "bang", "bao", "cao", "cap", "chi", "co", "cong", "do", "don", "gia",
    "hai", "ho", "la", "muc", "nam", "ngay", "nhat", "quyet", "tai", "thang",
    "theo", "tram", "tri", "truong", "vi",
}


def _plain_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.casefold())
    folded = "".join(character for character in normalized if unicodedata.category(character) != "Mn")
    return re.sub(r"\s+", " ", folded.replace("đ", "d")).strip()


def _canonical_number(raw: str) -> Decimal | None:
    value = raw.strip().replace(" ", "")
    if "," in value and "." in value:
        decimal_separator = "," if value.rfind(",") > value.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        value = value.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif "," in value:
        value = value.replace(",", ".")
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _canonical_unit(raw: str) -> str:
    folded = _plain_fold(raw).replace(" ", "")
    if not folded:
        return ""
    if folded == "%":
        return "percent"
    if folded in {"mg/l", "mgl"}:
        return "mg/l"
    if folded in {"g/l", "gl"}:
        return "g/l"
    if folded in {"m3", "m³"}:
        return "m3"
    if folded in {"trieum3", "trieum³"}:
        return "million_m3"
    if folded in {"diem", "point", "points"}:
        return "point"
    if folded in {"m", "cm", "mm"}:
        return folded
    return folded


def _numeric_mentions(text: str) -> list[_NumericMention]:
    pattern = re.compile(
        r"(?<![\w/])([+-]?\d+(?:[.,]\d+)?)(?![\w/])"
        r"\s*(trieu\s*m(?:3|³)|mg\s*/\s*l|g\s*/\s*l|m(?:3|³)|cm|mm|m|%|diem)?",
        flags=re.IGNORECASE,
    )
    folded = _plain_fold(text)
    mentions: list[_NumericMention] = []
    for match in pattern.finditer(folded):
        value = _canonical_number(match.group(1))
        if value is None:
            continue
        raw_unit = match.group(2) or ""
        unit = _canonical_unit(raw_unit)
        is_year = not unit and value == value.to_integral_value() and Decimal("1900") <= value <= Decimal("2100")
        mentions.append(
            _NumericMention(
                value=value,
                unit="year" if is_year else unit,
                raw=match.group(0),
                is_year=is_year,
            )
        )
    return mentions


def _units(text: str) -> set[str]:
    matches = re.findall(
        r"trieu\s*m(?:3|³)|mg\s*/\s*l|g\s*/\s*l|m(?:3|³)|cm|mm|(?<!\w)m(?!\w)|%|diem",
        _plain_fold(text),
        flags=re.IGNORECASE,
    )
    return {_canonical_unit(value) for value in matches if _canonical_unit(value)}


def _condition_mentions(text: str) -> list[_Condition]:
    folded = _plain_fold(text)
    number = r"([+-]?\d+(?:[.,]\d+)?)"
    unit = r"\s*(%|mg\s*/\s*l|g\s*/\s*l|trieu\s*m(?:3|³)|m(?:3|³)|cm|mm|m)?"
    patterns = (
        ("GE", rf"\btu\s+{number}{unit}\s+tro\s+len\b"),
        ("LE", rf"\btu\s+{number}{unit}\s+tro\s+xuong\b"),
        ("LE", rf"\b(?:khong\s+qua|khong\s+vuot\s+qua|toi\s+da)\s+{number}{unit}"),
        ("GE", rf"\b(?:khong\s+duoi|it\s+nhat|toi\s+thieu)\s+{number}{unit}"),
        ("LT", rf"\b(?:duoi|nho\s+hon)\s+{number}{unit}"),
        ("GT", rf"\b(?:tren|lon\s+hon)\s+{number}{unit}"),
        ("LE", rf"<=\s*{number}{unit}"),
        ("GE", rf">=\s*{number}{unit}"),
        ("LT", rf"<\s*{number}{unit}"),
        ("GT", rf">\s*{number}{unit}"),
        ("EQ", rf"\b(?:bang|dung\s+bang)\s+{number}{unit}"),
    )
    conditions: list[_Condition] = []
    seen: set[tuple[str, Decimal, str]] = set()
    for operator, pattern in patterns:
        for match in re.finditer(pattern, folded):
            value = _canonical_number(match.group(1))
            if value is None:
                continue
            canonical_unit = _canonical_unit(match.group(2) or "")
            key = (operator, value, canonical_unit)
            if key in seen:
                continue
            seen.add(key)
            conditions.append(_Condition(operator, value, canonical_unit, match.group(0)))
    return conditions


def _condition_equivalent(left: _Condition, right: _Condition) -> bool:
    units_compatible = not left.unit or not right.unit or left.unit == right.unit
    return left.operator == right.operator and left.value == right.value and units_compatible


def _condition_conflicts(left: _Condition, right: _Condition) -> bool:
    units_compatible = not left.unit or not right.unit or left.unit == right.unit
    if left.value != right.value or not units_compatible:
        return False
    opposites = {
        ("LT", "GE"), ("LT", "GT"), ("LE", "GT"),
        ("GE", "LT"), ("GT", "LT"), ("GT", "LE"),
    }
    return (left.operator, right.operator) in opposites


def _condition_entails(evidence: _Condition, claim: _Condition) -> bool:
    units_compatible = not evidence.unit or not claim.unit or evidence.unit == claim.unit
    if evidence.value != claim.value or not units_compatible:
        return False
    return (evidence.operator, claim.operator) in {
        ("EQ", "EQ"), ("GE", "GE"), ("GE", "GT"), ("GT", "GT"),
        ("LE", "LE"), ("LE", "LT"), ("LT", "LT"),
    }


def _authority_markers(text: str) -> set[str]:
    folded = _plain_fold(text)
    markers: set[str] = set()
    if re.search(r"\bchu\s+tich\b", folded):
        markers.add("role:chairperson")
    if re.search(r"\bubnd\b|\buy\s+ban\s+nhan\s+dan\b", folded):
        markers.add("institution:ubnd")
    for level in re.findall(
        r"(?:chu\s+tich\s+)?(?:ubnd|uy\s+ban\s+nhan\s+dan)?\s*cap\s+(xa|huyen|tinh|trung\s+uong)",
        folded,
    ):
        markers.add(f"level:{level.replace(' ', '_')}")
    if re.search(r"\bchu\s+tich\s+xa\b", folded):
        markers.add("level:xa")
    if re.search(r"\bbo\s+truong\b", folded):
        markers.add("role:bo_truong")
    if re.search(r"\bthu\s+tuong\b", folded):
        markers.add("role:thu_tuong")
    return markers


def _authority_relation(claim_markers: set[str], evidence_markers: set[str]) -> str:
    if not claim_markers:
        return "ALIGNED"
    if not evidence_markers:
        return "INSUFFICIENT"
    for prefix in ("level:", "institution:", "role:"):
        claim_values = {item for item in claim_markers if item.startswith(prefix)}
        evidence_values = {item for item in evidence_markers if item.startswith(prefix)}
        if claim_values and evidence_values and claim_values != evidence_values:
            return "CONTRADICTED"
        if claim_values and not evidence_values:
            return "INSUFFICIENT"
        if prefix == "role:" and evidence_values and not claim_values:
            return "INSUFFICIENT"
    return "ALIGNED" if claim_markers <= evidence_markers else "INSUFFICIENT"


def _legal_actions(text: str) -> set[tuple[str, str]]:
    folded = _plain_fold(text)
    actions = ("quyet dinh", "phe duyet", "ban hanh", "cho phep", "xu ly")
    found: set[tuple[str, str]] = set()
    for action in actions:
        if re.search(rf"\b(?:khong|chua)\s+{re.escape(action)}\b", folded):
            found.add((action, "NEGATED"))
        elif re.search(rf"\b{re.escape(action)}\b", folded):
            found.add((action, "AFFIRMED"))
    return found


def _jurisdiction_markers(text: str) -> set[str]:
    folded = _plain_fold(text)
    matches = re.findall(
        r"\b(?:tai|tren\s+dia\s+ban)\s+(?:tinh|thanh\s+pho)\s+([a-z0-9_-]+)",
        folded,
    )
    return {f"jurisdiction:{item}" for item in matches}


def _legal_field_relation(claim: str, evidence: str) -> str:
    claim_actions = _legal_actions(claim)
    evidence_actions = _legal_actions(evidence)
    claim_jurisdictions = _jurisdiction_markers(claim)
    evidence_jurisdictions = _jurisdiction_markers(evidence)
    for claim_values, evidence_values in (
        (claim_actions, evidence_actions),
        (claim_jurisdictions, evidence_jurisdictions),
    ):
        if claim_values and evidence_values and claim_values != evidence_values:
            return "CONTRADICTED"
        if bool(claim_values) != bool(evidence_values):
            return "INSUFFICIENT"
    return "ALIGNED"


def _temporal_markers(text: str) -> set[str]:
    folded = _plain_fold(text)
    markers: set[str] = set()
    for match in re.finditer(r"(?<!\d)(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?(?!\d)", folded):
        d_val, m_val, y_val = int(match.group(1)), int(match.group(2)), match.group(3)
        if 1 <= d_val <= 31 and 1 <= m_val <= 12:
            dm = f"{d_val:02d}/{m_val:02d}"
            markers.add(dm)
            if y_val:
                y_num = int(y_val)
                if y_num < 100:
                    y_num += 2000
                markers.add(f"{dm}/{y_num}")
                markers.add(f"year:{y_num}")
    years = {str(int(item.value)) for item in _numeric_mentions(text) if item.is_year}
    for year in years:
        markers.add(f"year:{year}")
    return markers


def _temporal_verdict(claim_temporal: set[str], scope_temporal: set[str]) -> str:
    if not claim_temporal:
        return "ALIGNED"
    if not scope_temporal:
        return "INSUFFICIENT"
    claim_dm = {item for item in claim_temporal if "/" in item and not item.startswith("year:") and len(item.split("/")) == 2}
    scope_dm = {item for item in scope_temporal if "/" in item and not item.startswith("year:") and len(item.split("/")) == 2}
    claim_years = {item for item in claim_temporal if item.startswith("year:")}
    scope_years = {item for item in scope_temporal if item.startswith("year:")}

    if claim_dm and scope_dm and not (claim_dm & scope_dm):
        return "INSUFFICIENT"
    if claim_years and scope_years and not (claim_years & scope_years):
        return "INSUFFICIENT"
    if (claim_dm and scope_dm and (claim_dm & scope_dm)) or (claim_years and scope_years and (claim_years & scope_years)):
        return "ALIGNED"
    return "ALIGNED" if claim_temporal <= scope_temporal else "INSUFFICIENT"


def _attribute_mentions(text: str) -> list[tuple[int, int, str]]:
    """Find metric labels without treating nearby numbers as their values."""
    folded = _plain_fold(text)
    candidates: list[tuple[int, int, str]] = []
    for phrase in _ATTRIBUTE_PHRASES:
        for match in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", folded):
            candidates.append((match.start(), match.end(), phrase))
    for match in re.finditer(r"(?<!\w)([A-Z]{2,10})(?!\w)", text):
        acronym = _plain_fold(match.group(1))
        if acronym not in {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "tt"}:
            candidates.append((match.start(), match.end(), acronym))
    selected: list[tuple[int, int, str]] = []
    for candidate in sorted(candidates, key=lambda item: (item[0], -(item[1] - item[0]))):
        if candidate[2] == "muc" and folded[max(0, candidate[0] - 3):candidate[0]].strip().endswith("o"):
            continue
        if candidate[2] == "do" and folded[max(0, candidate[0] - 5):candidate[0]].strip().endswith("thuc"):
            continue
        if any(candidate[0] < end and start < candidate[1] for start, end, _ in selected):
            continue
        selected.append(candidate)
    return selected


def _measurement_after(text: str, start: int, limit: int | None = None) -> _NumericMention | None:
    mention, _ = _measurement_after_with_span(text, start, limit)
    return mention


def _measurement_after_with_span(text: str, start: int, limit: int | None = None) -> tuple[_NumericMention | None, int]:
    suffix = _plain_fold(text[start:limit])
    match = re.search(
        r"(?<![\w/])([+-]?\d+(?:[.,]\d+)?)(?![\w/])"
        r"\s*(trieu\s*m(?:3|³|Â³)|mg\s*/\s*l|g\s*/\s*l|m(?:3|³|Â³)|cm|mm|m|%|diem)?",
        suffix,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None, start
    prefix = suffix[:match.start()].strip()
    if not match.group(2) and prefix and not re.fullmatch(r"(?:la|=|:)?", prefix):
        return None, start
    value = _canonical_number(match.group(1))
    if value is None:
        return None, start
    mention = _NumericMention(value, _canonical_unit(match.group(2) or ""), match.group(0))
    return mention, start + match.end()


def _entity_tokens(text: str) -> frozenset[str]:
    identifiers = _identifier_tokens(text)
    if identifiers:
        return frozenset(identifiers)
    named = re.findall(
        r"\b(?:[Tt]ram|[Tt]rạm|[Hh]o|[Hh]ồ|[Cc]ua|[Cc]ủa|[Tt]ai|[Tt]ại|[Oo]|[Ởở]|[Cc]ống|[Cc]ong|[Vv]à|[Vv]a)\s+((?:[A-ZÀ-ỸĐ][\w-]*)(?:\s+[A-ZÀ-ỸĐ][\w-]*){0,2})",
        text,
    )
    if named:
        tokens = frozenset(_plain_fold(named[-1]).split()) - _RELATION_GENERIC_TOKENS
        if tokens:
            return tokens
    before_verb = re.search(
        r"\b((?:[A-ZÀ-ỸĐ][\w-]*)(?:\s+[A-ZÀ-ỸĐ][\w-]*){0,2})\s+(?:là|đạt|có|=)\s+",
        text,
    )
    if before_verb:
        tokens = frozenset(_plain_fold(before_verb.group(1)).split()) - _RELATION_GENERIC_TOKENS
        if tokens:
            return tokens
    before_value = re.match(
        r"\s*((?:[A-ZÀ-ỸĐ][\w-]*)(?:\s+[A-ZÀ-ỸĐ][\w-]*){0,2})\s+(?=\d)",
        text,
    )
    if before_value:
        tokens = frozenset(_plain_fold(before_value.group(1)).split()) - _RELATION_GENERIC_TOKENS
        if tokens:
            return tokens
    return frozenset()


def _narrative_relations(text: str, provenance: str) -> list[_FactRelation]:
    """Extract locally stated measurement relations from a narrative fragment.

    This deliberately accepts only metric labels followed by a value.  A value
    elsewhere in the same sentence is not attached to that metric.
    """
    facts: list[_FactRelation] = []
    inherited_entity: frozenset[str] = frozenset()
    inherited_temporal: frozenset[str] = frozenset()
    previous_end = 0
    attributes = _attribute_mentions(text)
    for index, (start, end, attribute) in enumerate(attributes):
        next_start = attributes[index + 1][0] if index + 1 < len(attributes) else None
        value, value_end = _measurement_after_with_span(text, end, next_start)
        if value is None:
            continue
        local_prefix = text[previous_end:start]
        local_suffix = text[end:value_end]
        entity = _entity_tokens(local_prefix) or _entity_tokens(local_suffix) or inherited_entity
        temporal = frozenset(_temporal_markers(local_prefix)) or frozenset(_temporal_markers(local_suffix)) or inherited_temporal
        folded_prefix = _plain_fold(local_prefix)
        folded_suffix = _plain_fold(local_suffix)
        negated = bool(
            re.search(r"\b(?:khong|chua)(?:\s+dat)?\s*$", folded_prefix)
            or re.match(r"\s*(?:khong|chua)\s+(?:dat\s+)?", folded_suffix)
        )
        facts.append(_FactRelation(entity, attribute, value, temporal, "NEGATED" if negated else "AFFIRMED", provenance))
        inherited_entity = entity
        inherited_temporal = temporal
        previous_end = value_end

    # Handle parallel coordinate clauses with elided attribute: " và [Entity] là/đạt/có [Value]" or ", [Entity] là/đạt/có [Value]"
    if facts:
        coord_matches = re.finditer(
            r"(?:\s+và\s+|,\s*(?:và\s+)?)([^,.;\n]+?)\s+(?:là|đạt|có|=)\s+",
            text,
            re.IGNORECASE,
        )
        for m in coord_matches:
            tail_ent_raw = m.group(1).strip()
            if _attribute_mentions(tail_ent_raw):
                continue
            tail_val, _ = _measurement_after_with_span(text, m.end())
            if tail_val is None:
                continue
            if any(f.value.value == tail_val.value for f in facts):
                continue
            tail_entity = _entity_tokens(tail_ent_raw) or (frozenset(_plain_fold(tail_ent_raw).split()) - _RELATION_GENERIC_TOKENS)
            if not tail_entity:
                continue
            prev_fact = facts[-1]
            temporal = frozenset(_temporal_markers(tail_ent_raw)) or prev_fact.temporal
            facts.append(
                _FactRelation(
                    tail_entity,
                    prev_fact.attribute,
                    tail_val,
                    temporal,
                    prev_fact.polarity,
                    provenance,
                )
            )

    return facts


def _table_header_attributes(text: str) -> list[str]:
    return [attribute for _, _, attribute in _attribute_mentions(text)]


def _table_relations(scope: _EvidenceScope) -> list[_FactRelation]:
    attributes = _table_header_attributes(scope.shared_text)
    values = _numeric_mentions(scope.row_text)
    entity = _entity_tokens(scope.row_text)
    if not entity or not attributes or len(values) != len(attributes):
        return []
    shared_units = _units(scope.shared_text)
    default_unit = next(iter(shared_units)) if len(shared_units) == 1 else ""
    normalized_values = [
        value if value.unit or not default_unit else _NumericMention(value.value, default_unit, value.raw)
        for value in values
    ]
    temporal = frozenset(_temporal_markers(scope.text))
    return [
        _FactRelation(entity, attribute, value, temporal, "AFFIRMED", scope.evidence_ids[0])
        for attribute, value in zip(attributes, normalized_values, strict=True)
    ]


def _table_cell_relations(scope: _EvidenceScope) -> list[_FactRelation]:
    text = scope.row_text or scope.text
    entity_match = re.search(r"Thực thể:\s*([^;|]+)", text)
    metric_match = re.search(r"Thông số:\s*([^;|]+)", text)
    time_match = re.search(r"Thời gian:\s*([^;|]+)", text)
    val_match = re.search(r"Giá trị:\s*([^;|]+)", text)
    unit_match = re.search(r"Đơn vị:\s*([^;|]+)", text)
    if not (entity_match and metric_match and val_match):
        return _narrative_relations(text, scope.evidence_ids[0])
    entity = frozenset(_plain_fold(entity_match.group(1).strip()).split())
    raw_metric = metric_match.group(1).strip()
    attrs = _attribute_mentions(raw_metric)
    attribute = attrs[0][2] if attrs else _plain_fold(raw_metric)
    val_raw = val_match.group(1).strip()
    val_mentions = _numeric_mentions(val_raw)
    if val_mentions:
        val_num = val_mentions[0].value
        raw_unit = val_mentions[0].unit or (unit_match.group(1).strip() if unit_match else "")
    else:
        val_num = _canonical_number(val_raw)
        raw_unit = unit_match.group(1).strip() if unit_match else ""
    if val_num is None:
        return []
    unit = _canonical_unit(raw_unit)
    value = _NumericMention(val_num, unit, f"{val_raw} {raw_unit}".strip())
    time_text = (time_match.group(1).strip() if time_match else "") + " " + raw_metric
    temporal = frozenset(_temporal_markers(time_text))
    return [_FactRelation(entity, attribute, value, temporal, "AFFIRMED", scope.evidence_ids[0])]


def _scope_relations(scope: _EvidenceScope) -> list[_FactRelation]:
    if scope.kind == "table_row":
        return _table_relations(scope)
    if scope.kind == "table_cell" or "[Ô BẢNG NGUỒN]" in scope.text:
        return _table_cell_relations(scope)
    return _narrative_relations(scope.row_text or scope.text, scope.evidence_ids[0])


def _same_entity(left: _FactRelation, right: _FactRelation) -> bool:
    return left.entity == right.entity or left.entity <= right.entity or right.entity <= left.entity


def _temporal_relation(left: _FactRelation, right: _FactRelation) -> str:
    return _temporal_verdict(set(left.temporal), set(right.temporal))


def _relation_fact_verdict(claim: str, scopes: list[_EvidenceScope]) -> dict[str, Any] | None:
    claim_facts = _narrative_relations(claim, "claim")
    if not claim_facts:
        return None
    evidence_facts = [(scope, fact) for scope in scopes for fact in _scope_relations(scope)]
    supported_ids: set[str] = set()
    contradicted_ids: set[str] = set()
    relation_verdicts: list[dict[str, Any]] = []
    for claim_fact in claim_facts:
        matches = [
            (scope, evidence_fact)
            for scope, evidence_fact in evidence_facts
            if _same_entity(claim_fact, evidence_fact) and claim_fact.attribute == evidence_fact.attribute
        ]
        if not matches:
            relation_verdicts.append(
                {
                    "entity": sorted(claim_fact.entity),
                    "attribute": claim_fact.attribute,
                    "value": str(claim_fact.value.value),
                    "unit": claim_fact.value.unit,
                    "temporal": sorted(claim_fact.temporal),
                    "polarity": claim_fact.polarity,
                    "status": "INSUFFICIENT",
                    "supporting_evidence_ids": [],
                    "contradicting_evidence_ids": [],
                    "reason": "FACT_SUBJECT_OR_ATTRIBUTE_NOT_FOUND",
                }
            )
            continue
        fact_supporting_ids: set[str] = set()
        fact_contradicting_ids: set[str] = set()
        for scope, evidence_fact in matches:
            temporal = _temporal_relation(claim_fact, evidence_fact)
            if temporal != "ALIGNED":
                continue
            if (
                claim_fact.value.value != evidence_fact.value.value
                or claim_fact.value.unit != evidence_fact.value.unit
                or claim_fact.polarity != evidence_fact.polarity
            ):
                fact_contradicting_ids.update(scope.evidence_ids)
                continue
            fact_supporting_ids.update(scope.evidence_ids)
        if fact_supporting_ids and fact_contradicting_ids:
            status = "INSUFFICIENT"
            reason = "CONFLICTING_EVIDENCE_FOR_FACT"
        elif fact_supporting_ids:
            status = "SUPPORTED"
            reason = "EXPLICIT_FACT_RELATION"
        elif fact_contradicting_ids:
            status = "CONTRADICTED"
            reason = "ENTITY_ATTRIBUTE_VALUE_TIME_OR_POLARITY_CONFLICT"
        else:
            status = "INSUFFICIENT"
            reason = "FACT_RELATION_NOT_ESTABLISHED"
        relation_verdicts.append(
            {
                "entity": sorted(claim_fact.entity),
                "attribute": claim_fact.attribute,
                "value": str(claim_fact.value.value),
                "unit": claim_fact.value.unit,
                "temporal": sorted(claim_fact.temporal),
                "polarity": claim_fact.polarity,
                "status": status,
                "supporting_evidence_ids": sorted(fact_supporting_ids),
                "contradicting_evidence_ids": sorted(fact_contradicting_ids),
                "reason": reason,
            }
        )
        if status == "SUPPORTED":
            supported_ids.update(fact_supporting_ids)
        elif status == "CONTRADICTED":
            contradicted_ids.update(fact_contradicting_ids)
    statuses = {item["status"] for item in relation_verdicts}
    if "CONTRADICTED" in statuses:
        return {
            "status": "CONTRADICTED",
            "evidence_ids": sorted(contradicted_ids),
            "reason": "ENTITY_ATTRIBUTE_VALUE_TIME_OR_POLARITY_CONFLICT",
            "relation_verdicts": relation_verdicts,
        }
    if statuses == {"SUPPORTED"}:
        return {
            "status": "SUPPORTED",
            "evidence_ids": sorted(supported_ids),
            "reason": "EXPLICIT_FACT_RELATION",
            "relation_verdicts": relation_verdicts,
        }
    return {
        "status": "INSUFFICIENT",
        "evidence_ids": [],
        "reason": "FACT_RELATION_NOT_ESTABLISHED",
        "relation_verdicts": relation_verdicts,
    }


def _split_local_clauses(text: str) -> list[str]:
    clauses = [
        part.strip(" -")
        for part in re.split(
            r";|\n+|,\s*(?=(?:Truong|Trường)\s+h(?:op|ợp)|(?:Nam|Năm)\s+\d{4}|(?:Tram|Trạm|Ho|Hồ)\s+)"
            r"|\s+(?=(?:trong\s+khi)\b)|(?<=[.!?])\s+(?=[A-ZÀ-ỸĐ0-9])",
            text,
            flags=re.IGNORECASE,
        )
        if part.strip(" -")
    ]
    return clauses or ([text.strip()] if text.strip() else [])


def _embedded_table_records(text: str) -> tuple[str, list[str]]:
    pattern = re.compile(r"(?<![\w/.,])\d{1,3}\s+(?=[^\W\d_]{1,12}\d{1,4}\b)", flags=re.UNICODE)
    matches = list(pattern.finditer(text))
    if len(matches) < 2:
        return "", []
    prefix = text[:matches[0].start()].strip()
    records = [
        text[match.start():(matches[index + 1].start() if index + 1 < len(matches) else len(text))].strip()
        for index, match in enumerate(matches)
    ]
    return prefix, records


def _build_evidence_scopes(evidence: list[Evidence]) -> list[_EvidenceScope]:
    grouped: dict[str, list[Evidence]] = {}
    ungrouped: list[Evidence] = []
    scopes: list[_EvidenceScope] = []
    for item in evidence:
        if item.unit_type == "TABLE_CELL" or "[Ô BẢNG NGUỒN]" in item.text:
            scopes.append(
                _EvidenceScope(
                    text=item.text,
                    evidence_ids=(item.evidence_id,),
                    kind="table_cell",
                    group=item.context_group or "",
                    row_text=item.text,
                )
            )
        elif item.context_group:
            grouped.setdefault(item.context_group, []).append(item)
        else:
            ungrouped.append(item)
    for group, items in grouped.items():
        items.sort(key=lambda item: (item.page_number, _evidence_block_number(item.evidence_id), item.evidence_id))
        if group.startswith("TABLE:"):
            embedded = False
            for item in items:
                prefix, records = _embedded_table_records(item.text)
                if not records:
                    continue
                embedded = True
                for record in records:
                    scopes.append(
                        _EvidenceScope(
                            text=" ".join(part for part in (prefix, record) if part),
                            evidence_ids=(item.evidence_id,),
                            kind="table_row",
                            group=group,
                            row_text=record,
                            shared_text=prefix,
                        )
                    )
            if embedded:
                for item in items:
                    if not _embedded_table_records(item.text)[1]:
                        for clause in _split_local_clauses(item.text):
                            scopes.append(_EvidenceScope(clause, (item.evidence_id,), "text", group))
                continue
            shared_items = [
                item for item in items
                if item.context_role in {"table_caption", "table_header_or_unit"}
            ]
            shared_text = " ".join(item.text for item in shared_items)
            shared_ids = tuple(item.evidence_id for item in shared_items)
            current_row: list[Evidence] = []
            rows: list[list[Evidence]] = []
            for item in items:
                if item in shared_items:
                    continue
                if item.context_role == "table_row":
                    if current_row:
                        rows.append(current_row)
                    current_row = [item]
                elif current_row:
                    current_row.append(item)
            if current_row:
                rows.append(current_row)
            if rows:
                for row in rows:
                    row_text = " ".join(item.text for item in row)
                    scopes.append(
                        _EvidenceScope(
                            text=" ".join(part for part in (shared_text, row_text) if part),
                            evidence_ids=tuple(dict.fromkeys(shared_ids + tuple(item.evidence_id for item in row))),
                            kind="table_row",
                            group=group,
                            row_text=row_text,
                            shared_text=shared_text,
                        )
                    )
            else:
                for item in items:
                    for clause in _split_local_clauses(item.text):
                        scopes.append(_EvidenceScope(clause, (item.evidence_id,), "text", group))
            continue
        identity_items = [item for item in items if item.context_role == "legal_identity"]
        identity_text = " ".join(item.text for item in identity_items)
        identity_ids = tuple(item.evidence_id for item in identity_items)
        for item in items:
            if item in identity_items:
                continue
            for clause in _split_local_clauses(item.text):
                scopes.append(
                    _EvidenceScope(
                        text=" ".join(part for part in (identity_text, clause) if part),
                        evidence_ids=tuple(dict.fromkeys(identity_ids + (item.evidence_id,))),
                        kind="legal_branch" if item.context_role == "legal_condition" else "text",
                        group=group,
                        row_text=clause,
                        shared_text=identity_text,
                    )
                )
    for item in ungrouped:
        for clause in _split_local_clauses(item.text):
            scopes.append(_EvidenceScope(clause, (item.evidence_id,), "text"))
    unique: list[_EvidenceScope] = []
    seen: set[tuple[str, tuple[str, ...], str]] = set()
    for scope in scopes:
        key = (_ascii_fold(scope.text), scope.evidence_ids, scope.kind)
        if key not in seen:
            seen.add(key)
            unique.append(scope)
    return unique


def _identifier_tokens(text: str) -> set[str]:
    unit_tokens = {"m", "cm", "mm", "m3", "m³", "mg", "mgl", "percent", "diem"}
    return {
        token
        for token in _ascii_fold(text).split()
        if re.search(r"[a-z]", token)
        and re.search(r"\d", token)
        and token not in unit_tokens
    }


def _topic_overlap(claim: str, text: str) -> float:
    claim_tokens = {_ascii_fold(token) for token in _content_tokens(claim)}
    text_tokens = {_ascii_fold(token) for token in _content_tokens(text)}
    return len(claim_tokens & text_tokens) / max(1, len(claim_tokens))


def _table_relation_match(claim: str, scope: _EvidenceScope) -> tuple[bool, dict[str, Any]]:
    claim_facts = _narrative_relations(claim, "claim")
    row_facts = _table_relations(scope)
    if claim_facts:
        pairs = [
            (claim_fact, row_fact)
            for claim_fact in claim_facts
            for row_fact in row_facts
            if _same_entity(claim_fact, row_fact) and claim_fact.attribute == row_fact.attribute
        ]
        return bool(pairs), {
            "relation_pairs": len(pairs),
            "claim_fact_count": len(claim_facts),
            "row_fact_count": len(row_facts),
        }
    claim_tokens = set(_ascii_fold(claim).split())
    row_tokens = set(_ascii_fold(scope.row_text).split())
    shared_tokens = set(_ascii_fold(scope.shared_text).split())
    identifiers = _identifier_tokens(claim)
    if identifiers:
        entity_match = identifiers <= row_tokens
        entity_tokens = identifiers
    else:
        candidates = (
            claim_tokens & row_tokens
            - shared_tokens
            - _RELATION_GENERIC_TOKENS
            - {token for phrase in _MEASUREMENT_TERMS for token in phrase.split()}
        )
        entity_tokens = {token for token in candidates if not token.isdigit() and len(token) >= 3}
        entity_match = bool(entity_tokens)
    attribute_tokens = {
        token
        for phrase in _MEASUREMENT_TERMS
        for token in phrase.split()
        if token in claim_tokens and token in (shared_tokens | row_tokens)
    }
    attribute_match = bool(attribute_tokens) or not shared_tokens
    return entity_match and attribute_match, {
        "entity_tokens": sorted(entity_tokens),
        "attribute_tokens": sorted(attribute_tokens),
        "entity_match": entity_match,
        "attribute_match": attribute_match,
    }


def _table_cell_relation_match(claim: str, scope: _EvidenceScope) -> tuple[bool, dict[str, Any]]:
    overlap = _topic_overlap(claim, scope.row_text or scope.text)
    identifiers = _identifier_tokens(claim)
    identifier_match = not identifiers or identifiers <= _identifier_tokens(scope.text)
    cell_entity = ""
    match_entity = re.search(r"Thực thể:\s*([^|]+)", scope.text)
    if match_entity:
        cell_entity = _plain_fold(match_entity.group(1).strip())
    claim_folded = _plain_fold(claim)
    entity_match = not cell_entity or cell_entity in claim_folded
    match = (overlap >= 0.20 or entity_match) and identifier_match
    return match, {
        "topic_overlap": round(overlap, 6),
        "identifier_match": identifier_match,
        "entity_match": entity_match,
    }


def _scope_relation_match(claim: str, scope: _EvidenceScope) -> tuple[bool, dict[str, Any]]:
    if scope.kind == "table_row":
        return _table_relation_match(claim, scope)
    if scope.kind == "table_cell" or "[Ô BẢNG NGUỒN]" in scope.text:
        return _table_cell_relation_match(claim, scope)
    claim_facts = _narrative_relations(claim, "claim")
    scope_facts = _scope_relations(scope)
    if claim_facts:
        pairs = [
            (claim_fact, evidence_fact)
            for claim_fact in claim_facts
            for evidence_fact in scope_facts
            if _same_entity(claim_fact, evidence_fact) and claim_fact.attribute == evidence_fact.attribute
        ]
        return bool(pairs), {
            "relation_pairs": len(pairs),
            "claim_fact_count": len(claim_facts),
            "scope_fact_count": len(scope_facts),
        }
    overlap = _topic_overlap(claim, scope.row_text or scope.text)
    identifiers = _identifier_tokens(claim)
    identifier_match = not identifiers or identifiers <= _identifier_tokens(scope.text)
    return overlap >= 0.35 and identifier_match, {
        "topic_overlap": round(overlap, 6),
        "identifier_match": identifier_match,
    }


def _condition_verdict(claim: str, scopes: list[_EvidenceScope]) -> dict[str, Any] | None:
    claim_conditions = _condition_mentions(claim)
    evidence_conditions = [(scope, _condition_mentions(scope.row_text or scope.text)) for scope in scopes]
    conditioned_scopes = [(scope, conditions) for scope, conditions in evidence_conditions if conditions]
    if not claim_conditions:
        if len({(condition.operator, condition.value, condition.unit) for _, conditions in conditioned_scopes for condition in conditions}) > 1:
            related = [scope for scope, _ in conditioned_scopes if _topic_overlap(claim, scope.text) >= 0.25]
            if related:
                return {"status": "INSUFFICIENT", "evidence_ids": [], "reason": "CONDITION_MISSING"}
        return None
    matching: list[_EvidenceScope] = []
    conflicting: list[_EvidenceScope] = []
    for scope, conditions in conditioned_scopes:
        if all(any(_condition_entails(item, claim_condition) for item in conditions) for claim_condition in claim_conditions):
            matching.append(scope)
        elif any(_condition_conflicts(claim_condition, item) for claim_condition in claim_conditions for item in conditions):
            conflicting.append(scope)
    supported: list[_EvidenceScope] = []
    contradicted: list[_EvidenceScope] = []
    insufficient_relation = False
    claim_authorities = _authority_markers(claim)
    for scope in matching:
        relation_match, _ = _scope_relation_match(claim, scope)
        evidence_authorities = _authority_markers(scope.row_text or scope.text)
        authority_relation = _authority_relation(claim_authorities, evidence_authorities)
        if authority_relation == "CONTRADICTED":
            contradicted.append(scope)
            continue
        if authority_relation == "INSUFFICIENT":
            insufficient_relation = True
            continue
        legal_relation = _legal_field_relation(claim, scope.row_text or scope.text)
        if legal_relation == "CONTRADICTED":
            contradicted.append(scope)
            continue
        if legal_relation == "INSUFFICIENT":
            insufficient_relation = True
            continue
        semantic_relation = _semantic_relation(claim, scope.row_text or scope.text)[0]
        if semantic_relation == "CONTRADICTED":
            contradicted.append(scope)
        elif relation_match:
            supported.append(scope)
    if supported and contradicted:
        return {"status": "INSUFFICIENT", "evidence_ids": [], "reason": "CONFLICTING_CONDITION_BRANCHES"}
    if supported:
        return {
            "status": "SUPPORTED",
            "evidence_ids": sorted({item for scope in supported for item in scope.evidence_ids}),
            "reason": "MATCHING_CONDITION_BRANCH",
        }
    if contradicted or (conflicting and not matching):
        sources = contradicted or conflicting
        return {
            "status": "CONTRADICTED",
            "evidence_ids": sorted({item for scope in sources for item in scope.evidence_ids}),
            "reason": "CONDITION_OR_AUTHORITY_CONFLICT",
        }
    if insufficient_relation:
        return {"status": "INSUFFICIENT", "evidence_ids": [], "reason": "LEGAL_FIELDS_NOT_ESTABLISHED"}
    return {"status": "INSUFFICIENT", "evidence_ids": [], "reason": "CONDITION_NOT_ESTABLISHED"}


def _numeric_verdict(
    claim: str,
    scopes: list[_EvidenceScope],
    claim_conditions: list[_Condition],
) -> dict[str, Any] | None:
    fact_verdict = _relation_fact_verdict(claim, scopes)
    if fact_verdict is not None:
        return fact_verdict
    claim_temporal = _temporal_markers(claim)
    temporal_years = {
        Decimal(item.split(":")[1])
        for item in claim_temporal
        if item.startswith("year:")
    }
    condition_values = {(item.value, item.unit) for item in claim_conditions}
    claim_mentions = [
        item for item in _numeric_mentions(claim)
        if (item.value, item.unit) not in condition_values
        and not (item.is_year and item.value in temporal_years)
    ]
    if not claim_mentions:
        claim_mentions = [
            item for item in _numeric_mentions(claim)
            if item.is_year and (item.value, item.unit) not in condition_values
        ]
    if not claim_mentions:
        return None
    supported_ids: set[str] = set()
    saw_relation = False
    contradiction_ids: set[str] = set()
    insufficient = False
    for mention in claim_mentions:
        mention_supported = False
        mention_contradicted = False
        for scope in scopes:
            relation_match, _ = _scope_relation_match(claim, scope)
            if not relation_match:
                continue
            saw_relation = True
            scope_mentions = _numeric_mentions(re.sub(r"^\s*\d{1,3}\s+", "", scope.row_text or scope.text))
            scope_temporal = _temporal_markers(scope.text)
            t_verdict = _temporal_verdict(claim_temporal, scope_temporal)
            if t_verdict == "CONTRADICTED":
                mention_contradicted = True
                contradiction_ids.update(scope.evidence_ids)
                continue
            elif t_verdict == "INSUFFICIENT" and scope.kind != "table_cell":
                insufficient = True
                continue
            same_value = [item for item in scope_mentions if item.value == mention.value]
            scope_units = _units(scope.text)
            if mention.unit and mention.unit != "year":
                compatible = [
                    item for item in same_value
                    if item.unit == mention.unit or (not item.unit and scope_units == {mention.unit})
                ]
                incompatible = [item for item in same_value if item.unit and item.unit != mention.unit]
            else:
                compatible = same_value
                incompatible = []
            if compatible:
                mention_supported = True
                supported_ids.update(scope.evidence_ids)
            elif incompatible:
                mention_contradicted = True
                contradiction_ids.update(scope.evidence_ids)
            elif scope_mentions:
                comparable = [
                    item for item in scope_mentions
                    if mention.unit in {"", "year"}
                    or item.unit == mention.unit
                    or (not item.unit and scope_units == {mention.unit})
                ]
                if comparable:
                    mention_contradicted = True
                    contradiction_ids.update(scope.evidence_ids)
                else:
                    insufficient = True
            else:
                insufficient = True
        if mention_supported and mention_contradicted:
            return {"status": "INSUFFICIENT", "evidence_ids": [], "reason": "CONFLICTING_NUMERIC_RECORDS"}
        if mention_contradicted and not mention_supported:
            return {
                "status": "CONTRADICTED",
                "evidence_ids": sorted(contradiction_ids),
                "reason": "ENTITY_VALUE_UNIT_OR_TIME_CONFLICT",
            }
        if not mention_supported:
            insufficient = True
    if supported_ids and not insufficient:
        return {"status": "SUPPORTED", "evidence_ids": sorted(supported_ids), "reason": "LOCAL_NUMERIC_RELATION"}
    if saw_relation:
        return {"status": "INSUFFICIENT", "evidence_ids": [], "reason": "NUMERIC_RELATION_INCOMPLETE"}
    return {"status": "INSUFFICIENT", "evidence_ids": [], "reason": "NUMERIC_SUBJECT_NOT_FOUND"}


def _semantic_verdict(claim: str, scopes: list[_EvidenceScope]) -> dict[str, Any] | None:
    if not _semantic_assertions(claim):
        return None
    aligned: list[_EvidenceScope] = []
    contradicted: list[_EvidenceScope] = []
    for scope in scopes:
        if _topic_overlap(claim, scope.row_text or scope.text) < 0.25:
            continue
        relation = _semantic_relation(claim, scope.row_text or scope.text)[0]
        if relation == "ALIGNED":
            aligned.append(scope)
        elif relation == "CONTRADICTED":
            contradicted.append(scope)
    if aligned and contradicted:
        return {"status": "INSUFFICIENT", "evidence_ids": [], "reason": "CONFLICTING_SEMANTIC_ASSERTIONS"}
    if aligned:
        return {
            "status": "SUPPORTED",
            "evidence_ids": sorted({item for scope in aligned for item in scope.evidence_ids}),
            "reason": "LOCAL_SEMANTIC_ALIGNMENT",
        }
    if contradicted:
        return {
            "status": "CONTRADICTED",
            "evidence_ids": sorted({item for scope in contradicted for item in scope.evidence_ids}),
            "reason": "LOCAL_SEMANTIC_CONTRADICTION",
        }
    return {"status": "INSUFFICIENT", "evidence_ids": [], "reason": "SEMANTIC_ASSERTION_NOT_ESTABLISHED"}


def _claim_grounding_assessment(claim: str, evidence: list[Evidence]) -> dict[str, Any]:
    scopes = _build_evidence_scopes(evidence)
    evidence_text = " ".join(scope.text for scope in scopes)
    lexical_support, overlap, evidence_ids = _claim_support(claim, evidence)
    _, semantic_detail = _semantic_relation(claim, evidence_text)
    normalized_claim = _ascii_fold(claim)
    phrase_similarity = _character_ngram_dice(claim, evidence_text)
    exact_scopes = [scope for scope in scopes if normalized_claim and normalized_claim in _ascii_fold(scope.text)]
    detectors = [
        detector for detector in (
            _condition_verdict(claim, scopes),
            _numeric_verdict(claim, scopes, _condition_mentions(claim)),
            _semantic_verdict(claim, scopes),
        )
        if detector is not None
    ]
    if exact_scopes:
        detectors.append(
            {
                "status": "SUPPORTED",
                "evidence_ids": sorted({item for scope in exact_scopes for item in scope.evidence_ids}),
                "reason": "EXACT_LOCAL_STATEMENT",
            }
        )
    statuses = {item["status"] for item in detectors}
    if "CONTRADICTED" in statuses:
        status = "CONTRADICTED"
    elif "INSUFFICIENT" in statuses or not detectors:
        status = "INSUFFICIENT"
    elif statuses == {"SUPPORTED"}:
        status = "SUPPORTED"
    else:
        status = "INSUFFICIENT"
    supporting_ids = sorted(
        {
            evidence_id
            for detector in detectors
            if detector["status"] == "SUPPORTED"
            for evidence_id in detector["evidence_ids"]
        }
    )
    contradicting_ids = sorted(
        {
            evidence_id
            for detector in detectors
            if detector["status"] == "CONTRADICTED"
            for evidence_id in detector["evidence_ids"]
        }
    )
    return {
        "claim": claim,
        "status": status,
        "best_content_overlap": round(overlap, 6),
        "phrase_similarity": round(phrase_similarity, 6),
        "nearest_evidence_ids": evidence_ids,
        "supporting_evidence_ids": supporting_ids,
        "contradicting_evidence_ids": contradicting_ids,
        "detectors": detectors,
        "scope_count": len(scopes),
        "legacy_status": "UNVERIFIED" if status == "INSUFFICIENT" else status,
        "lexical_candidate_only": lexical_support and status != "SUPPORTED",
        **semantic_detail,
    }


def enforce_citation_grounding(
    generation: GenerationResult,
    context: ContextBuild,
) -> tuple[GenerationResult, dict[str, Any]]:
    """Reject unsupported answers and retain only claim-relevant citations.

    The guard never invents or replaces a citation. It either keeps an exact
    context citation emitted by the model or returns a grounded abstention.
    """
    audit: dict[str, Any] = {
        "original_citation_count": len(generation.citations),
        "retained_citation_count": 0,
        "invalid_citation_count": 0,
        "irrelevant_citation_count": 0,
        "unsupported_claims": [],
        "claim_support": [],
        "support_status": "UNVERIFIED",
        "action": "PASS",
        "reason": "",
    }

    folded_answer = _ascii_fold(generation.answer)
    refusal = "khong du bang chung" in folded_answer or (
        generation.abstained and len(_content_tokens(generation.answer)) <= 3
    )
    if refusal:
        result = GenerationResult(
            answer=REFUSAL_TEXT,
            citations=[],
            abstained=True,
            abstention_reason=generation.abstention_reason or "Evidence không đủ để trả lời.",
            evidence_supported=False,
            parse_error=generation.parse_error,
            raw_response=generation.raw_response,
        )
        audit.update({"action": "ABSTAIN", "reason": "MODEL_ABSTAINED"})
        return result, audit

    if generation.abstained:
        result = GenerationResult(
            answer=generation.answer.strip(),
            citations=[],
            abstained=True,
            abstention_reason=generation.abstention_reason or "Cần thêm thông tin câu hỏi.",
            evidence_supported=False,
            parse_error=generation.parse_error,
            raw_response=generation.raw_response,
        )
        audit.update({"action": "ABSTAIN", "reason": "MODEL_ABSTAINED"})
        return result, audit

    def grounded_abstention(
        reason: str,
        unsupported: list[str] | None = None,
        support_status: str = "UNVERIFIED",
    ) -> tuple[GenerationResult, dict[str, Any]]:
        audit.update(
            {
                "action": "ABSTAIN",
                "reason": reason,
                "unsupported_claims": unsupported or [],
                "retained_citation_count": 0,
                "support_status": support_status,
            }
        )
        return (
            GenerationResult(
                answer=REFUSAL_TEXT,
                citations=[],
                abstained=True,
                abstention_reason=f"P5 grounding guard: {reason}",
                evidence_supported=False,
                parse_error=generation.parse_error,
                raw_response=generation.raw_response,
            ),
            audit,
        )

    if generation.parse_error:
        return grounded_abstention("PARSE_ERROR")
    claims = _answer_claims(generation.answer)
    if not claims:
        return grounded_abstention("NO_SUBSTANTIVE_CLAIM")

    by_key = {item.citation_key(): item for item in context.evidence}
    for item in context.evidence:
        if (item.unit_type == "TABLE_CELL" or "_R" in item.evidence_id) and "_R" in item.evidence_id:
            parent_table_id = item.evidence_id.split("_R")[0]
            by_key.setdefault((item.doc_id, item.page_number, parent_table_id), item)
    valid_pairs: list[tuple[dict[str, Any], Evidence]] = []
    for citation in generation.citations:
        key = (citation["doc_id"], citation["page_number"], citation["evidence_id"])
        item = by_key.get(key)
        if item is None:
            audit["invalid_citation_count"] += 1
        else:
            valid_pairs.append((citation, item))
    if not valid_pairs:
        return grounded_abstention("NO_EXACT_CONTEXT_CITATION")

    directly_relevant_ids: set[str] = set()
    for _, item in valid_pairs:
        for claim in claims:
            overlap = _claim_support(claim, [item])[1]
            claim_numbers = _numbers(claim)
            item_numbers = _numbers(item.text)
            numeric_support = bool(claim_numbers) and (
                claim_numbers <= item_numbers
                or bool(claim_numbers & item_numbers)
            )
            phrase_threshold = 0.30 + min(0.12, len(item.text) / 20000)
            phrase_support = _character_ngram_dice(claim, item.text) >= phrase_threshold
            semantic_relation = _semantic_relation(claim, item.text)[0]
            table_support = (
                item.context_role in {"table_caption", "table_header_or_unit", "table_row"}
                or item.unit_type == "TABLE_CELL"
            ) and bool(claim_numbers & item_numbers)
            table_cell_val_mismatch = False
            if item.unit_type == "TABLE_CELL":
                val_m = re.search(r"Giá trị:\s*([^\s;]+)", item.text)
                if val_m:
                    val_nums = _numbers(val_m.group(1))
                    if val_nums and not (val_nums & claim_numbers):
                        table_cell_val_mismatch = True
                        numeric_support = False
                        table_support = False
            if not table_cell_val_mismatch and overlap >= 0.10 and (
                phrase_support
                or numeric_support
                or table_support
                or semantic_relation in {"ALIGNED", "CONTRADICTED"}
            ):
                directly_relevant_ids.add(item.evidence_id)
                break
    relevant_groups = {
        item.context_group
        for _, item in valid_pairs
        if item.evidence_id in directly_relevant_ids and item.context_group
    }
    retained_pairs = []
    for citation, item in valid_pairs:
        structural_support = (
            item.context_group in relevant_groups
            and item.context_role in {"table_caption", "table_header_or_unit", "table_row", "legal_condition"}
        )
        if item.evidence_id in directly_relevant_ids or structural_support:
            retained_pairs.append((citation, item))
        else:
            audit["irrelevant_citation_count"] += 1
    if not retained_pairs:
        return grounded_abstention("CITATIONS_DO_NOT_SUPPORT_ANY_CLAIM", support_status="INSUFFICIENT")

    cited_evidence = [item for _, item in retained_pairs]
    claim_support = [_claim_grounding_assessment(claim, cited_evidence) for claim in claims]
    audit["claim_support"] = claim_support
    contradicted = [item["claim"] for item in claim_support if item["status"] == "CONTRADICTED"]
    if contradicted:
        return grounded_abstention(
            "CONTRADICTED_ANSWER_CLAIM",
            contradicted,
            support_status="CONTRADICTED",
        )
    unverified = [item["claim"] for item in claim_support if item["status"] != "SUPPORTED"]
    if unverified:
        return grounded_abstention(
            "UNVERIFIED_ANSWER_CLAIM",
            unverified,
            support_status="INSUFFICIENT",
        )

    supporting_ids = {
        evidence_id
        for assessment in claim_support
        for evidence_id in assessment["supporting_evidence_ids"]
    }
    final_pairs = [
        pair for pair in retained_pairs
        if pair[1].evidence_id in supporting_ids
        or (pair[1].unit_type == "TABLE_CELL" and pair[1].evidence_id.split("_R")[0] in supporting_ids)
        or (pair[0]["evidence_id"] in supporting_ids)
    ]
    audit["irrelevant_citation_count"] += len(retained_pairs) - len(final_pairs)
    if not final_pairs:
        return grounded_abstention("CITATIONS_DO_NOT_SUPPORT_ANY_CLAIM")
    retained_citations = [citation for citation, _ in final_pairs]
    audit["retained_citation_count"] = len(retained_citations)
    audit["support_status"] = "SUPPORTED"
    result = GenerationResult(
        answer=generation.answer,
        citations=retained_citations,
        abstained=False,
        abstention_reason="",
        evidence_supported=True,
        parse_error=generation.parse_error,
        raw_response=generation.raw_response,
    )
    return result, audit


def evaluate_answer(
    generation: GenerationResult,
    reference_answer: str,
    context: ContextBuild,
    evidence_sufficiency: str,
) -> dict[str, Any]:
    f1 = token_f1(reference_answer, generation.answer)
    recall = content_recall(reference_answer, generation.answer)
    number_recall = numeric_recall(reference_answer, generation.answer)
    context_body = " ".join(item.text for item in context.evidence)
    reference_context_recall = content_recall(reference_answer, context_body)
    reference_context_numeric = numeric_recall(reference_answer, context_body)
    if reference_context_recall >= 0.35 and reference_context_numeric == 1.0:
        reference_context_support = "LIKELY_PRESENT"
    elif reference_context_recall >= 0.20 and reference_context_numeric >= 0.5:
        reference_context_support = "PARTIAL"
    else:
        reference_context_support = "NOT_DEMONSTRATED"
    folded_answer = _ascii_fold(generation.answer)
    refusal_answer = folded_answer == _ascii_fold(REFUSAL_TEXT) or "khong du bang chung" in folded_answer
    effective_abstention = refusal_answer or (
        generation.abstained and len(_content_tokens(generation.answer)) <= 3
    )
    semantic = _semantic_assessment(reference_answer, generation.answer, recall, number_recall, f1)
    if effective_abstention:
        correctness = "ABSTAIN"
        semantic["semantic_correctness"] = "ABSTAIN"
        semantic["content_completeness"] = "INCOMPLETE"
    elif semantic["semantic_correctness"] == "MATCH":
        correctness = "PROVISIONAL_MATCH"
    elif semantic["semantic_correctness"] == "SEMANTIC_MATCH":
        correctness = "PROVISIONAL_SEMANTIC_MATCH"
    elif semantic["semantic_correctness"] == "PARTIAL":
        correctness = "PROVISIONAL_PARTIAL"
    else:
        correctness = "PROVISIONAL_MISMATCH"

    valid_keys = {item.citation_key() for item in context.evidence}
    valid_citations: list[dict[str, Any]] = []
    invalid_citations: list[dict[str, Any]] = []
    for citation in generation.citations:
        key = (citation["doc_id"], citation["page_number"], citation["evidence_id"])
        (valid_citations if key in valid_keys else invalid_citations).append(citation)
    if not context.evidence:
        citation_validity = "NOT_APPLICABLE" if not generation.citations else "INVALID"
    elif effective_abstention and not generation.citations:
        citation_validity = "NOT_APPLICABLE"
    elif not generation.citations:
        citation_validity = "MISSING"
    elif valid_citations and not invalid_citations:
        citation_validity = "VALID"
    elif valid_citations:
        citation_validity = "PARTIAL"
    else:
        citation_validity = "INVALID"

    claims = _answer_claims(generation.answer)
    unsupported_claims: list[dict[str, Any]] = []
    supported_count = 0
    if effective_abstention:
        claims = []
    for claim in claims:
        supported, overlap, evidence_ids = _claim_support(claim, context.evidence)
        if supported:
            supported_count += 1
        else:
            unsupported_claims.append(
                {"claim": claim, "best_content_overlap": round(overlap, 6), "nearest_evidence_ids": evidence_ids}
            )
    faithfulness = supported_count / len(claims) if claims else (1.0 if generation.abstained else 0.0)
    if effective_abstention:
        evidence_support = "NOT_ASSESSED"
    elif not context.evidence:
        evidence_support = "NO_SUPPLIED_EVIDENCE"
    elif faithfulness >= 0.8 and citation_validity in {"VALID", "NOT_APPLICABLE"}:
        evidence_support = "HIGH"
    elif faithfulness >= 0.5:
        evidence_support = "PARTIAL"
    else:
        evidence_support = "LOW"

    cited_evidence = [
        item for item in context.evidence if item.citation_key() in {
            (citation["doc_id"], citation["page_number"], citation["evidence_id"])
            for citation in valid_citations
        }
    ]
    cited_claim_assessments = [_claim_support(claim, cited_evidence) for claim in claims]
    cited_claim_support = [assessment[0] for assessment in cited_claim_assessments]
    if not generation.citations:
        citation_claim_support = "NOT_APPLICABLE" if effective_abstention else "MISSING"
    elif not cited_evidence:
        citation_claim_support = "UNSUPPORTED"
    elif cited_claim_support and all(cited_claim_support):
        citation_claim_support = "SUPPORTED"
    elif any(cited_claim_support) or any(
        assessment[1] >= 0.10 for assessment in cited_claim_assessments
    ):
        citation_claim_support = "PARTIAL"
    else:
        citation_claim_support = "UNSUPPORTED"
    citation_relevance_flags = []
    for item in cited_evidence:
        citation_relevance_flags.append(any(_claim_support(claim, [item])[1] >= 0.15 for claim in claims))
    if not cited_evidence:
        citation_relevance = "NOT_APPLICABLE"
    elif all(citation_relevance_flags):
        citation_relevance = "ALL_RELEVANT"
    elif any(citation_relevance_flags):
        citation_relevance = "PARTIAL"
    else:
        citation_relevance = "NONE_RELEVANT"

    abstention_expected = evidence_sufficiency in {"NONE", "INSUFFICIENT"}
    if effective_abstention == abstention_expected:
        abstention_behavior = "EXPECTED"
    elif effective_abstention:
        abstention_behavior = "OVER_ABSTENTION"
    else:
        abstention_behavior = "FAILED_TO_ABSTAIN"
    abstention_flag_consistency = (
        "CONSISTENT" if generation.abstained == effective_abstention else "INCONSISTENT"
    )
    rationale = (
        f"Multi-axis exploratory rubric: semantic={semantic['semantic_correctness']}, "
        f"completeness={semantic['content_completeness']}, token_f1={f1:.3f}, "
        f"content_recall={recall:.3f}, numeric_recall={number_recall:.3f}; "
        f"evidence_support={evidence_support}; citation_id={citation_validity}; "
        f"citation_claim_support={citation_claim_support}. No official accuracy claim."
    )
    return {
        "token_f1": round(f1, 6),
        "content_recall": round(recall, 6),
        "numeric_recall": round(number_recall, 6),
        "reference_context_content_recall": round(reference_context_recall, 6),
        "reference_context_numeric_recall": round(reference_context_numeric, 6),
        "reference_context_support": reference_context_support,
        "provisional_correctness": correctness,
        **semantic,
        "citation_validity": citation_validity,
        "citation_id_validity": citation_validity,
        "citation_claim_support": citation_claim_support,
        "citation_relevance": citation_relevance,
        "valid_citations": valid_citations,
        "invalid_citations": invalid_citations,
        "faithfulness_score": round(faithfulness, 6),
        "evidence_support": evidence_support,
        "unsupported_claims": unsupported_claims,
        "abstention_expected": abstention_expected,
        "abstention_behavior": abstention_behavior,
        "effective_abstention": effective_abstention,
        "abstention_flag_consistency": abstention_flag_consistency,
        "evaluation_rationale": rationale,
    }
