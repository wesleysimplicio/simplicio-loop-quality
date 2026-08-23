import unittest

from simplicio_loop_quality.package_smoke import normalize_package_result, plan_package_smoke


class PackageSmokeTest(unittest.TestCase):
    def test_artifact_and_real_code_are_crossed(self):
        plan = plan_package_smoke({"artifacts": ["dist/pkg.whl"], "real_code_paths": ["src/app.py"]})
        self.assertEqual(plan.status, "PLANNED")
        self.assertIn(("package-smoke", "dist/pkg.whl", "src/app.py"), plan.commands)

    def test_missing_artifact_blocks(self):
        self.assertEqual(plan_package_smoke({"real_code_paths": ["src/app.py"]}).status, "BLOCKED")

    def test_missing_artifact_digest_blocks_result(self):
        plan = plan_package_smoke({"artifacts": ["dist/a.whl"], "real_code_paths": ["src/a.py"]})
        self.assertEqual(normalize_package_result({"plan_id": plan.plan_id, "status": "PASS"}, expected_plan_id=plan.plan_id)["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
