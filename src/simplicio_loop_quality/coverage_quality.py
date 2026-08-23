"""Coverage dimensions and threshold evaluation with explicit missing states."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-coverage/v1"
DIMENSIONS = ("line", "branch", "condition", "changed", "critical")


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class CoverageDimension:
    name: str
    covered: int
    total: int
    minimum_percent: float

    @property
    def percent(self) -> float:
        return 100.0 if self.total == 0 else (100.0 * self.covered / self.total)


@dataclass(frozen=True)
class CoverageReport:
    status: str
    dimensions: tuple[CoverageDimension, ...]
    reason_codes: tuple[str, ...]
    report_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "dimensions": [{**item.__dict__, "percent": item.percent} for item in self.dimensions], "reason_codes": list(self.reason_codes), "report_id": self.report_id}


def evaluate_coverage(metrics: Mapping[str, Mapping[str, Any]], thresholds: Mapping[str, float]) -> CoverageReport:
    dimensions: list[CoverageDimension] = []
    reasons: set[str] = set()
    for name in DIMENSIONS:
        raw = metrics.get(name)
        if not isinstance(raw, Mapping):
            reasons.add(f"{name.upper()}_MISSING")
            continue
        try:
            covered, total = int(raw["covered"]), int(raw["total"])
        except (KeyError, TypeError, ValueError):
            reasons.add(f"{name.upper()}_INVALID")
            continue
        minimum = float(thresholds.get(name, 0))
        if covered < 0 or total < 0 or covered > total or minimum < 0 or minimum > 100:
            reasons.add(f"{name.upper()}_INVALID")
            continue
        dimension = CoverageDimension(name, covered, total, minimum)
        dimensions.append(dimension)
        if dimension.percent < minimum:
            reasons.add(f"{name.upper()}_BELOW_THRESHOLD")
    status = (
        "PASS"
        if len(dimensions) == len(DIMENSIONS) and not reasons
        else ("BLOCKED" if not dimensions else "FAIL")
    )
    payload = {"status": status, "dimensions": [item.__dict__ for item in dimensions], "reasons": sorted(reasons)}
    return CoverageReport(status, tuple(dimensions), tuple(sorted(reasons)), _hash(payload))


class CoverageAgent:
    def evaluate(self, request: Mapping[str, Any]) -> CoverageReport:
        return evaluate_coverage(request.get("metrics", {}), request.get("thresholds", {}))


__all__ = [
    "DIMENSIONS",
    "CoverageAgent",
    "CoverageDimension",
    "CoverageReport",
    "SCHEMA",
    "evaluate_coverage",
]
