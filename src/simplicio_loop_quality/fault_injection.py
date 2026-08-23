"""Controlled fault-injection scenarios and recovery evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-fault-injection/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class FaultPlan:
    status: str
    faults: tuple[str, ...]
    plan_id: str
    reason_codes: tuple[str, ...] = ()


def plan_faults(request: Mapping[str, Any]) -> FaultPlan:
    faults = tuple(sorted(str(x) for x in request.get("faults", ("timeout", "permission", "external_failure"))))
    allowed = {"timeout", "permission", "external_failure", "invalid_input", "crash"}
    reasons = ("FAULT_KIND_UNSUPPORTED",) if any(item not in allowed for item in faults) else ()
    payload = {"faults": faults}
    return FaultPlan("PLANNED" if not reasons else "BLOCKED", faults, _hash(payload), reasons)


def normalize_recovery(result: Mapping[str, Any], *, expected_plan_id: str) -> dict[str, Any]:
    reasons = []
    if result.get("plan_id") != expected_plan_id:
        reasons.append("PLAN_STALE")
    if not result.get("recovery_evidence_ref"):
        reasons.append("RECOVERY_EVIDENCE_MISSING")
    if result.get("resources_released") is not True:
        reasons.append("RESOURCES_NOT_RELEASED")
    status = str(result.get("status", "BLOCKED")).upper()
    if reasons:
        status = "BLOCKED"
    return {"schema": SCHEMA, "status": status, "reason_codes": reasons}


__all__ = ["FaultPlan", "SCHEMA", "normalize_recovery", "plan_faults"]
