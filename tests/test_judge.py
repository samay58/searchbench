import os
import unittest

from searchbench.judge import Judge
from searchbench.queries import EvidenceRequirement


class TestJudge(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("OPENAI_API_KEY", "test-key")

    def test_parse_verdict_correct(self):
        judge = Judge(model="test-model")
        verdict = judge._parse_verdict("CORRECT: matches expected", True)
        self.assertEqual(verdict, ("correct", "matches expected"))

    def test_parse_verdict_plausible(self):
        judge = Judge(model="test-model")
        verdict = judge._parse_verdict("PLAUSIBLE: cites sources", False)
        self.assertEqual(verdict, ("plausible", "cites sources"))

    def test_evidence_gate_missing_domain(self):
        evidence = EvidenceRequirement(min_citations=1, required_domains=("sec.gov",))
        passed, notes = Judge._check_evidence(["https://example.com"], evidence)
        self.assertFalse(passed)
        self.assertIn("missing domains", notes)

    def test_evidence_gate_min_citations(self):
        evidence = EvidenceRequirement(min_citations=2)
        passed, notes = Judge._check_evidence(["https://sec.gov"], evidence)
        self.assertFalse(passed)
        self.assertIn("only 1 citation", notes)

    def test_fallback_number_equivalence(self):
        judge = Judge(model="test-model")
        result = judge._fallback(["4"], "four", [], "test")
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
