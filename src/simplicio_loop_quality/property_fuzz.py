"""Reproducible property/fuzz planning and failure minimization records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-property-fuzz/v1"


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class FuzzPlan:
    status: str
    engine: str | None
    seed: int | None
    cases: int
    plan_id: str
    reason_codes: tuple[str, ...] = ()


def plan_fuzz(project: Mapping[str, Any]) -> FuzzPlan:
    engine = next(
        (
            str(x)
            for x in project.get("engines", ())
            if str(x) in {"hypothesis", "proptest", "fast-check", "go-fuzz"}
        ),
        None,
    )
    seed = project.get("seed")
    cases = int(project.get("cases", 0)) if isinstance(project.get("cases", 0), int) else 0
    reasons = []
    if not engine:
        reasons.append("FUZZ_ENGINE_UNAVAILABLE")
    if not isinstance(seed, int) or isinstance(seed, bool):
        reasons.append("FUZZ_SEED_MISSING")
    if cases <= 0:
        reasons.append("FUZZ_CASE_COUNT_INVALID")
    payload = {"engine": engine, "seed": seed, "cases": cases}
    return FuzzPlan(
        "PLANNED" if not reasons else "BLOCKED",
        engine,
        seed if isinstance(seed, int) and not isinstance(seed, bool) else None,
        cases,
        _hash(payload),
        tuple(reasons),
    )


def normalize_fuzz_failure(
    result: Mapping[str, Any], *, expected_plan_id: str
) -> dict[str, Any]:
    reasons = []
    if result.get("plan_id") != expected_plan_id:
        reasons.append("PLAN_STALE")
    if result.get("status") == "FAIL" and not result.get("minimal_input"):
        reasons.append("MINIMAL_COUNTEREXAMPLE_MISSING")
    status = str(result.get("status", "BLOCKED")).upper()
    if reasons:
        status = "BLOCKED"
    return {
        "schema": SCHEMA,
        "status": status,
        "minimal_input": result.get("minimal_input"),
        "seed": result.get("seed"),
        "reason_codes": reasons,
    }


__all__ = ["FuzzPlan", "SCHEMA", "normalize_fuzz_failure", "plan_fuzz"]
