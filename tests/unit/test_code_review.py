import unittest

from simplicio_loop_quality.code_review import review_diff


class CodeReviewTest(unittest.TestCase):
    def test_independent_clean_review_passes(self):
        self.assertEqual(review_diff([], reviewer_id="reviewer", author_id="author", source_sha="sha", diff_source_sha="sha").status, "PASS")

    def test_self_review_stale_diff_and_unsupported_claim_fail(self):
        result = review_diff([{"finding_id": "f", "severity": "suggestion", "detail": "check"}], reviewer_id="author", author_id="author", source_sha="new", diff_source_sha="old")
        self.assertEqual(result.status, "FAIL")
        self.assertIn("SELF_REVIEW_FORBIDDEN", result.reason_codes)
        self.assertIn("STALE_DIFF", result.reason_codes)
        self.assertIn("UNSUPPORTED_CLAIM", result.reason_codes)

    def test_blocking_finding_fails_even_with_evidence(self):
        result = review_diff([{"finding_id": "f", "severity": "blocking", "evidence_ref": "ev", "detail": "bad"}], reviewer_id="reviewer", author_id="author", source_sha="sha", diff_source_sha="sha")
        self.assertEqual(result.status, "FAIL")
        self.assertIn("BLOCKING_FINDINGS", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
