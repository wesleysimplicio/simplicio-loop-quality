"""Compatibility matrix and migration safety planning."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

SCHEMA = "simplicio.quality-compatibility/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def plan_compatibility(request: Mapping[str, Any]) -> dict[str, Any]:
    versions = tuple(sorted(str(x) for x in request.get("versions", ())))
    migrations = tuple(sorted(str(x) for x in request.get("migrations", ())))
    reasons = []
    if len(versions) < 2:
        reasons.append("COMPATIBILITY_MATRIX_TOO_SMALL")
    if not migrations:
        reasons.append("MIGRATION_CASES_MISSING")
    payload = {"versions": versions, "migrations": migrations}
    return {"schema": SCHEMA, "status": "PLANNED" if not reasons else "BLOCKED", "versions": versions, "migrations": migrations, "reason_codes": reasons, "plan_id": _hash(payload)}


def normalize_compatibility(result: Mapping[str, Any], *, expected_plan_id: str) -> dict[str, Any]:
    reasons = []
    if result.get("plan_id") != expected_plan_id:
        reasons.append("PLAN_STALE")
    if result.get("rollback_evidence_ref") is None:
        reasons.append("ROLLBACK_EVIDENCE_MISSING")
    if result.get("failures"):
        reasons.append("COMPATIBILITY_FAILURES")
    status = str(result.get("status", "BLOCKED")).upper()
    if reasons:
        status = "BLOCKED" if "ROLLBACK_EVIDENCE_MISSING" in reasons else "FAIL"
    return {"schema": SCHEMA, "status": status, "reason_codes": reasons}


__all__ = ["SCHEMA", "normalize_compatibility", "plan_compatibility"]
