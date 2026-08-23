"""Reproducible benchmark statistics and baseline comparison."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-performance/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _percentile(values: list[float], percentile: float) -> float:
    position = (len(values) - 1) * percentile
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


@dataclass(frozen=True)
class BenchmarkSummary:
    status: str
    sample_count: int
    p50: float | None
    p95: float | None
    p99: float | None
    mean: float | None
    variance: float | None
    confidence95: tuple[float, float] | None
    delta_percent: float | None
    reason_codes: tuple[str, ...]
    summary_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, **self.__dict__}


def summarize_benchmark(samples: list[float], *, baseline_p95: float | None, budget_p95: float | None, minimum_samples: int = 10) -> BenchmarkSummary:
    reasons: set[str] = set()
    values = sorted(float(value) for value in samples if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0)
    if len(values) < minimum_samples:
        reasons.add("SAMPLE_COUNT_INSUFFICIENT")
    if not values:
        reasons.add("SAMPLES_EMPTY")
    mean = sum(values) / len(values) if values else None
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1) if values and len(values) > 1 else None
    standard_error = math.sqrt(variance / len(values)) if variance is not None else None
    confidence = (mean - 1.96 * standard_error, mean + 1.96 * standard_error) if mean is not None and standard_error is not None else None
    p95 = _percentile(values, 0.95) if values else None
    delta = 100 * (p95 - baseline_p95) / baseline_p95 if p95 is not None and baseline_p95 else None
    if baseline_p95 is None:
        reasons.add("BASELINE_MISSING")
    if budget_p95 is not None and p95 is not None and p95 > budget_p95:
        reasons.add("BUDGET_EXCEEDED")
    status = "PASS" if values and len(values) >= minimum_samples and not reasons else ("BLOCKED" if not values or baseline_p95 is None else "FAIL")
    payload = {"values": values, "baseline": baseline_p95, "budget": budget_p95, "reasons": sorted(reasons)}
    return BenchmarkSummary(status, len(values), _percentile(values, 0.50) if values else None, p95, _percentile(values, 0.99) if values else None, mean, variance, confidence, delta, tuple(sorted(reasons)), _hash(payload))


class PerformanceBenchmarkAgent:
    def summarize(self, request: Mapping[str, Any]) -> BenchmarkSummary:
        return summarize_benchmark(list(request.get("samples", ())), baseline_p95=request.get("baseline_p95"), budget_p95=request.get("budget_p95"), minimum_samples=int(request.get("minimum_samples", 10)))


__all__ = ["BenchmarkSummary", "PerformanceBenchmarkAgent", "SCHEMA", "summarize_benchmark"]
