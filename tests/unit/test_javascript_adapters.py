import unittest

from simplicio_loop_quality.javascript_adapters import normalize_javascript_report, plan_javascript_adapter


class JavaScriptAdapterTest(unittest.TestCase):
    def test_esm_workspace_and_pnpm_are_discovered(self):
        plan = plan_javascript_adapter(["package.json", "pnpm-lock.yaml", "packages/web/src/index.ts"], {"type": "module", "workspaces": ["packages/*"]})
        self.assertEqual(plan.status, "PLANNED")
        self.assertEqual(plan.module_mode, "esm")
        self.assertTrue(plan.workspace)

    def test_missing_lockfile_blocks(self):
        self.assertEqual(plan_javascript_adapter(["package.json"], {}).status, "BLOCKED")

    def test_invalid_status_is_blocked(self):
        self.assertEqual(normalize_javascript_report({"status": "green"})["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
