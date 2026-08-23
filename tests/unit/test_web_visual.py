import unittest

from simplicio_loop_quality.web_visual import normalize_visual_result, plan_web_visual


class WebVisualTest(unittest.TestCase):
    def test_routes_and_viewports_cross_product(self):
        plan = plan_web_visual({"routes": ["/login"], "viewports": ["desktop", "mobile"]})
        self.assertEqual(plan["status"], "PLANNED")
        self.assertEqual(len(plan["scenarios"]), 2)

    def test_missing_routes_blocks(self):
        self.assertEqual(plan_web_visual({})["status"], "BLOCKED")

    def test_missing_screenshots_blocks_result(self):
        plan = plan_web_visual({"routes": ["/"], "viewports": ["desktop"]})
        result = normalize_visual_result({"plan_id": plan["plan_id"], "status": "PASS"}, expected_plan_id=plan["plan_id"])
        self.assertEqual(result["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
