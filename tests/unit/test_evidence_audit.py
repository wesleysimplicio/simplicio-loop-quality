import hashlib
import unittest

from simplicio_loop_quality.evidence_audit import audit_evidence


class EvidenceAuditTest(unittest.TestCase):
    def setUp(self):
        self.identity = {"run_id": "run", "task_id": "task", "attempt_id": "attempt", "fence": "fence", "source_sha": "a" * 40, "policy_hash": "b" * 64}
        self.record = {
            "evidence_id": "ev-1", "identity": self.identity, "producer_agent": "producer", "executor_agent": "executor",
            "auditor_agent": "auditor", "content": "ok", "sha256": hashlib.sha256(b"ok").hexdigest(),
        }

    def test_independent_fresh_evidence_passes(self):
        verdict = audit_evidence([self.record], expected_identity=self.identity, auditor_id="audit-seat")
        self.assertEqual(verdict.status, "PASS")

    def test_forged_missing_stale_cross_run_and_tampered_inputs_block_or_fail(self):
        cases = [
            {**self.record, "producer_agent": "auditor"},
            {**self.record, "identity": {**self.identity, "run_id": "other"}},
            {**self.record, "sha256": "0" * 64},
            {key: value for key, value in self.record.items() if key != "identity"},
        ]
        for record in cases:
            verdict = audit_evidence([record], expected_identity=self.identity, auditor_id="audit-seat")
            self.assertIn(verdict.status, {"FAIL", "BLOCKED"})
            self.assertTrue(verdict.findings)


if __name__ == "__main__":
    unittest.main()
