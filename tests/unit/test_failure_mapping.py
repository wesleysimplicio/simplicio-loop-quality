import unittest

from simplicio_loop_quality.failure_mapping import map_failure


class FailureMappingTest(unittest.TestCase):
    def test_timeout_has_retry_hint_but_does_not_retry_locally(self):
        decision = map_failure({"kind": "timeout"}, attempts_remaining=1)
        self.assertTrue(decision.retry_hint)
        self.assertEqual(decision.status, "BLOCKED")

    def test_exhaustion_and_permanent_failures_are_terminal(self):
        self.assertEqual(map_failure({"kind": "timeout"}, attempts_remaining=0).reason_code, "RETRY_EXHAUSTED")
        self.assertFalse(map_failure({"kind": "permission"}, attempts_remaining=2).retry_hint)
        self.assertEqual(map_failure({"kind": "permission"}, attempts_remaining=2).status, "FAIL")


if __name__ == "__main__":
    unittest.main()
