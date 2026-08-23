import unittest

from simplicio_loop_quality.rust_adapters import normalize_rust_report, plan_rust_adapter


class RustAdapterTest(unittest.TestCase):
    def test_workspace_features_and_target_are_preserved(self):
        plan = plan_rust_adapter(["Cargo.toml", "Cargo.lock", "crates/a/Cargo.toml", "src/bin/tool.rs"], features=("proptest",), target="x86_64-unknown-linux-gnu")
        self.assertEqual(plan.status, "PLANNED")
        self.assertTrue(plan.workspace)
        self.assertIn("binary", plan.features)
        self.assertEqual(plan.target, "x86_64-unknown-linux-gnu")

    def test_missing_cargo_manifest_blocks(self):
        self.assertEqual(plan_rust_adapter(["src/main.rs"]).status, "BLOCKED")

    def test_diagnostics_are_normalized(self):
        self.assertEqual(normalize_rust_report({"status": "FAIL", "diagnostics": ["error"]})["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
