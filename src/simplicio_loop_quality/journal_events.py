"""Idempotent quality event normalization for the Loop journal."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-journal-event/v1"


def event_key(identity: Mapping[str, Any], event_type: str, sequence: int) -> str:
    payload = {"identity": dict(identity), "event_type": event_type, "sequence": sequence}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class EventDecision:
    status: str
    key: str
    reason_codes: tuple[str, ...] = ()


def accept_event(
    event: Mapping[str, Any],
    *,
    last_sequence: int | None,
    expected_identity: Mapping[str, Any],
) -> EventDecision:
    identity = event.get("identity")
    reasons: list[str] = []
    if not isinstance(identity, Mapping) or dict(identity) != dict(expected_identity):
        reasons.append("IDENTITY_MISMATCH")
    event_type = str(event.get("event_type", ""))
    sequence = event.get("sequence")
    if (
        not event_type
        or not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or sequence < 0
    ):
        reasons.append("EVENT_SHAPE_INVALID")
        sequence = int(sequence) if isinstance(sequence, int) and not isinstance(sequence, bool) else 0
    if last_sequence is not None and sequence < last_sequence:
        reasons.append("EVENT_OUT_OF_ORDER")
    key = event_key(expected_identity, event_type, sequence)
    if event.get("idempotency_key") not in {None, key}:
        reasons.append("IDEMPOTENCY_KEY_MISMATCH")
    status = "ACCEPTED" if not reasons else "REJECTED"
    return EventDecision(status, key, tuple(sorted(set(reasons))))


__all__ = ["EventDecision", "SCHEMA", "accept_event", "event_key"]
