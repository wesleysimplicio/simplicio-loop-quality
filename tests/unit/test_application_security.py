import unittest

from simplicio_loop_quality.application_security import normalize_security_findings, plan_security


class ApplicationSecurityTest(unittest.TestCase):
    def test_security_tools_plan_checks(self):
        plan = plan_security({"files": ["src/app.py"], "tools": ["semgrep"]})
        self.assertEqual(plan.status, "PLANNED")
        self.assertIn("secret_scan", plan.checks)

    def test_tool_absence_blocks(self):
        self.assertEqual(plan_security({"files": ["src/app.py"]}).status, "BLOCKED")

    def test_finding_is_fail(self):
        self.assertEqual(normalize_security_findings([{"rule": "secret"}], source_sha="s")["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
