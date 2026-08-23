import unittest

from simplicio_loop_quality.hermetic import plan_environment, verify_cleanup


class HermeticTest(unittest.TestCase):
    def test_plan_captures_services_seed_and_cleanup(self):
        plan = plan_environment({"services": ["db"], "ports": [5432], "filesystem": ["tmp/db"], "network": "none", "seed": 7})
        self.assertEqual(plan.status, "PLANNED")
        self.assertEqual(plan.seed, 7)
        self.assertTrue(plan.cleanup_required)

    def test_invalid_scope_and_network_block(self):
        plan = plan_environment({"filesystem": ["../escape"], "network": "public"})
        self.assertEqual(plan.status, "BLOCKED")
        self.assertIn("FILESYSTEM_SCOPE_INVALID", plan.reason_codes)

    def test_cleanup_failure_is_blocked(self):
        result = verify_cleanup(owned_resources=["db", "cache"], released_resources=["db"], cleanup_receipt="ev")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("RESOURCES_NOT_RELEASED", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
