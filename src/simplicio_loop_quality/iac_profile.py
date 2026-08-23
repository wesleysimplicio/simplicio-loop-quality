"""Infrastructure-as-code quality profile planning."""

from __future__ import annotations

from typing import Any, Mapping

SCHEMA = "simplicio.quality-iac-profile/v1"


def plan_iac_profile(files: list[str]) -> dict[str, Any]:
    files = sorted(str(x) for x in files)
    kinds = sorted({"terraform" if path.endswith(".tf") else "kubernetes" if path.endswith((".yaml", ".yml")) else "ansible" if "ansible" in path else "" for path in files} - {""})
    reasons = [] if kinds else ["IAC_FILES_MISSING"]
    checks = ("format", "schema", "security", "plan-diff", "drift")
    return {"schema": SCHEMA, "status": "PLANNED" if kinds else "BLOCKED", "kinds": kinds, "checks": checks, "reason_codes": reasons}


def normalize_iac_result(result: Mapping[str, Any]) -> dict[str, Any]:
    status = str(result.get("status", "BLOCKED")).upper()
    if not result.get("plan_digest"):
        status = "BLOCKED"
    return {"schema": SCHEMA, "status": status if status in {"PASS", "FAIL", "BLOCKED"} else "BLOCKED", "plan_digest": result.get("plan_digest"), "findings": list(result.get("findings", ())) }


__all__ = ["SCHEMA", "normalize_iac_result", "plan_iac_profile"]
