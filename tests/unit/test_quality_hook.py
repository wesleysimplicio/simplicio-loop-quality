import unittest

from simplicio_loop_quality.quality_hook import validate_hook_result


class QualityHookTest(unittest.TestCase):
    def test_required_pass_is_accepted(self):
        self.assertEqual(validate_hook_result({"status": "PASS"}).status, "ACCEPTED")

    def test_missing_crash_partial_and_invalid_results_block(self):
        for result in (None, {"crashed": True}, {"status": "PASS", "partial_write": True}, {"status": "wat"}):
            self.assertEqual(validate_hook_result(result).status, "BLOCKED")

    def test_diagnostic_mode_can_be_nonterminal(self):
        self.assertEqual(validate_hook_result(None, required=False, mode="diagnostic").status, "ACCEPTED")


if __name__ == "__main__":
    unittest.main()
