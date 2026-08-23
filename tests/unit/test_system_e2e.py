import unittest

from simplicio_loop_quality.system_e2e import normalize_e2e_result, plan_system_e2e


class SystemE2ETest(unittest.TestCase):
    def test_scenarios_are_planned(self):
        plan = plan_system_e2e({"scenarios": ["login", "checkout"]})
        self.assertEqual(plan.status, "PLANNED")
        self.assertIn(("system-e2e", "login"), plan.commands)

    def test_missing_scenarios_blocks(self):
        self.assertEqual(plan_system_e2e({}).status, "BLOCKED")

    def test_missing_user_visible_evidence_blocks(self):
        plan = plan_system_e2e({"scenarios": ["login"]})
        result = normalize_e2e_result({"plan_id": plan.plan_id, "status": "PASS"}, expected_plan_id=plan.plan_id)
        self.assertEqual(result["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
