import unittest

from simplicio_loop_quality.cli_reports import parse_cli_status, project_cli_report


class CLIReportsTest(unittest.TestCase):
    def test_statuses_have_ci_neutral_exit_codes(self):
        self.assertEqual(project_cli_report({"status": "PASS"})["exit_code"], 0)
        self.assertEqual(project_cli_report({"status": "BLOCKED"})["exit_code"], 2)

    def test_unknown_exit_code_is_blocked(self):
        self.assertEqual(parse_cli_status(99), "BLOCKED")


if __name__ == "__main__":
    unittest.main()
