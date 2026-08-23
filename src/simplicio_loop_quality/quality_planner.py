"""Stateless deterministic quality plan compilation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-plan/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class QualityPlan:
    status: str
    lanes: tuple[str, ...]
    agents: tuple[str, ...]
    dependencies: tuple[tuple[str, str], ...]
    resources: Mapping[str, str]
    blockers: tuple[str, ...]
    plan_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "lanes": list(self.lanes), "agents": list(self.agents), "dependencies": [list(x) for x in self.dependencies], "resources": dict(self.resources), "blockers": list(self.blockers), "plan_hash": self.plan_hash}


def compile_quality_plan(policy: Mapping[str, Any], impact: Mapping[str, Any], traceability: Mapping[str, Any]) -> QualityPlan:
    blockers: set[str] = set()
    lanes = set(str(lane) for lane in policy.get("mandatory_lanes", ()))
    lanes.update(str(lane) for lane in impact.get("mandatory_lanes", ()))
    if not lanes:
        blockers.add("MANDATORY_LANES_MISSING")
    if traceability.get("status") not in {"PASS", "ACCEPTED"}:
        blockers.add("TRACEABILITY_BLOCKED")
    mapping = {"static_quality": "static_quality_agent", "unit": "unit_component_agent", "component": "unit_component_agent", "contract": "integration_contract_agent", "invariants": "invariant_review_agent", "evidence_audit": "evidence_audit_agent"}
    agents = {mapping[lane] for lane in lanes if lane in mapping}
    if len(agents) < len(lanes - set(mapping) ):
        blockers.add("LANE_AGENT_MAPPING_MISSING")
    dependencies = tuple(sorted((mapping[left], mapping[right]) for left, right in (("static_quality", "evidence_audit"), ("unit", "evidence_audit")) if left in lanes and right in lanes))
    resources = {agent: "test" for agent in sorted(agents)}
    payload = {"lanes": sorted(lanes), "agents": sorted(agents), "dependencies": dependencies, "resources": resources, "blockers": sorted(blockers)}
    return QualityPlan("PLANNED" if not blockers else "BLOCKED", tuple(sorted(lanes)), tuple(sorted(agents)), dependencies, resources, tuple(sorted(blockers)), _hash(payload))


class QualityPlannerAgent:
    def plan(self, request: Mapping[str, Any]) -> QualityPlan:
        return compile_quality_plan(request.get("policy", {}), request.get("impact", {}), request.get("traceability", {}))


__all__ = ["QualityPlan", "QualityPlannerAgent", "SCHEMA", "compile_quality_plan"]
