import unittest

from simplicio_loop_quality.compatibility import normalize_compatibility, plan_compatibility


class CompatibilityTest(unittest.TestCase):
    def test_matrix_and_migrations_are_planned(self):
        result = plan_compatibility({"versions": ["1", "2"], "migrations": ["upgrade", "downgrade"]})
        self.assertEqual(result["status"], "PLANNED")

    def test_small_matrix_blocks(self):
        self.assertEqual(plan_compatibility({"versions": ["1"], "migrations": ["upgrade"]})["status"], "BLOCKED")

    def test_missing_rollback_evidence_blocks(self):
        plan = plan_compatibility({"versions": ["1", "2"], "migrations": ["upgrade"]})
        result = normalize_compatibility({"plan_id": plan["plan_id"], "status": "PASS"}, expected_plan_id=plan["plan_id"])
        self.assertEqual(result["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
