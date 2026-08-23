import unittest

from simplicio_loop_quality.ai_quality import normalize_ai_result, plan_ai_quality


class AIQualityTest(unittest.TestCase):
    def test_reproducible_plan_requires_seed(self):
        plan = plan_ai_quality({"model_id": "model-v1", "checks": ["toxicity", "grounding"], "seed": 7, "temperature": 0})
        self.assertEqual(plan.status, "PLANNED")

    def test_missing_model_or_seed_blocks(self):
        plan = plan_ai_quality({"checks": ["grounding"]})
        self.assertEqual(plan.status, "BLOCKED")
        self.assertIn("MODEL_ID_MISSING", plan.blocked_reasons)

    def test_stale_plan_and_missing_evidence_block(self):
        plan = plan_ai_quality({"model_id": "m", "checks": ["x"], "seed": 1})
        result = normalize_ai_result({"plan_id": "old", "status": "PASS"}, expected_plan_id=plan.plan_id)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("PLAN_STALE", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
