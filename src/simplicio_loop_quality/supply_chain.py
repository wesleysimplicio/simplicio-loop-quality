"""Supply-chain provenance and dependency-lock validation."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

SCHEMA = "simplicio.quality-supply-chain/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def plan_supply_chain(files: list[str]) -> dict[str, Any]:
    lockfiles = tuple(sorted(path for path in files if path.endswith((".lock", "lock.json", "poetry.lock", "Cargo.lock"))))
    tools = ("dependency-audit", "license-audit", "provenance", "artifact-integrity")
    status = "PLANNED" if lockfiles else "BLOCKED"
    reasons = [] if lockfiles else ["LOCKFILE_MISSING"]
    payload = {"lockfiles": lockfiles, "tools": tools, "reasons": reasons}
    return {"schema": SCHEMA, "status": status, "lockfiles": lockfiles, "tools": tools, "reason_codes": reasons, "plan_id": _hash(payload)}


def normalize_supply_chain(result: Mapping[str, Any], *, expected_plan_id: str) -> dict[str, Any]:
    reasons = []
    if result.get("plan_id") != expected_plan_id:
        reasons.append("PLAN_STALE")
    if not result.get("dependency_digests"):
        reasons.append("DEPENDENCY_DIGESTS_MISSING")
    if result.get("license_findings"):
        reasons.append("LICENSE_FINDINGS")
    status = str(result.get("status", "BLOCKED")).upper()
    if reasons:
        status = "BLOCKED"
    return {"schema": SCHEMA, "status": status, "reason_codes": reasons}


__all__ = ["SCHEMA", "normalize_supply_chain", "plan_supply_chain"]
