import unittest

from simplicio_loop_quality.completeness import evaluate_completeness


class CompletenessTest(unittest.TestCase):
    def test_complete_criterion_passes(self):
        result = evaluate_completeness([{"criterion_id": "AC-1", "implementation_refs": ["src/a.py"], "test_refs": ["tests/test_a.py"], "evidence_refs": ["ev-1"]}], source_sha="a", policy_hash="p")
        self.assertEqual(result.status, "PASS")

    def test_missing_implementation_test_or_evidence_blocks(self):
        result = evaluate_completeness([{"criterion_id": "AC-1", "implementation_refs": [], "test_refs": [], "evidence_refs": []}], source_sha="a", policy_hash="p")
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(set(result.criteria[0].reason_codes), {"IMPLEMENTATION_MISSING", "TEST_MISSING", "EVIDENCE_MISSING"})

    def test_empty_criteria_is_not_complete(self):
        self.assertEqual(evaluate_completeness([], source_sha="a", policy_hash="p").status, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
