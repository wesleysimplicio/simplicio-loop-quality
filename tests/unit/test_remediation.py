import unittest

from simplicio_loop_quality.remediation import normalize_findings, reverify


class RemediationTest(unittest.TestCase):
    def test_duplicate_findings_are_fingerprinted_once(self):
        items = [{"path": "a.py", "rule": "E1", "detail": "bad"}, {"path": "a.py", "rule": "E1", "detail": "bad"}]
        self.assertEqual(len(normalize_findings(items, source_sha="s")), 1)

    def test_reverification_resolves_or_reopens_and_stale_blocks(self):
        request = normalize_findings([{"detail": "bad"}], source_sha="s")[0]
        self.assertEqual(reverify(request, candidate_status="PASS", candidate_source_sha="s").status, "RESOLVED")
        self.assertEqual(reverify(request, candidate_status="FAIL", candidate_source_sha="s").status, "REOPENED")
        self.assertEqual(reverify(request, candidate_status="PASS", candidate_source_sha="new").status, "STALE")


if __name__ == "__main__":
    unittest.main()
