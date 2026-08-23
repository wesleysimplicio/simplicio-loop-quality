"""Long-horizon, multi-repository benchmark planning and validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SCHEMA = "simplicio.quality-evo-benchmark/v1"
SCENARIOS = (
    "S0_BASELINE",
    "S1_RUNTIME",
    "S2_RUNTIME_LOOP",
    "S3_FULL_STACK",
    "S4_LOOP_FAST_STANDALONE",
)
REQUIRED_METRICS = (
    "task_resolution_rate",
    "acceptance_rate",
    "total_seconds",
    "first_valid_change_seconds",
    "retries",
    "tokens",
    "cache_hit_rate",
    "cpu_seconds",
    "rss_bytes",
    "io_bytes",
    "regressions",
    "receipt_coverage",
)


def validate_dataset(tasks: list[Mapping[str, Any]]) -> dict[str, Any]:
    reasons: list[str] = []
    if len(tasks) < 12:
        reasons.append("TASK_COUNT_BELOW_12")
    if len({str(task.get("repository", "")) for task in tasks}) < 3:
        reasons.append("REPOSITORY_COUNT_BELOW_3")
    if len({str(task.get("class", "")) for task in tasks}) < 3:
        reasons.append("TASK_CLASS_COUNT_BELOW_3")
    for task in tasks:
        for field in ("task_id", "repository", "base_sha", "spec_ref", "test_ref"):
            if not task.get(field):
                reasons.append(f"TASK_{field.upper()}_MISSING")
    return {
        "schema": SCHEMA,
        "status": "PASS" if not reasons else "BLOCKED",
        "task_count": len(tasks),
        "reason_codes": sorted(set(reasons)),
    }


def evaluate_benchmark_run(run: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if str(run.get("scenario", "")) not in SCENARIOS:
        reasons.append("SCENARIO_INVALID")
    if int(run.get("repetitions", 0)) < 10:
        reasons.append("REPETITIONS_BELOW_10")
    if not run.get("raw_samples"):
        reasons.append("RAW_SAMPLES_MISSING")
    if not run.get("source_sha"):
        reasons.append("SOURCE_SHA_MISSING")
    if not run.get("receipt_refs"):
        reasons.append("RECEIPTS_MISSING")
    metrics = run.get("metrics")
    if not isinstance(metrics, Mapping):
        reasons.append("METRICS_MISSING")
        metrics = {}
    for name in REQUIRED_METRICS:
        value = metrics.get(name)
        if value is None:
            if not metrics.get(f"{name}_unavailable_reason"):
                reasons.append(f"{name.upper()}_UNAVAILABLE_REASON_MISSING")
        elif isinstance(value, (int, float)) and value < 0:
            reasons.append(f"{name.upper()}_INVALID")
    status = "PASS" if not reasons else "BLOCKED"
    return {
        "schema": SCHEMA,
        "status": status,
        "scenario": run.get("scenario"),
        "reason_codes": sorted(set(reasons)),
    }


__all__ = [
    "REQUIRED_METRICS",
    "SCENARIOS",
    "SCHEMA",
    "evaluate_benchmark_run",
    "validate_dataset",
]
