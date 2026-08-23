"""Database/data-pipeline profile planning and migration safety checks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-data-profile/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class DataQualityPlan:
    status: str
    engine: str | None
    commands: tuple[tuple[str, ...], ...]
    checks: tuple[str, ...]
    reason_codes: tuple[str, ...]
    plan_id: str


def plan_data_quality(project: Mapping[str, Any]) -> DataQualityPlan:
    files = {str(path) for path in project.get("files", ())}
    engine = next((name for name in ("postgres", "mysql", "sqlite", "bigquery", "snowflake") if name in project.get("engines", ())), None)
    checks = {"schema_drift", "migration_reversibility", "idempotent_seed", "nullability", "referential_integrity"}
    if any(path.endswith((".sql", ".dbml")) for path in files):
        checks.add("sql_contract")
    reasons = () if engine else ("DATA_ENGINE_UNAVAILABLE",)
    commands = (("migration", "validate"), ("migration", "up", "--dry-run"), ("migration", "down", "--dry-run")) if engine else ()
    payload = {"engine": engine, "commands": commands, "checks": sorted(checks), "files": sorted(files)}
    return DataQualityPlan("PLANNED" if engine else "BLOCKED", engine, commands, tuple(sorted(checks)), reasons, _hash(payload))


def normalize_data_result(result: Mapping[str, Any], *, expected_plan_id: str) -> dict[str, Any]:
    reasons = []
    if result.get("plan_id") != expected_plan_id:
        reasons.append("PLAN_STALE")
    if not result.get("evidence_refs"):
        reasons.append("EVIDENCE_MISSING")
    status = str(result.get("status", "BLOCKED")).upper()
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        reasons.append("STATUS_INVALID")
        status = "BLOCKED"
    if reasons:
        status = "BLOCKED"
    return {"schema": SCHEMA, "status": status, "findings": list(result.get("findings", ())), "reason_codes": reasons, "evidence_refs": list(result.get("evidence_refs", ())) }


class DataQualityProfile:
    def plan(self, request: Mapping[str, Any]) -> DataQualityPlan:
        return plan_data_quality(request)


__all__ = ["DataQualityPlan", "DataQualityProfile", "SCHEMA", "normalize_data_result", "plan_data_quality"]
