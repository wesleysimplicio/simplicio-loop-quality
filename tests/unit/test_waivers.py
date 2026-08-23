import unittest
from datetime import datetime, timedelta, timezone

from simplicio_loop_quality.waivers import evaluate_waiver, select_waivers, waiver_policy_hash


class WaiverTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.policy_hash = waiver_policy_hash({"threshold": 0})
        self.value = {
            "waiver_id": "W-1",
            "reason_code": "TOOL_UNAVAILABLE",
            "justification": "The approved analyzer is unavailable in this isolated runner.",
            "scope": "static",
            "created_by": "author",
            "approver": "reviewer",
            "expires_at": (self.now + timedelta(days=1)).isoformat(),
            "source_sha": "a" * 40,
            "policy_hash": self.policy_hash,
        }

    def test_valid_waiver_is_approved(self):
        verdict = evaluate_waiver(self.value, lane="static", source_sha="a" * 40, policy_hash=self.policy_hash, now=self.now)
        self.assertEqual(verdict.status, "APPROVED")

    def test_expired_self_approved_stale_and_overbroad_are_blocked(self):
        cases = [
            {**self.value, "expires_at": self.now.isoformat()},
            {**self.value, "created_by": "reviewer"},
            {**self.value, "source_sha": "b" * 40},
            {**self.value, "scope": "*"},
        ]
        for case in cases:
            verdict = evaluate_waiver(case, lane="static", source_sha="a" * 40, policy_hash=self.policy_hash, now=self.now)
            self.assertEqual(verdict.status, "BLOCKED")

    def test_missing_waiver_does_not_auto_approve(self):
        verdict = select_waivers({}, required_lanes=("static",), source_sha="a" * 40, policy_hash=self.policy_hash, now=self.now)[0]
        self.assertEqual(verdict.reason_codes, ("WAIVER_MISSING",))


if __name__ == "__main__":
    unittest.main()
