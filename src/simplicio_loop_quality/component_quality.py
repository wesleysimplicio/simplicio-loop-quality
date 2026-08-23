"""Component-test planning from impact boundaries and cleanup evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-component/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Component:
    component_id: str
    boundary: tuple[str, ...]
    collaborators: tuple[str, ...]
    command: tuple[str, ...]


@dataclass(frozen=True)
class ComponentTestPlan:
    status: str
    components: tuple[Component, ...]
    overlap: Mapping[str, tuple[str, ...]]
    source_sha: str
    policy_hash: str
    request_id: str
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "status": self.status,
            "components": [{"component_id": c.component_id, "boundary": list(c.boundary), "collaborators": list(c.collaborators), "command": list(c.command)} for c in self.components],
            "overlap": {key: list(value) for key, value in sorted(self.overlap.items())},
            "source_sha": self.source_sha,
            "policy_hash": self.policy_hash,
            "request_id": self.request_id,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class ComponentResult:
    component_id: str
    status: str
    cleanup_evidence_ref: str | None
    reason_codes: tuple[str, ...] = ()


def discover_components(impact: Mapping[str, Any]) -> tuple[Component, ...]:
    raw = impact.get("components")
    components: list[Component] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, Mapping) or not item.get("id"):
                continue
            components.append(Component(
                str(item["id"]),
                tuple(sorted(str(path) for path in item.get("boundary", item.get("paths", ())))),
                tuple(sorted(str(name) for name in item.get("collaborators", ()))) ,
                tuple(str(arg) for arg in item.get("command", ("python", "-m", "pytest"))),
            ))
    if not components:
        paths = impact.get("impacted_files", impact.get("changed_files", ()))
        grouped: dict[str, list[str]] = {}
        for path in paths if isinstance(paths, list) else ():
            name = str(path).split("/", 2)[1] if "/" in str(path) else "root"
            grouped.setdefault(name, []).append(str(path))
        for name, values in grouped.items():
            components.append(Component(name, tuple(sorted(values)), (), ("python", "-m", "pytest", name)))
    return tuple(sorted(components, key=lambda item: item.component_id))


def _overlap(components: tuple[Component, ...], impact: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    unit = {str(item) for item in impact.get("unit_tests", ()) if isinstance(item, str)}
    integration = {str(item) for item in impact.get("integration_tests", ()) if isinstance(item, str)}
    result: dict[str, tuple[str, ...]] = {}
    for component in components:
        overlap = sorted(set(component.boundary) & (unit | integration))
        result[component.component_id] = tuple(overlap)
    return result


def plan_component_tests(impact: Mapping[str, Any], *, source_sha: str, policy_hash: str) -> ComponentTestPlan:
    components = discover_components(impact)
    overlap = _overlap(components, impact)
    payload = {"source_sha": source_sha, "policy_hash": policy_hash, "components": [component.__dict__ for component in components], "overlap": overlap}
    return ComponentTestPlan("PLANNED" if components else "BLOCKED", components, overlap, source_sha, policy_hash, _hash(payload), () if components else ("COMPONENT_BOUNDARY_UNAVAILABLE",))


def normalize_component_results(results: list[Mapping[str, Any]] | None, *, source_sha: str, policy_hash: str) -> dict[str, Any]:
    if not results:
        return {"schema": SCHEMA, "status": "BLOCKED", "reason_codes": ["COMPONENT_RESULTS_EMPTY"], "results": [], "source_sha": source_sha, "policy_hash": policy_hash}
    normalized: list[ComponentResult] = []
    for item in results:
        component_id = str(item.get("component_id", ""))
        status = str(item.get("status", "BLOCKED")).upper()
        evidence = item.get("cleanup_evidence_ref")
        reasons: list[str] = []
        if not component_id:
            reasons.append("COMPONENT_ID_MISSING")
        if status not in {"PASS", "FAIL", "BLOCKED"}:
            reasons.append("STATUS_INVALID")
        if not evidence:
            reasons.append("CLEANUP_EVIDENCE_MISSING")
        if reasons:
            status = "BLOCKED"
        normalized.append(ComponentResult(component_id, status, str(evidence) if evidence else None, tuple(sorted(set(reasons)))))
    overall = "PASS" if normalized and all(item.status == "PASS" for item in normalized) else "FAIL"
    if any(item.status == "BLOCKED" for item in normalized):
        overall = "BLOCKED"
    return {"schema": SCHEMA, "status": overall, "results": [item.__dict__ for item in sorted(normalized, key=lambda x: x.component_id)], "source_sha": source_sha, "policy_hash": policy_hash}


class ComponentTestAgent:
    def plan(self, request: Mapping[str, Any]) -> ComponentTestPlan:
        return plan_component_tests(request, source_sha=str(request.get("source_sha", "")), policy_hash=str(request.get("policy_hash", "")))


__all__ = ["Component", "ComponentResult", "ComponentTestAgent", "ComponentTestPlan", "SCHEMA", "discover_components", "normalize_component_results", "plan_component_tests"]
