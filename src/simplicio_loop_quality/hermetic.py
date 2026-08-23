"""Declarative hermetic-environment requests and cleanup verification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-hermetic-environment/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class EnvironmentPlan:
    status: str
    services: tuple[str, ...]
    ports: tuple[int, ...]
    filesystem: tuple[str, ...]
    network: str
    credentials: tuple[str, ...]
    seed: int | None
    cleanup_required: bool
    plan_id: str
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, **self.__dict__}


def plan_environment(request: Mapping[str, Any]) -> EnvironmentPlan:
    reasons: set[str] = set()
    services = tuple(sorted(str(item) for item in request.get("services", ()) if item))
    ports = tuple(sorted(int(item) for item in request.get("ports", ()) if isinstance(item, int) and 0 < item < 65536))
    filesystem = tuple(sorted(str(item) for item in request.get("filesystem", ()) if item))
    credentials = tuple(sorted(str(item) for item in request.get("credentials", ()) if item))
    network = str(request.get("network", "none"))
    if network not in {"none", "allowlist"}:
        reasons.add("NETWORK_POLICY_INVALID")
    if len(ports) != len(tuple(request.get("ports", ()) or ())):
        reasons.add("PORT_REQUEST_INVALID")
    if request.get("cleanup_required", True) is not True:
        reasons.add("CLEANUP_REQUIRED")
    if any(path.startswith("/") or ".." in path.split("/") for path in filesystem):
        reasons.add("FILESYSTEM_SCOPE_INVALID")
    payload = {"services": services, "ports": ports, "filesystem": filesystem, "network": network, "credentials": credentials, "seed": request.get("seed"), "cleanup_required": request.get("cleanup_required", True)}
    return EnvironmentPlan("PLANNED" if not reasons else "BLOCKED", services, ports, filesystem, network, credentials, request.get("seed"), True, _hash(payload), tuple(sorted(reasons)))


def verify_cleanup(*, owned_resources: list[str], released_resources: list[str], cleanup_receipt: str | None) -> dict[str, Any]:
    owned, released = set(owned_resources), set(released_resources)
    missing = sorted(owned - released)
    status = "PASS" if cleanup_receipt and not missing else "BLOCKED"
    reasons = [] if status == "PASS" else (["CLEANUP_RECEIPT_MISSING"] if not cleanup_receipt else [])
    if missing:
        reasons.append("RESOURCES_NOT_RELEASED")
    return {"schema": SCHEMA, "status": status, "missing_resources": missing, "reason_codes": reasons, "cleanup_receipt": cleanup_receipt}


class HermeticEnvironmentAgent:
    def plan(self, request: Mapping[str, Any]) -> EnvironmentPlan:
        return plan_environment(request)


__all__ = ["EnvironmentPlan", "HermeticEnvironmentAgent", "SCHEMA", "plan_environment", "verify_cleanup"]
