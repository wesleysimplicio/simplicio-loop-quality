"""Packaged-artifact and real-code smoke-test planning."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-package-smoke/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class PackageSmokePlan:
    status: str
    artifacts: tuple[str, ...]
    commands: tuple[tuple[str, ...], ...]
    real_code_paths: tuple[str, ...]
    plan_id: str
    reason_codes: tuple[str, ...] = ()


def plan_package_smoke(project: Mapping[str, Any]) -> PackageSmokePlan:
    artifacts = tuple(sorted(str(x) for x in project.get("artifacts", ())))
    paths = tuple(sorted(str(x) for x in project.get("real_code_paths", ())))
    reasons = []
    if not artifacts:
        reasons.append("PACKAGED_ARTIFACT_MISSING")
    if not paths:
        reasons.append("REAL_CODE_PATH_MISSING")
    commands = tuple(("package-smoke", artifact, path) for artifact in artifacts for path in paths)
    payload = {"artifacts": artifacts, "paths": paths, "commands": commands}
    return PackageSmokePlan("PLANNED" if not reasons else "BLOCKED", artifacts, commands, paths, _hash(payload), tuple(reasons))


def normalize_package_result(result: Mapping[str, Any], *, expected_plan_id: str) -> dict[str, Any]:
    reasons = []
    if result.get("plan_id") != expected_plan_id:
        reasons.append("PLAN_STALE")
    if not result.get("artifact_sha256"):
        reasons.append("ARTIFACT_DIGEST_MISSING")
    status = str(result.get("status", "BLOCKED")).upper()
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        status = "BLOCKED"
        reasons.append("STATUS_INVALID")
    if reasons:
        status = "BLOCKED"
    return {"schema": SCHEMA, "status": status, "reason_codes": reasons, "artifact_sha256": result.get("artifact_sha256"), "evidence_refs": list(result.get("evidence_refs", ())) }


class PackageSmokeAgent:
    def plan(self, request: Mapping[str, Any]) -> PackageSmokePlan:
        return plan_package_smoke(request)


__all__ = ["PackageSmokeAgent", "PackageSmokePlan", "SCHEMA", "normalize_package_result", "plan_package_smoke"]
