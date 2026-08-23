import unittest

from simplicio_loop_quality.release_candidate import (
    REQUIRED_CHECKS,
    evaluate_release_candidate,
)


def candidate():
    return {
        "version": "0.1.0",
        "source_sha": "source",
        "artifacts": [{"name": "package.whl", "sha256": "digest", "size": 100}],
        "sbom": "sbom.json",
        "provenance": "provenance.json",
        "signature": "signature",
        "checks": {name: True for name in REQUIRED_CHECKS},
    }


class ReleaseCandidateTest(unittest.TestCase):
    def test_complete_candidate_passes(self):
        self.assertEqual(evaluate_release_candidate(candidate())["status"], "PASS")

    def test_tamper_check_fails_closed(self):
        value = candidate()
        value["checks"]["tamper_detection"] = False
        result = evaluate_release_candidate(value)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("TAMPER_DETECTION_FAILED", result["reason_codes"])

    def test_missing_clean_install_is_blocked(self):
        value = candidate()
        value["checks"]["clean_install"] = None
        result = evaluate_release_candidate(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("CLEAN_INSTALL_UNAVAILABLE", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
