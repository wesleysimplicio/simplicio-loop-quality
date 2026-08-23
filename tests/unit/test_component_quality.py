import unittest

from simplicio_loop_quality.component_quality import discover_components, normalize_component_results, plan_component_tests


class ComponentQualityTest(unittest.TestCase):
    def test_explicit_boundaries_are_preserved(self):
        components = discover_components({"components": [{"id": "cache", "boundary": ["src/cache.py"], "collaborators": ["filesystem"]}]})
        self.assertEqual(components[0].component_id, "cache")
        self.assertEqual(components[0].collaborators, ("filesystem",))

    def test_impact_paths_provide_fallback_boundaries(self):
        plan = plan_component_tests({"impacted_files": ["src/cache.py"]}, source_sha="a", policy_hash="p")
        self.assertEqual(plan.status, "PLANNED")

    def test_missing_cleanup_evidence_blocks(self):
        result = normalize_component_results([{"component_id": "cache", "status": "PASS"}], source_sha="a", policy_hash="p")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("CLEANUP_EVIDENCE_MISSING", result["results"][0]["reason_codes"])


if __name__ == "__main__":
    unittest.main()
