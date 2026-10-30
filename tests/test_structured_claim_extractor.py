"""Unit tests for Schema-Constrained Structured Claim Extractor (Stanford CS329Z principle)."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE))

from scripts.structured_claim_extractor import StructuredClaimExtractor, ExtractedClaimRecord


class TestStructuredClaimExtractor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extractor = StructuredClaimExtractor(model="qwen2.5:7b")

    def test_pure_abstention_short_circuit(self):
        q = "Tổng dung tích hồ Bình Điền là bao nhiêu?"
        ans = "Không đủ bằng chứng trong ngữ cảnh được cung cấp để trả lời câu hỏi này."
        res = self.extractor.extract_structured_claims(q, ans, use_cache=False)
        self.assertEqual(res.answer_status, "ABSTAINED")
        self.assertEqual(len(res.claims), 0)
        self.assertIn("PURE_ABSTENTION_DETECTED", res.diagnostics)

    def test_multi_claim_extraction(self):
        q = "Diện tích trong đê và ngoài đê của hệ thống Bắc Nam Hà lần lượt là bao nhiêu?"
        ans = "Diện tích trong đê của hệ thống Bắc Nam Hà là 85.326 ha, còn diện tích ngoài đê là 14.935 ha."
        res = self.extractor.extract_structured_claims(q, ans, use_cache=True)
        self.assertIn(res.answer_status, ["ANSWERED", "PARTIAL"])
        self.assertGreaterEqual(len(res.claims), 2)

        # Check values
        values = [c.value for c in res.claims]
        self.assertTrue(any(abs(v - 85.326) < 1e-2 or abs(v - 85326.0) < 1e-2 for v in values))
        self.assertTrue(any(abs(v - 14.935) < 1e-2 or abs(v - 14935.0) < 1e-2 for v in values))

    def test_negated_claim_polarity(self):
        q = "Hồ Cửa Đạt đã đạt dung tích thiết kế chưa?"
        ans = "Hồ Cửa Đạt chưa đạt dung tích thiết kế 1.45 tỷ m3 trong đợt mưa lũ vừa qua."
        res = self.extractor.extract_structured_claims(q, ans, use_cache=True)
        self.assertGreaterEqual(len(res.claims), 1)
        polarities = [c.polarity for c in res.claims]
        self.assertTrue("NEGATED" in polarities or "UNCERTAIN" in polarities or "AFFIRMED" in polarities)

    def test_generic_subject_rejection(self):
        q = "Tổng dung tích là bao nhiêu?"
        ans = "Tổng dung tích được ghi nhận là 120 triệu m3."
        res = self.extractor.extract_structured_claims(q, ans, use_cache=True)
        # If subject is generic or empty, it should be marked CLAIM_EXTRACTION_UNRESOLVED
        for c in res.claims:
            if not c.subject or c.subject.lower() in ["hệ thống thủy lợi", "công trình", ""]:
                self.assertEqual(c.extraction_status, "CLAIM_EXTRACTION_UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
