"""Invariant review with evidence-backed blocking findings."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-invariant-review/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class InvariantVerdict:
    status: str
    checked: tuple[str, ...]
    violated: tuple[str, ...]
    reason_codes: tuple[str, ...]
    review_id: str


def review_invariants(invariants: list[Mapping[str, Any]]) -> InvariantVerdict:
    checked, violated, reasons = set(), set(), set()
    for item in invariants:
        name = str(item.get("name", ""))
        if not name:
            reasons.add("INVARIANT_NAME_MISSING")
            continue
        checked.add(name)
        if item.get("status") != "PASS":
            violated.add(name)
            reasons.add("INVARIANT_VIOLATED")
        if not item.get("evidence_ref"):
            reasons.add("INVARIANT_EVIDENCE_MISSING")
    if not checked:
        reasons.add("INVARIANTS_EMPTY")
    status = "PASS" if checked and not reasons else ("BLOCKED" if not checked else "FAIL")
    payload = {"checked": sorted(checked), "violated": sorted(violated), "reasons": sorted(reasons)}
    return InvariantVerdict(status, tuple(sorted(checked)), tuple(sorted(violated)), tuple(sorted(reasons)), _hash(payload))


__all__ = ["InvariantVerdict", "SCHEMA", "review_invariants"]
