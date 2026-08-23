import unittest

from simplicio_loop_quality.concurrency_reliability import normalize_concurrency_result, plan_concurrency


class ConcurrencyTest(unittest.TestCase):
    def test_default_scenarios_use_multiple_workers(self):
        plan = plan_concurrency({})
        self.assertEqual(plan.status, "PLANNED")
        self.assertGreaterEqual(plan.workers, 2)

    def test_invalid_worker_count_blocks(self):
        self.assertEqual(plan_concurrency({"workers": 1}).status, "BLOCKED")

    def test_race_and_unreleased_resources_do_not_pass(self):
        plan = plan_concurrency({})
        result = normalize_concurrency_result({"plan_id": plan.plan_id, "status": "PASS", "race_detected": True}, expected_plan_id=plan.plan_id)
        self.assertEqual(result["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
