import unittest

from simplicio_loop_quality.python_adapters import normalize_python_report, plan_python_adapter


class PythonAdapterTest(unittest.TestCase):
    def test_sync_async_and_packaging_features_are_discovered(self):
        plan = plan_python_adapter(["pyproject.toml", "packages/a/src/a/async_api.py"])
        self.assertEqual(plan.status, "PLANNED")
        self.assertIn("async", plan.features)
        self.assertIn("packaging", plan.features)

    def test_non_python_project_blocks(self):
        self.assertEqual(plan_python_adapter(["README.md"]).status, "BLOCKED")

    def test_report_preserves_tool_version_and_status(self):
        report = normalize_python_report({"tool": "pytest", "version": "8", "status": "PASS", "evidence_refs": ["ev"]})
        self.assertEqual(report["version"], "8")
        self.assertEqual(report["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
