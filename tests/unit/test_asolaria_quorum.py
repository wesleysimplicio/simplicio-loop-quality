import unittest

from simplicio_loop_quality.asolaria_quorum import evaluate_quorum


def seats():
    values = {}
    for index, name in enumerate(("executor", "verifier", "auditor")):
        values[name] = {
            "agent_address": name,
            "context_hash": f"context-{index}",
            "prompt_hash": f"prompt-{index}",
            "seed": str(index),
            "source_sha": "source",
            "policy_hash": "policy",
            "criteria_refs": ["AC-1"],
            "evidence_refs": [f"evidence/{name}"],
        }
    values["clean_control"] = True
    return values


class AsolariaQuorumTest(unittest.TestCase):
    def test_independent_tri_vantage_quorum_passes(self):
        result = evaluate_quorum(["AC-1"], seats(), source_sha="source", policy_hash="policy")
        self.assertEqual(result["status"], "PASS")

    def test_same_context_in_two_seats_is_rejected(self):
        value = seats()
        value["verifier"]["agent_address"] = "executor"
        value["verifier"]["context_hash"] = "context-0"
        value["verifier"]["prompt_hash"] = "prompt-0"
        value["verifier"]["seed"] = "0"
        result = evaluate_quorum(["AC-1"], value, source_sha="source", policy_hash="policy")
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("INDEPENDENCE_COLLISION", result["reason_codes"])

    def test_stale_or_missing_receipt_does_not_pass(self):
        value = seats()
        value["auditor"]["stale"] = True
        value["auditor"]["evidence_refs"] = []
        result = evaluate_quorum(["AC-1"], value, source_sha="source", policy_hash="policy")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("EVIDENCE_STALE", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
