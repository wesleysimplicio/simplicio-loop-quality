import unittest

from simplicio_loop_quality.flaky_repeatability import classify_repeatability


class FlakyRepeatabilityTest(unittest.TestCase):
    def test_stable_passes(self):
        result = classify_repeatability(["PASS"] * 5)
        self.assertEqual(result.status, "PASS")
        self.assertFalse(result.quarantine)

    def test_mixed_results_are_flaky_and_quarantined(self):
        result = classify_repeatability(["PASS", "FAIL", "PASS", "FAIL"])
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(result.flaky)
        self.assertTrue(result.quarantine)

    def test_empty_runs_block(self):
        self.assertEqual(classify_repeatability([]).status, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
