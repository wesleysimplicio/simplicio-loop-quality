"""Correlated quality events and historical trend comparison."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

SCHEMA = "simplicio.quality-observability/v1"


def correlation_id(identity: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(identity), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def compare_trend(current: Mapping[str, float], baseline: Mapping[str, float]) -> dict[str, Any]:
    regressions = {key: float(current[key]) - float(baseline[key]) for key in current if key in baseline and float(current[key]) > float(baseline[key])}
    return {"schema": SCHEMA, "status": "FAIL" if regressions else "PASS", "regressions": regressions, "metrics": dict(current)}


def build_observation(identity: Mapping[str, Any], event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"schema": SCHEMA, "correlation_id": correlation_id(identity), "event_type": event_type, "payload": dict(payload)}


__all__ = ["SCHEMA", "build_observation", "compare_trend", "correlation_id"]
