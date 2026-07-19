import json
import unittest
from importlib import resources

from simplicio_loop_quality.agents import AGENTS, agent_ids, find_agent
from simplicio_loop_quality.policy import load_strict_policy


class AgentSpecsTest(unittest.TestCase):
    def test_agent_ids_are_unique_and_agents_do_not_self_approve(self):
        ids = agent_ids()
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 16)
        self.assertTrue(all(not agent.may_self_approve for agent in AGENTS))
        self.assertTrue(all(not agent.may_author_product_code for agent in AGENTS))

    def test_find_agent(self):
        agent = find_agent("quality_gate_agent")
        self.assertEqual(agent.authority, "gate")
        self.assertEqual(agent.to_dict()["role_id"], "quality_gate_agent")

    def test_find_agent_rejects_unknown_role(self):
        with self.assertRaises(KeyError):
            find_agent("missing")

    def test_strict_policy_manifest_and_agent_catalog_have_no_drift(self):
        policy = load_strict_policy()
        assigned_lanes = {lane for agent in AGENTS for lane in agent.lanes}
        self.assertEqual(set(policy.lanes) - assigned_lanes, set())

        manifest = json.loads(
            resources.files("simplicio_loop_quality.contracts")
            .joinpath("loop-extension.json")
            .read_text(encoding="utf-8")
        )
        manifest_roles = {binding["role_id"] for binding in manifest["role_bindings"]}
        self.assertEqual(manifest_roles, set(agent_ids()))
