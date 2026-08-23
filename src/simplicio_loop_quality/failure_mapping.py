"""Quality failure classification without a local retry engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-failure-mapping/v1"


@dataclass(frozen=True)
class FailureDecision:
    category: str
    reason_code: str
    retry_hint: bool
    status: str
    preserve_first: bool = True
    preserve_final: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, **self.__dict__}


_RULES = {
    "timeout": ("transient", "TIMEOUT", True, "BLOCKED"),
    "rate_limit": ("transient", "RATE_LIMIT", True, "BLOCKED"),
    "oom": ("resource", "OUT_OF_MEMORY", False, "BLOCKED"),
    "cancelled": ("cancelled", "CANCELLED", False, "BLOCKED"),
    "permission": ("permanent", "PERMISSION_DENIED", False, "FAIL"),
    "assertion": ("permanent", "ASSERTION_FAILED", False, "FAIL"),
    "unknown": ("policy", "UNKNOWN_FAILURE", False, "BLOCKED"),
}


def map_failure(failure: Mapping[str, Any], *, attempts_remaining: int) -> FailureDecision:
    kind = str(failure.get("kind", "unknown")).lower()
    category, code, retryable, status = _RULES.get(kind, _RULES["unknown"])
    retry_hint = retryable and attempts_remaining > 0
    if not attempts_remaining and retryable:
        status = "FAIL"
        code = "RETRY_EXHAUSTED"
    return FailureDecision(category, code, retry_hint, status)


__all__ = ["FailureDecision", "SCHEMA", "map_failure"]
