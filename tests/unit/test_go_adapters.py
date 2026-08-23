import unittest

from simplicio_loop_quality.go_adapters import normalize_go_events, plan_go_adapter


class GoAdapterTest(unittest.TestCase):
    def test_workspace_and_cgo_are_preserved(self):
        plan = plan_go_adapter(["go.work", "go.mod", "cmd/app/main.go"], cgo=True)
        self.assertEqual(plan.status, "PLANNED")
        self.assertTrue(plan.workspace)
        self.assertTrue(plan.cgo)

    def test_missing_module_blocks(self):
        self.assertEqual(plan_go_adapter(["main.go"]).status, "BLOCKED")

    def test_json_fail_event_is_not_a_pass(self):
        result = normalize_go_events([{"Action": "fail", "Test": "TestBad"}])
        self.assertEqual(result["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
