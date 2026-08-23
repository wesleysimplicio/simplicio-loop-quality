import unittest

from simplicio_loop_quality.static_quality import discover_analyzers, normalize_findings, plan_static_quality


class StaticQualityTest(unittest.TestCase):
    def test_python_analyzer_is_discovered_and_pinned(self):
        plan = plan_static_quality({"files": ["src/app.py"], "tools": {"ruff_version": "0.6"}}, source_sha="a", policy_hash="p")
        self.assertEqual(plan.status, "PLANNED")
        self.assertEqual(plan.analyzers[0].version_pin, "0.6")

    def test_tool_absence_is_blocked(self):
        plan = plan_static_quality({"files": ["README.md"], "tools": {}}, source_sha="a", policy_hash="p")
        self.assertEqual(plan.status, "BLOCKED")
        self.assertIn("STATIC_TOOLS_UNAVAILABLE", plan.reason_codes)

    def test_findings_are_normalized_and_not_a_pass(self):
        result = normalize_findings([{"tool": "ruff", "rule": "E501", "path": "src/app.py", "line": 3, "message": "long"}], source_sha="a", policy_hash="p")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["findings"][0]["line"], 3)


if __name__ == "__main__":
    unittest.main()
