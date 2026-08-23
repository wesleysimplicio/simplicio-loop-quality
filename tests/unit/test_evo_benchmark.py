import unittest

from simplicio_loop_quality.evo_benchmark import (
    REQUIRED_METRICS,
    evaluate_benchmark_run,
    validate_dataset,
)


def task(index):
    return {
        "task_id": f"task-{index}",
        "repository": f"repo-{index % 3}",
        "class": f"class-{index % 3}",
        "base_sha": "a" * 40,
        "spec_ref": f"spec/{index}",
        "test_ref": f"test/{index}",
    }


def run():
    metrics = {name: 1 for name in REQUIRED_METRICS}
    metrics["retries"] = 0
    return {
        "scenario": "S3_FULL_STACK",
        "repetitions": 10,
        "raw_samples": [{"total_seconds": 1}],
        "source_sha": "a" * 40,
        "receipt_refs": ["receipt"],
        "metrics": metrics,
    }


class EvoBenchmarkTest(unittest.TestCase):
    def test_dataset_requires_long_horizon_corpus(self):
        self.assertEqual(validate_dataset([task(index) for index in range(12)])["status"], "PASS")

    def test_complete_run_passes(self):
        self.assertEqual(evaluate_benchmark_run(run())["status"], "PASS")

    def test_missing_metric_reason_blocks(self):
        value = run()
        value["metrics"].pop("tokens")
        result = evaluate_benchmark_run(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("TOKENS_UNAVAILABLE_REASON_MISSING", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
