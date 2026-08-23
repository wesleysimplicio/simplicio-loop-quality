import unittest

from simplicio_loop_quality.golden_defects import build_golden_matrix, evaluate_golden_results


class GoldenDefectsTest(unittest.TestCase):
    def test_defect_and_clean_control_cases_are_created(self):
        matrix = build_golden_matrix(["python", "rust"])
        self.assertEqual(matrix["status"], "PLANNED")
        self.assertIn(("python", "seeded-defect"), matrix["cases"])
        self.assertIn(("rust", "clean-control"), matrix["cases"])

    def test_failed_or_clean_false_gap_does_not_pass(self):
        result = evaluate_golden_results([{"case_type": "clean-control", "status": "PASS", "findings": ["hallucinated"]}])
        self.assertEqual(result["status"], "FAIL")

    def test_empty_results_block(self):
        self.assertEqual(evaluate_golden_results([])["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
