import unittest

from simplicio_loop_quality.observability import build_observation, compare_trend, correlation_id


class ObservabilityTest(unittest.TestCase):
    def test_correlation_is_deterministic(self):
        self.assertEqual(correlation_id({"run_id": "r"}), correlation_id({"run_id": "r"}))
        self.assertEqual(build_observation({"run_id": "r"}, "quality", {})["event_type"], "quality")

    def test_regression_is_visible(self):
        result = compare_trend({"duration": 12}, {"duration": 10})
        self.assertEqual(result["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
