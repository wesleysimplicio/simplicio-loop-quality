"""Integration-test stage planning around real collaborators."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-integration/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class IntegrationPlan:
    status: str
    collaborators: tuple[str, ...]
    commands: tuple[tuple[str, ...], ...]
    seed: int | None
    cleanup_required: bool
    plan_id: str
    reason_codes: tuple[str, ...] = ()


def plan_integration(project: Mapping[str, Any]) -> IntegrationPlan:
    collaborators = tuple(sorted(str(x) for x in project.get("collaborators", ())))
    reasons = [] if collaborators else ["REAL_COLLABORATORS_MISSING"]
    if project.get("cleanup_required", True) is not True:
        reasons.append("CLEANUP_REQUIRED")
    commands = (("integration", "happy-path"), ("integration", "failure-path"), ("integration", "idempotency")) if collaborators else ()
    payload = {"collaborators": collaborators, "commands": commands, "seed": project.get("seed"), "cleanup_required": project.get("cleanup_required", True)}
    return IntegrationPlan("PLANNED" if not reasons else "BLOCKED", collaborators, commands, project.get("seed"), True, _hash(payload), tuple(sorted(reasons)))


def normalize_integration_result(result: Mapping[str, Any], *, expected_plan_id: str) -> dict[str, Any]:
    reasons = []
    if result.get("plan_id") != expected_plan_id:
        reasons.append("PLAN_STALE")
    if not result.get("cleanup_evidence_ref"):
        reasons.append("CLEANUP_EVIDENCE_MISSING")
    status = str(result.get("status", "BLOCKED")).upper()
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        status = "BLOCKED"
        reasons.append("STATUS_INVALID")
    if reasons:
        status = "BLOCKED"
    return {"schema": SCHEMA, "status": status, "findings": list(result.get("findings", ())), "reason_codes": reasons}


class IntegrationTestAgent:
    def plan(self, request: Mapping[str, Any]) -> IntegrationPlan:
        return plan_integration(request)


__all__ = ["IntegrationPlan", "IntegrationTestAgent", "SCHEMA", "normalize_integration_result", "plan_integration"]
