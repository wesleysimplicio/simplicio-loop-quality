import unittest

from simplicio_loop_quality.fast_conformance import (
    build_conformance_matrix,
    evaluate_conformance,
)


def result(case):
    engine, mode, lane, slots = case
    return {
        "engine": engine,
        "mode": mode,
        "lane": lane,
        "slots": slots,
        "status": "PASS",
        "source_sha": "source",
        "policy_hash": "policy",
        "evidence_refs": ["receipt"],
        "rollback_exercised": True,
    }


class FastConformanceTest(unittest.TestCase):
    def test_matrix_has_both_engines_and_modes(self):
        matrix = build_conformance_matrix()
        self.assertIn(("python", "full", "conformance", 1), matrix["cases"])
        self.assertIn(("rust", "loop-standalone", "conformance", 100), matrix["cases"])

    def test_complete_bound_results_pass(self):
        cases = tuple(build_conformance_matrix()["cases"])
        verdict = evaluate_conformance(
            [result(case) for case in cases],
            expected_cases=cases,
            source_sha="source",
            policy_hash="policy",
        )
        self.assertEqual(verdict["status"], "PASS")

    def test_rust_fallback_is_rejected(self):
        case = ("rust", "full", "conformance", 1)
        value = result(case)
        value["fallback_used"] = True
        verdict = evaluate_conformance(
            [value], expected_cases=(case,), source_sha="source", policy_hash="policy"
        )
        self.assertEqual(verdict["status"], "FAIL")
        self.assertIn("RUST_FALLBACK_USED", verdict["reason_codes"])


if __name__ == "__main__":
    unittest.main()
