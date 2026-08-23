import unittest

from simplicio_loop_quality.container_profile import normalize_container_result, plan_container_profile


class ContainerProfileTest(unittest.TestCase):
    def test_image_and_manifests_are_planned(self):
        plan = plan_container_profile(["Dockerfile", "deploy/app.yaml"], image="registry/app@sha256:x")
        self.assertEqual(plan["status"], "PLANNED")
        self.assertIn("nonroot", plan["checks"])

    def test_missing_image_blocks(self):
        self.assertEqual(plan_container_profile(["Dockerfile"])["status"], "BLOCKED")

    def test_missing_digest_blocks_result(self):
        plan = plan_container_profile(["Dockerfile"], image="registry/app@sha256:x")
        result = normalize_container_result({"plan_id": plan["plan_id"], "status": "PASS"}, expected_plan_id=plan["plan_id"])
        self.assertEqual(result["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
