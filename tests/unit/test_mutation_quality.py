import unittest

from simplicio_loop_quality.mutation_quality import evaluate_mutations, plan_mutation


class MutationQualityTest(unittest.TestCase):
    def test_engine_absence_blocks_planning(self):
        self.assertEqual(plan_mutation({"tools": {}}, changed_scope=("src/a.py",)).status, "BLOCKED")

    def test_killed_mutants_meet_strength_threshold(self):
        report = evaluate_mutations({"killed": 9, "survived": 1, "timed_out": 0, "equivalent": 2}, minimum_score=90)
        self.assertEqual(report.status, "PASS")
        self.assertEqual(report.score, 90)

    def test_survivors_timeouts_and_empty_results_do_not_pass(self):
        self.assertEqual(evaluate_mutations({"killed": 1, "survived": 9}, minimum_score=90).status, "FAIL")
        self.assertEqual(evaluate_mutations({}, minimum_score=90).status, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
