import unittest

from simplicio_loop_quality.ruby_adapters import normalize_ruby_report, plan_ruby_adapter


class RubyAdapterTest(unittest.TestCase):
    def test_bundler_lock_and_rspec_are_required(self):
        plan = plan_ruby_adapter(["Gemfile", "Gemfile.lock", "spec/app_spec.rb"])
        self.assertEqual(plan.status, "PLANNED")
        self.assertEqual(plan.framework, "rspec")

    def test_missing_lockfile_blocks(self):
        self.assertEqual(plan_ruby_adapter(["Gemfile"]).status, "BLOCKED")

    def test_invalid_status_blocks(self):
        self.assertEqual(normalize_ruby_report({"status": "green"})["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
