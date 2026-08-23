import unittest

from simplicio_loop_quality.test_selection import validate_test_selection


class TestSelectionTest(unittest.TestCase):
    def test_impact_covered_by_unique_tests_passes(self):
        result = validate_test_selection({"impacted_files": ["src/a.py"]}, [{"test_id": "t", "paths": ["src/a.py"]}])
        self.assertEqual(result["status"], "PASS")

    def test_uncovered_impact_and_duplicates_block(self):
        result = validate_test_selection({"impacted_files": ["src/a.py"]}, [{"test_id": "t", "paths": []}, {"test_id": "t", "paths": []}])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("IMPACT_UNCOVERED", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
