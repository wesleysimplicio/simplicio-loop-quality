"""Fail-closed quality lifecycle hook validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-hook/v1"


@dataclass(frozen=True)
class HookDecision:
    status: str
    mode: str
    reason_codes: tuple[str, ...]
    provider_status: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "mode": self.mode, "reason_codes": list(self.reason_codes), "provider_status": self.provider_status}


def validate_hook_result(result: Mapping[str, Any] | None, *, required: bool = True, mode: str = "required") -> HookDecision:
    reasons: list[str] = []
    if mode not in {"required", "plan_only", "diagnostic"}:
        reasons.append("HOOK_MODE_INVALID")
        mode = "required"
    if result is None:
        reasons.append("PROVIDER_MISSING")
    else:
        provider_status = str(result.get("status", "")).upper()
        if provider_status not in {"PASS", "FAIL", "BLOCKED", "PLANNED"}:
            reasons.append("PROVIDER_RESULT_INVALID")
        if result.get("partial_write"):
            reasons.append("PARTIAL_RESULT_WRITE")
        if result.get("crashed"):
            reasons.append("PROVIDER_CRASHED")
    provider_status = str(result.get("status")).upper() if result and result.get("status") is not None else None
    if not required and mode == "diagnostic" and reasons == ["PROVIDER_MISSING"]:
        reasons = []
    status = "ACCEPTED" if not reasons else "BLOCKED"
    if provider_status == "FAIL" and required:
        status = "FAIL"
    return HookDecision(status, mode, tuple(sorted(set(reasons))), provider_status)


__all__ = ["HookDecision", "SCHEMA", "validate_hook_result"]
