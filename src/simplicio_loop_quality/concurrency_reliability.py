"""Concurrency/recovery scenario planning and race/deadlock normalization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-concurrency/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class ConcurrencyPlan:
    status: str
    scenarios: tuple[str, ...]
    workers: int
    plan_id: str
    reason_codes: tuple[str, ...] = ()


def plan_concurrency(request: Mapping[str, Any]) -> ConcurrencyPlan:
    scenarios = tuple(sorted(str(x) for x in request.get("scenarios", ("race", "deadlock", "cancel"))))
    workers = request.get("workers", 2)
    reasons = []
    if not isinstance(workers, int) or isinstance(workers, bool) or workers < 2:
        reasons.append("WORKER_COUNT_INVALID")
        workers = 0
    payload = {"scenarios": scenarios, "workers": workers}
    return ConcurrencyPlan("PLANNED" if not reasons else "BLOCKED", scenarios, workers, _hash(payload), tuple(reasons))


def normalize_concurrency_result(result: Mapping[str, Any], *, expected_plan_id: str) -> dict[str, Any]:
    reasons = []
    if result.get("plan_id") != expected_plan_id:
        reasons.append("PLAN_STALE")
    if result.get("resource_cleanup") is not True:
        reasons.append("RESOURCE_CLEANUP_UNVERIFIED")
    if result.get("race_detected") or result.get("deadlock_detected"):
        reasons.append("CONCURRENCY_DEFECT")
    status = str(result.get("status", "BLOCKED")).upper()
    if reasons:
        status = "BLOCKED" if "RESOURCE_CLEANUP_UNVERIFIED" in reasons or "PLAN_STALE" in reasons else "FAIL"
    return {"schema": SCHEMA, "status": status, "reason_codes": reasons}


__all__ = ["ConcurrencyPlan", "SCHEMA", "normalize_concurrency_result", "plan_concurrency"]
