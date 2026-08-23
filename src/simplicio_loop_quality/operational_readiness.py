"""Operational-readiness planning with fail-closed evidence checks."""

from __future__ import annotations

from typing import Any, Mapping

SCHEMA = "simplicio.quality-operational-readiness/v1"
REQUIRED = ("healthchecks", "alerts", "rollback", "cleanup", "runbook")


def plan_operational_readiness(requirements: Mapping[str, Any]) -> dict[str, Any]:
    missing = sorted(name for name in REQUIRED if not requirements.get(name))
    checks = tuple(REQUIRED)
    return {
        "schema": SCHEMA,
        "status": "PLANNED" if not missing else "BLOCKED",
        "checks": checks,
        "missing_requirements": missing,
        "reason_codes": ["READINESS_REQUIREMENTS_MISSING"] if missing else [],
    }


def normalize_readiness(result: Mapping[str, Any]) -> dict[str, Any]:
    reasons = []
    if str(result.get("status", "")).upper() not in {"PASS", "FAIL"}:
        reasons.append("READINESS_STATUS_INVALID")
    if not result.get("evidence_refs"):
        reasons.append("READINESS_EVIDENCE_MISSING")
    if result.get("failed_checks"):
        reasons.append("READINESS_CHECK_FAILED")
    return {
        "schema": SCHEMA,
        "status": "BLOCKED" if reasons else str(result["status"]).upper(),
        "reason_codes": reasons,
    }


__all__ = ["REQUIRED", "SCHEMA", "normalize_readiness", "plan_operational_readiness"]
