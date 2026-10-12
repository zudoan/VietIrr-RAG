import re

class AnswerComponentExtractorV24:
    """
    V2.4 Answer Component Extractor.
    Takes ONLY (question, reference_answer).
    NEVER takes gold evidence or evidence count.
    Decomposes the QA pair into real, explicit domain requirements.
    """
    def __init__(self):
        pass

    def extract_components(self, question, answer):
        """
        Input: question, reference_answer
        Output:
        {
            "components": [
                {
                    "component_id": "C1",
                    "requirement": "...",
                    "expected_answer_content": "..."
                }
            ]
        }
        """
        components = []
        q_strip = question.strip()
        a_strip = answer.strip()

        # 1. Check for numbered clauses: (1) ... (2) ... (3) ...
        # in question and answer
        q_clauses = re.findall(r'\(([1-4])\)\s*([^;?]+)', q_strip)
        a_clauses = re.findall(r'\(([1-4])\)\s*([^;.]+)', a_strip)

        if len(q_clauses) >= 2 and len(a_clauses) >= 2:
            a_dict = {c[0]: c[1].strip() for c in a_clauses}
            for c_num, c_req in q_clauses:
                req_text = c_req.strip()
                ans_text = a_dict.get(c_num, req_text)
                components.append({
                    "component_id": f"C{c_num}",
                    "requirement": req_text,
                    "expected_answer_content": ans_text
                })
            return {"components": components}

        # 2. Check for compound conjunctions in Question:
        # e.g., "cho biết X kèm theo Y" or "đối chiếu X với Y" or "X và định hướng Y"
        compound_patterns = [
            r'^(.*?)\s+kèm theo\s+(.*?)$',
            r'^(.*?)\s+đồng thời\s+(.*?)$',
            r'^(.*?)\s+và\s+(?:nội dung|định hướng|biện pháp|giải pháp|phân tích)\s+(.*?)$',
            r'^.*?đối chiếu\s+(.*?)\s+với\s+(.*?)$',
        ]

        found_split = None
        for pat in compound_patterns:
            m = re.search(pat, q_strip, re.IGNORECASE)
            if m:
                part1, part2 = m.group(1).strip(), m.group(2).strip()
                if len(part1) > 10 and len(part2) > 10:
                    found_split = (part1, part2)
                    break

        if found_split:
            part1, part2 = found_split
            # Check if answer also has two clear parts
            if "(1)" in a_strip and "(2)" in a_strip:
                a_parts = re.findall(r'\(([1-2])\)\s*([^;.]+)', a_strip)
                a1 = a_parts[0][1].strip() if len(a_parts) > 0 else a_strip[:len(a_strip)//2]
                a2 = a_parts[1][1].strip() if len(a_parts) > 1 else a_strip[len(a_strip)//2:]
            else:
                a1 = a_strip
                a2 = a_strip

            components.append({
                "component_id": "C1",
                "requirement": part1,
                "expected_answer_content": a1
            })
            components.append({
                "component_id": "C2",
                "requirement": part2,
                "expected_answer_content": a2
            })
            return {"components": components}

        # 3. Single requirement QA
        # Extract main domain question intent
        components.append({
            "component_id": "C1",
            "requirement": q_strip,
            "expected_answer_content": a_strip
        })
        return {"components": components}
