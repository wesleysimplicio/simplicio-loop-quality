import unittest

from simplicio_loop_quality.quality_gate_agent import evaluate_quality_gate


class QualityGateAgentTest(unittest.TestCase):
    def setUp(self):
        self.receipt = {"source_sha": "s", "policy_hash": "p", "audit_status": "PASS", "lanes": [{"status": "PASS"}], "findings": []}

    def test_fresh_audited_all_pass_receipt_is_recommended(self):
        self.assertEqual(evaluate_quality_gate(self.receipt, source_sha="s", policy_hash="p").status, "PASS")

    def test_missing_audit_stale_binding_and_failed_lane_block(self):
        result = evaluate_quality_gate({"source_sha": "old", "policy_hash": "p", "lanes": [{"status": "FAIL"}]}, source_sha="s", policy_hash="p")
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("INDEPENDENT_AUDIT_REQUIRED", result.reason_codes)
        self.assertIn("SOURCE_STALE", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
