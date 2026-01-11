import os
import unittest

from searchbench.judge import Judge


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

    def test_fallback_number_equivalence(self):
        judge = Judge(model="test-model")
        result = judge._fallback(["4"], "four", [], "test")
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
