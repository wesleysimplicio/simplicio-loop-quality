import unittest

from simplicio_loop_quality.load_stress import normalize_load_result, plan_load_stress


class LoadStressTest(unittest.TestCase):
    def test_positive_budget_is_planned(self):
        self.assertEqual(plan_load_stress({"duration_seconds": 60, "concurrency": 10})["status"], "PLANNED")

    def test_invalid_budget_blocks(self):
        self.assertEqual(plan_load_stress({"duration_seconds": 0, "concurrency": 1})["status"], "BLOCKED")

    def test_missing_metrics_and_cleanup_block(self):
        plan = plan_load_stress({"duration_seconds": 1, "concurrency": 2})
        result = normalize_load_result({"plan_id": plan["plan_id"], "status": "PASS"}, expected_plan_id=plan["plan_id"])
        self.assertEqual(result["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
