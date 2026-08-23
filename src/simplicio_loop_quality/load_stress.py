"""Load/stress/soak budget planning and resource-evidence checks."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

SCHEMA = "simplicio.quality-load-stress/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def plan_load_stress(request: Mapping[str, Any]) -> dict[str, Any]:
    duration = request.get("duration_seconds", 0)
    concurrency = request.get("concurrency", 0)
    reasons = []
    if not isinstance(duration, int) or duration <= 0:
        reasons.append("DURATION_INVALID")
    if not isinstance(concurrency, int) or concurrency <= 0:
        reasons.append("CONCURRENCY_INVALID")
    payload = {"duration_seconds": duration, "concurrency": concurrency, "mode": request.get("mode", "load")}
    return {"schema": SCHEMA, "status": "PLANNED" if not reasons else "BLOCKED", "duration_seconds": duration, "concurrency": concurrency, "mode": request.get("mode", "load"), "reason_codes": reasons, "plan_id": _hash(payload)}


def normalize_load_result(result: Mapping[str, Any], *, expected_plan_id: str) -> dict[str, Any]:
    reasons = []
    if result.get("plan_id") != expected_plan_id:
        reasons.append("PLAN_STALE")
    if result.get("p95_ms") is None or result.get("throughput") is None:
        reasons.append("PERFORMANCE_METRICS_MISSING")
    if result.get("resource_cleanup") is not True:
        reasons.append("RESOURCE_CLEANUP_UNVERIFIED")
    status = str(result.get("status", "BLOCKED")).upper()
    if reasons:
        status = "BLOCKED"
    return {"schema": SCHEMA, "status": status, "reason_codes": reasons}


__all__ = ["SCHEMA", "normalize_load_result", "plan_load_stress"]
