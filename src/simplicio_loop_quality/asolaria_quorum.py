"""Tri-vantage, independent quality quorum validation."""

from __future__ import annotations

from typing import Any, Mapping

SCHEMA = "simplicio.quality-asolaria-quorum/v1"
SEATS = ("executor", "verifier", "auditor")


def evaluate_quorum(
    criteria: list[str],
    seats: Mapping[str, Mapping[str, Any]],
    *,
    source_sha: str,
    policy_hash: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    identities: set[tuple[str, str, str, str]] = set()
    for seat in SEATS:
        value = seats.get(seat)
        if not isinstance(value, Mapping):
            reasons.append(f"{seat.upper()}_MISSING")
            continue
        identity = (
            str(value.get("agent_address", "")),
            str(value.get("context_hash", "")),
            str(value.get("prompt_hash", "")),
            str(value.get("seed", "")),
        )
        if not all(identity):
            reasons.append(f"{seat.upper()}_IDENTITY_INCOMPLETE")
        if identity in identities:
            reasons.append("INDEPENDENCE_COLLISION")
        identities.add(identity)
        if value.get("source_sha") != source_sha:
            reasons.append("SOURCE_BINDING_MISMATCH")
        if value.get("policy_hash") != policy_hash:
            reasons.append("POLICY_BINDING_MISMATCH")
        if not value.get("evidence_refs"):
            reasons.append("EVIDENCE_MISSING")
        if not set(criteria).issubset(set(value.get("criteria_refs", ()))):
            reasons.append(f"{seat.upper()}_TRACEABILITY_INCOMPLETE")
        if value.get("stale"):
            reasons.append("EVIDENCE_STALE")
        if value.get("timed_out"):
            reasons.append("SEAT_TIMEOUT")
    if not seats.get("clean_control"):
        reasons.append("CLEAN_CONTROL_MISSING")
    status = "PASS" if not reasons else "BLOCKED" if "EVIDENCE_MISSING" in reasons else "FAIL"
    return {
        "schema": SCHEMA,
        "status": status,
        "seats": SEATS,
        "reason_codes": sorted(set(reasons)),
    }


__all__ = ["SCHEMA", "SEATS", "evaluate_quorum"]
