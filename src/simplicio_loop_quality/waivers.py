"""Fail-closed, auditable waiver validation for quality lanes.

Waivers are data, not permissions hidden in runner code.  This module validates
their scope and provenance; it never auto-approves a missing or malformed
waiver and never treats a tool failure as a clean result.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA = "simplicio.quality-waiver/v1"
REASON_CODES = frozenset(
    {"NOT_APPLICABLE", "TOOL_UNAVAILABLE", "ENVIRONMENT_UNAVAILABLE", "RISK_ACCEPTED"}
)
OVERBROAD = frozenset({"*", "**", "all", "global"})


class WaiverError(ValueError):
    """Raised when a waiver violates the policy contract."""


@dataclass(frozen=True)
class WaiverVerdict:
    status: str
    waiver_id: str | None
    reason_codes: tuple[str, ...]
    lane: str
    scope: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "status": self.status,
            "waiver_id": self.waiver_id,
            "reason_codes": list(self.reason_codes),
            "lane": self.lane,
            "scope": self.scope,
        }


def _blocked(lane: str, scope: str, *reasons: str) -> WaiverVerdict:
    return WaiverVerdict("BLOCKED", None, tuple(sorted(set(reasons))), lane, scope)


def _parse_expiry(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def evaluate_waiver(
    value: Mapping[str, Any] | None,
    *,
    lane: str,
    source_sha: str,
    policy_hash: str,
    now: datetime | None = None,
) -> WaiverVerdict:
    """Return an explicit APPROVED/BLOCKED verdict for one lane."""

    if not value:
        return _blocked(lane, lane, "WAIVER_MISSING")
    scope = str(value.get("scope", ""))
    waiver_id = str(value.get("waiver_id", ""))
    reasons: list[str] = []
    if not waiver_id:
        reasons.append("WAIVER_ID_MISSING")
    reason_code = str(value.get("reason_code", ""))
    if reason_code not in REASON_CODES:
        reasons.append("REASON_CODE_INVALID")
    if not str(value.get("justification", "")).strip():
        reasons.append("JUSTIFICATION_MISSING")
    if not scope or scope in OVERBROAD:
        reasons.append("SCOPE_OVERBROAD")
    elif scope != lane:
        reasons.append("SCOPE_MISMATCH")
    created_by = str(value.get("created_by", "")).strip()
    approver = str(value.get("approver", "")).strip()
    if not created_by or not approver:
        reasons.append("APPROVER_MISSING")
    elif created_by == approver:
        reasons.append("SELF_APPROVED")
    expiry = _parse_expiry(value.get("expires_at"))
    current = now or datetime.now(timezone.utc)
    if expiry is None:
        reasons.append("EXPIRY_INVALID")
    elif expiry.astimezone(timezone.utc) <= current.astimezone(timezone.utc):
        reasons.append("WAIVER_EXPIRED")
    if value.get("source_sha") != source_sha:
        reasons.append("SOURCE_STALE")
    if value.get("policy_hash") != policy_hash:
        reasons.append("POLICY_STALE")
    if reasons:
        return WaiverVerdict("BLOCKED", waiver_id or None, tuple(sorted(set(reasons))), lane, scope)
    return WaiverVerdict("APPROVED", waiver_id, (), lane, scope)


def waiver_policy_hash(policy: Mapping[str, Any]) -> str:
    """Create a stable policy identity for binding waivers to policy text."""

    encoded = json.dumps(policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def select_waivers(
    values: Mapping[str, Mapping[str, Any]],
    *,
    required_lanes: tuple[str, ...] | list[str],
    source_sha: str,
    policy_hash: str,
    now: datetime | None = None,
) -> tuple[WaiverVerdict, ...]:
    """Validate one explicitly scoped waiver per excluded lane."""

    verdicts = tuple(
        evaluate_waiver(values.get(lane), lane=lane, source_sha=source_sha, policy_hash=policy_hash, now=now)
        for lane in sorted(set(required_lanes))
    )
    if any(item.status != "APPROVED" for item in verdicts):
        return verdicts
    ids = [item.waiver_id for item in verdicts]
    if len(ids) != len(set(ids)):
        return tuple(
            WaiverVerdict("BLOCKED", item.waiver_id, ("DUPLICATE_WAIVER_ID",), item.lane, item.scope)
            for item in verdicts
        )
    return verdicts


__all__ = ["SCHEMA", "WaiverError", "WaiverVerdict", "evaluate_waiver", "select_waivers", "waiver_policy_hash"]
