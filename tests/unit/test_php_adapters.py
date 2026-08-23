import unittest

from simplicio_loop_quality.php_adapters import normalize_php_report, plan_php_adapter


class PHPAdapterTest(unittest.TestCase):
    def test_composer_phpunit_plan_is_available(self):
        plan = plan_php_adapter(["composer.json", "tests/ExampleTest.php"])
        self.assertEqual(plan.status, "PLANNED")
        self.assertEqual(plan.framework, "phpunit")

    def test_missing_composer_blocks(self):
        self.assertEqual(plan_php_adapter(["index.php"]).status, "BLOCKED")

    def test_invalid_report_status_blocks(self):
        self.assertEqual(normalize_php_report({"status": "green"})["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
