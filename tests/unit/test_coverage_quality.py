import unittest

from simplicio_loop_quality.coverage_quality import evaluate_coverage


def complete(value=100):
    return {name: {"covered": value, "total": 100} for name in ("line", "branch", "condition", "changed", "critical")}


class CoverageQualityTest(unittest.TestCase):
    def test_all_dimensions_above_threshold_pass(self):
        result = evaluate_coverage(complete(), {name: 90 for name in complete()})
        self.assertEqual(result.status, "PASS")

    def test_changed_and_critical_gaps_fail(self):
        metrics = complete()
        metrics["changed"] = {"covered": 50, "total": 100}
        result = evaluate_coverage(metrics, {name: 90 for name in complete()})
        self.assertEqual(result.status, "FAIL")
        self.assertIn("CHANGED_BELOW_THRESHOLD", result.reason_codes)

    def test_missing_dimension_blocks(self):
        result = evaluate_coverage({}, {name: 90 for name in complete()})
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("LINE_MISSING", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
