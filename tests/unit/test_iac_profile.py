import unittest

from simplicio_loop_quality.iac_profile import normalize_iac_result, plan_iac_profile


class IACProfileTest(unittest.TestCase):
    def test_terraform_and_kubernetes_checks_are_planned(self):
        plan = plan_iac_profile(["main.tf", "deploy/app.yaml"])
        self.assertEqual(plan["status"], "PLANNED")
        self.assertIn("security", plan["checks"])

    def test_no_iac_files_blocks(self):
        self.assertEqual(plan_iac_profile(["README.md"])["status"], "BLOCKED")

    def test_missing_plan_digest_blocks_result(self):
        self.assertEqual(normalize_iac_result({"status": "PASS"})["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
