"""Repeatability classification and explicit quarantine decisions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

SCHEMA = "simplicio.quality-flaky-repeatability/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class RepeatabilityVerdict:
    status: str
    runs: int
    pass_count: int
    fail_count: int
    flaky: bool
    quarantine: bool
    verdict_id: str


def classify_repeatability(results: list[str], *, quarantine_threshold: float = 0.2) -> RepeatabilityVerdict:
    normalized = [str(item).upper() for item in results]
    passes, fails = normalized.count("PASS"), normalized.count("FAIL")
    runs = len(normalized)
    flaky = passes > 0 and fails > 0
    rate = min(passes, fails) / runs if runs else 1.0
    quarantine = flaky and rate >= quarantine_threshold
    status = "BLOCKED" if not runs else "FAIL" if flaky else "PASS" if fails == 0 else "FAIL"
    payload = {"results": normalized, "threshold": quarantine_threshold, "status": status}
    return RepeatabilityVerdict(status, runs, passes, fails, flaky, quarantine, _hash(payload))


__all__ = ["RepeatabilityVerdict", "SCHEMA", "classify_repeatability"]
