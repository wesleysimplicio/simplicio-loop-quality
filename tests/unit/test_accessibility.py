import unittest

from simplicio_loop_quality.accessibility import normalize_accessibility, plan_accessibility


class AccessibilityTest(unittest.TestCase):
    def test_routes_plan_wcag_checks(self):
        plan = plan_accessibility(["/login"])
        self.assertEqual(plan["status"], "PLANNED")
        self.assertIn("keyboard", plan["checks"])

    def test_missing_routes_blocks(self):
        self.assertEqual(plan_accessibility([])["status"], "BLOCKED")

    def test_violation_fails(self):
        self.assertEqual(normalize_accessibility([{"rule": "color-contrast"}])["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
