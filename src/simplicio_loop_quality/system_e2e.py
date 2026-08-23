"""System/E2E scenario planning with explicit user-visible evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-system-e2e/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class SystemE2EPlan:
    status: str
    scenarios: tuple[str, ...]
    commands: tuple[tuple[str, ...], ...]
    plan_id: str
    reason_codes: tuple[str, ...] = ()


def plan_system_e2e(project: Mapping[str, Any]) -> SystemE2EPlan:
    scenarios = tuple(sorted(str(x) for x in project.get("scenarios", ())))
    reasons = [] if scenarios else ["E2E_SCENARIOS_MISSING"]
    commands = tuple(("system-e2e", scenario) for scenario in scenarios)
    payload = {"scenarios": scenarios, "commands": commands}
    return SystemE2EPlan("PLANNED" if scenarios else "BLOCKED", scenarios, commands, _hash(payload), tuple(reasons))


def normalize_e2e_result(result: Mapping[str, Any], *, expected_plan_id: str) -> dict[str, Any]:
    reasons = []
    if result.get("plan_id") != expected_plan_id:
        reasons.append("PLAN_STALE")
    if not result.get("user_visible_evidence_refs"):
        reasons.append("USER_VISIBLE_EVIDENCE_MISSING")
    status = str(result.get("status", "BLOCKED")).upper()
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        status = "BLOCKED"
        reasons.append("STATUS_INVALID")
    if reasons:
        status = "BLOCKED"
    return {"schema": SCHEMA, "status": status, "reason_codes": reasons, "screenshots": list(result.get("screenshots", ())), "user_visible_evidence_refs": list(result.get("user_visible_evidence_refs", ())) }


class SystemE2EAgent:
    def plan(self, request: Mapping[str, Any]) -> SystemE2EPlan:
        return plan_system_e2e(request)


__all__ = ["SCHEMA", "SystemE2EAgent", "SystemE2EPlan", "normalize_e2e_result", "plan_system_e2e"]
