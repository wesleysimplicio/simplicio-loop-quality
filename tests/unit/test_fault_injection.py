import unittest

from simplicio_loop_quality.fault_injection import normalize_recovery, plan_faults


class FaultInjectionTest(unittest.TestCase):
    def test_default_faults_are_planned(self):
        self.assertEqual(plan_faults({}).status, "PLANNED")

    def test_unsupported_fault_blocks(self):
        self.assertEqual(plan_faults({"faults": ["teleport"]}).status, "BLOCKED")

    def test_recovery_without_cleanup_evidence_blocks(self):
        plan = plan_faults({})
        result = normalize_recovery({"plan_id": plan.plan_id, "status": "PASS"}, expected_plan_id=plan.plan_id)
        self.assertEqual(result["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
