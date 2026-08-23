import unittest

from simplicio_loop_quality.regression_quality import prove_regression


class RegressionQualityTest(unittest.TestCase):
    def test_fail_before_pass_after_is_required_for_pass(self):
        result = prove_regression([{"case_id": "bug-1", "baseline_status": "FAIL", "candidate_status": "PASS", "baseline_fingerprint": "b", "candidate_fingerprint": "c", "evidence_refs": ["ev"]}], source_sha="a", policy_hash="p")
        self.assertEqual(result.status, "PASS")

    def test_no_baseline_or_evidence_cannot_be_called_regression_proof(self):
        result = prove_regression([{"case_id": "bug-1", "baseline_status": "PASS", "candidate_status": "PASS"}], source_sha="a", policy_hash="p")
        self.assertEqual(result.status, "FAIL")
        self.assertIn("FAIL_BEFORE_NOT_PROVEN", result.reason_codes)

    def test_empty_regression_matrix_is_blocked(self):
        self.assertEqual(prove_regression([], source_sha="a", policy_hash="p").status, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
