import unittest

from simplicio_loop_quality.operational_readiness import (
    normalize_readiness,
    plan_operational_readiness,
)


class OperationalReadinessTest(unittest.TestCase):
    def test_complete_plan_is_planned(self):
        requirements = {name: ["evidence"] for name in ("healthchecks", "alerts", "rollback", "cleanup", "runbook")}
        self.assertEqual(plan_operational_readiness(requirements)["status"], "PLANNED")

    def test_missing_runbook_blocks(self):
        self.assertEqual(plan_operational_readiness({})["status"], "BLOCKED")

    def test_missing_evidence_blocks_result(self):
        result = normalize_readiness({"status": "PASS"})
        self.assertEqual(result["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
