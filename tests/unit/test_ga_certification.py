import unittest

from simplicio_loop_quality.ga_certification import (
    LANES,
    build_ga_matrix,
    evaluate_ga_results,
)


class GaCertificationTest(unittest.TestCase):
    def test_matrix_contains_quality_and_release_lanes(self):
        matrix = build_ga_matrix(("python",))
        self.assertEqual(len(matrix["cases"]), len(LANES))
        self.assertIn(("python", "golden_defect"), matrix["cases"])

    def test_complete_results_pass(self):
        cases = tuple(build_ga_matrix(("python",))["cases"])
        results = [
            {
                "profile": profile,
                "lane": lane,
                "status": "PASS",
                "source_sha": "source",
                "evidence_refs": [f"evidence/{profile}/{lane}"],
                "percent": 95 if lane == "changed_branch_coverage" else 100,
            }
            for profile, lane in cases
        ]
        self.assertEqual(
            evaluate_ga_results(results, expected_cases=cases, source_sha="source")["status"],
            "PASS",
        )

    def test_stale_or_missing_lane_is_not_pass(self):
        result = evaluate_ga_results(
            [],
            expected_cases=(("python", "unit"),),
            source_sha="source",
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("GA_CASE_MISSING", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
