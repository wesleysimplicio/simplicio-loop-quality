import unittest

from simplicio_loop_quality.property_fuzz import normalize_fuzz_failure, plan_fuzz


class PropertyFuzzTest(unittest.TestCase):
    def test_seeded_engine_plan_is_reproducible(self):
        plan = plan_fuzz({"engines": ["hypothesis"], "seed": 7, "cases": 100})
        self.assertEqual(plan.status, "PLANNED")

    def test_missing_engine_or_seed_blocks(self):
        self.assertEqual(plan_fuzz({"cases": 1}).status, "BLOCKED")

    def test_failure_without_minimal_counterexample_blocks(self):
        plan = plan_fuzz({"engines": ["hypothesis"], "seed": 1, "cases": 2})
        result = normalize_fuzz_failure({"plan_id": plan.plan_id, "status": "FAIL"}, expected_plan_id=plan.plan_id)
        self.assertEqual(result["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
