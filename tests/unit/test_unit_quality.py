import unittest

from simplicio_loop_quality.unit_quality import discover_unit_suites, normalize_unit_results, plan_unit_tests


class UnitQualityTest(unittest.TestCase):
    def test_python_suite_is_discovered(self):
        suites = discover_unit_suites({"files": ["pyproject.toml", "src/app.py", "tests/test_app.py"]})
        self.assertEqual(suites[0].framework, "pytest")

    def test_no_suite_and_empty_results_block(self):
        plan = plan_unit_tests({"files": ["README.md"]}, source_sha="a", policy_hash="p")
        self.assertEqual(plan.status, "BLOCKED")
        result = normalize_unit_results([], source_sha="a", policy_hash="p")
        self.assertEqual(result["status"], "BLOCKED")

    def test_missing_evidence_cannot_pass(self):
        result = normalize_unit_results([{"test_id": "test_a", "status": "PASS", "duration_ms": 4}], source_sha="a", policy_hash="p")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("EVIDENCE_MISSING", result["results"][0]["reason_codes"])


if __name__ == "__main__":
    unittest.main()
