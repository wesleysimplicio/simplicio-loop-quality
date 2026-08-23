import unittest

from simplicio_loop_quality.performance_quality import summarize_benchmark


class PerformanceQualityTest(unittest.TestCase):
    def test_ten_stable_samples_produce_statistics(self):
        result = summarize_benchmark([10 + (index % 2) for index in range(10)], baseline_p95=12, budget_p95=15)
        self.assertEqual(result.status, "PASS")
        self.assertIsNotNone(result.confidence95)

    def test_missing_baseline_or_samples_blocks(self):
        self.assertEqual(summarize_benchmark([1] * 10, baseline_p95=None, budget_p95=2).status, "BLOCKED")
        self.assertEqual(summarize_benchmark([], baseline_p95=1, budget_p95=2).status, "BLOCKED")

    def test_budget_regression_fails(self):
        result = summarize_benchmark([10] * 10, baseline_p95=10, budget_p95=5)
        self.assertEqual(result.status, "FAIL")
        self.assertIn("BUDGET_EXCEEDED", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
