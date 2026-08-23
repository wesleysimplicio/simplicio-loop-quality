import unittest

from simplicio_loop_quality.journal_events import accept_event, event_key


class JournalEventTest(unittest.TestCase):
    def test_same_identity_sequence_is_idempotent(self):
        identity = {"run_id": "r", "task_id": "t"}
        event = {"identity": identity, "event_type": "stage.accepted", "sequence": 1, "idempotency_key": event_key(identity, "stage.accepted", 1)}
        self.assertEqual(accept_event(event, last_sequence=None, expected_identity=identity).status, "ACCEPTED")

    def test_late_stale_and_key_mismatch_are_rejected(self):
        identity = {"run_id": "r", "task_id": "t"}
        event = {"identity": {"run_id": "other", "task_id": "t"}, "event_type": "x", "sequence": 1, "idempotency_key": "bad"}
        result = accept_event(event, last_sequence=2, expected_identity=identity)
        self.assertEqual(result.status, "REJECTED")
        self.assertIn("EVENT_OUT_OF_ORDER", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
