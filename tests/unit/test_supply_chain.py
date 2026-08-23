import unittest

from simplicio_loop_quality.supply_chain import normalize_supply_chain, plan_supply_chain


class SupplyChainTest(unittest.TestCase):
    def test_lockfile_plan_is_available(self):
        plan = plan_supply_chain(["pyproject.toml", "poetry.lock"])
        self.assertEqual(plan["status"], "PLANNED")
        self.assertIn("provenance", plan["tools"])

    def test_missing_lockfile_blocks(self):
        self.assertEqual(plan_supply_chain(["pyproject.toml"])["status"], "BLOCKED")

    def test_missing_digests_block_result(self):
        plan = plan_supply_chain(["Cargo.lock"])
        result = normalize_supply_chain({"plan_id": plan["plan_id"], "status": "PASS"}, expected_plan_id=plan["plan_id"])
        self.assertEqual(result["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
