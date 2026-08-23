import unittest

from simplicio_loop_quality.quality_planner import compile_quality_plan


class QualityPlannerTest(unittest.TestCase):
    def test_plan_is_deterministic_and_stateless(self):
        policy = {"mandatory_lanes": ["unit", "evidence_audit"]}
        impact = {}
        traceability = {"status": "PASS"}
        left = compile_quality_plan(policy, impact, traceability)
        right = compile_quality_plan(policy, impact, traceability)
        self.assertEqual(left, right)
        self.assertIn("unit_component_agent", left.agents)

    def test_missing_traceability_blocks(self):
        result = compile_quality_plan({"mandatory_lanes": ["unit"]}, {}, {"status": "BLOCKED"})
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("TRACEABILITY_BLOCKED", result.blockers)


if __name__ == "__main__":
    unittest.main()
