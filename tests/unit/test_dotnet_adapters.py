import unittest

from simplicio_loop_quality.dotnet_adapters import normalize_dotnet_report, plan_dotnet_adapter


class DotnetAdapterTest(unittest.TestCase):
    def test_solution_and_target_frameworks_are_discovered(self):
        plan = plan_dotnet_adapter(["App.sln", "src/App/App.csproj"], target_frameworks=("net8.0", "netstandard2.1"))
        self.assertEqual(plan.status, "PLANNED")
        self.assertIn("src/App/App.csproj", plan.projects)
        self.assertEqual(len(plan.target_frameworks), 2)

    def test_missing_project_blocks(self):
        self.assertEqual(plan_dotnet_adapter(["README.md"]).status, "BLOCKED")

    def test_trx_report_is_normalized(self):
        self.assertEqual(normalize_dotnet_report({"status": "PASS", "format": "trx"})["format"], "trx")


if __name__ == "__main__":
    unittest.main()
