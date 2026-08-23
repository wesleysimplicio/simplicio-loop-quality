import unittest

from simplicio_loop_quality.integration_agent import normalize_integration_result, plan_integration


class IntegrationAgentTest(unittest.TestCase):
    def test_real_collaborator_plan_has_failure_and_cleanup_paths(self):
        plan = plan_integration({"collaborators": ["db", "queue"], "seed": 3})
        self.assertEqual(plan.status, "PLANNED")
        self.assertIn(("integration", "failure-path"), plan.commands)

    def test_missing_collaborator_blocks(self):
        self.assertEqual(plan_integration({}).status, "BLOCKED")

    def test_missing_cleanup_evidence_blocks_result(self):
        plan = plan_integration({"collaborators": ["db"]})
        self.assertEqual(normalize_integration_result({"plan_id": plan.plan_id, "status": "PASS"}, expected_plan_id=plan.plan_id)["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
