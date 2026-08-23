import unittest

from simplicio_loop_quality.data_quality import normalize_data_result, plan_data_quality


class DataQualityTest(unittest.TestCase):
    def test_engine_plan_contains_migration_safety_checks(self):
        plan = plan_data_quality({"engines": ["postgres"], "files": ["migrations/001.sql"]})
        self.assertEqual(plan.status, "PLANNED")
        self.assertIn("migration_reversibility", plan.checks)

    def test_engine_absence_blocks(self):
        self.assertEqual(plan_data_quality({"files": ["schema.sql"]}).status, "BLOCKED")

    def test_stale_result_blocks(self):
        plan = plan_data_quality({"engines": ["sqlite"]})
        result = normalize_data_result({"plan_id": "old", "status": "PASS"}, expected_plan_id=plan.plan_id)
        self.assertEqual(result["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
