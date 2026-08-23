import unittest

from simplicio_loop_quality.swift_adapters import normalize_swift_report, plan_swift_adapter


class SwiftAdapterTest(unittest.TestCase):
    def test_swift_package_plan_is_available(self):
        plan = plan_swift_adapter(["Package.swift", "Sources/App/main.swift"], platforms=("macOS", "Linux"))
        self.assertEqual(plan.status, "PLANNED")
        self.assertIn(("swift", "test"), plan.commands)

    def test_missing_package_manifest_blocks(self):
        self.assertEqual(plan_swift_adapter(["main.swift"]).status, "BLOCKED")

    def test_invalid_status_blocks(self):
        self.assertEqual(normalize_swift_report({"status": "green"})["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
