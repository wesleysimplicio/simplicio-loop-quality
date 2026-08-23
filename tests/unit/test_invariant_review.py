import unittest

from simplicio_loop_quality.invariant_review import review_invariants


class InvariantReviewTest(unittest.TestCase):
    def test_evidence_backed_invariants_pass(self):
        result = review_invariants([{"name": "no-local-scheduler", "status": "PASS", "evidence_ref": "ev"}])
        self.assertEqual(result.status, "PASS")

    def test_violation_and_missing_evidence_are_not_pass(self):
        result = review_invariants([{"name": "fail-closed", "status": "FAIL"}])
        self.assertEqual(result.status, "FAIL")
        self.assertIn("INVARIANT_EVIDENCE_MISSING", result.reason_codes)

    def test_empty_invariants_block(self):
        self.assertEqual(review_invariants([]).status, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
