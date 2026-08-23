import unittest

from simplicio_loop_quality.hub_environment_binding import build_hub_environment_request, validate_cleanup_receipt


class HubEnvironmentBindingTest(unittest.TestCase):
    def test_request_is_loop_owned_and_bound(self):
        request = build_hub_environment_request({"services": ["db"], "seed": 7}, identity={"run_id": "r"}, stage_id="env")
        self.assertEqual(request["executor"], "simplicio-loop-hub")
        self.assertEqual(request["stage_id"], "env")
        self.assertTrue(request["request_hash"])

    def test_cleanup_receipt_is_fail_closed(self):
        self.assertIn("CLEANUP_NOT_VERIFIED", validate_cleanup_receipt({"status": "FAIL"}))
        self.assertEqual(validate_cleanup_receipt({"executor": "simplicio-loop-hub", "status": "PASS", "released_resources": ["db"]}), ())


if __name__ == "__main__":
    unittest.main()
