import unittest

from simplicio_loop_quality.stage_graph import compile_stage_graph


class StageGraphTest(unittest.TestCase):
    def test_fan_in_graph_is_deterministic(self):
        stages = [{"id": "a"}, {"id": "b"}, {"id": "gate"}]
        graph = compile_stage_graph(stages, [("a", "gate"), ("b", "gate")], policy_hash="p")
        self.assertEqual(graph.status, "PLANNED")
        self.assertEqual(graph, compile_stage_graph(list(reversed(stages)), [("b", "gate"), ("a", "gate")], policy_hash="p"))

    def test_cycle_duplicate_and_unknown_edge_block(self):
        result = compile_stage_graph([{"id": "a"}, {"id": "a"}], [("a", "missing"), ("a", "a")], policy_hash="p")
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("STAGE_ID_DUPLICATE", result.reason_codes)
        self.assertIn("EDGE_ENDPOINT_UNKNOWN", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
