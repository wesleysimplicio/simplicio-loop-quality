"""Mutation-test planning and strength-threshold evaluation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-mutation/v1"


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class MutationPlan:
    status: str
    engine: str | None
    scope: tuple[str, ...]
    timeout_ms: int
    reason_codes: tuple[str, ...]
    request_id: str


@dataclass(frozen=True)
class MutationReport:
    status: str
    killed: int
    survived: int
    timed_out: int
    equivalent: int
    score: float | None
    reason_codes: tuple[str, ...]
    report_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, **self.__dict__}


def discover_mutation_engine(project: Mapping[str, Any]) -> str | None:
    tools = project.get("tools", {}) if isinstance(project.get("tools", {}), Mapping) else {}
    for name in ("mutmut", "cosmic-ray", "cargo-mutants"):
        if tools.get(name) is True or name in project.get("dependencies", ()):
            return name
    return None


def plan_mutation(
    project: Mapping[str, Any], *, changed_scope: tuple[str, ...], timeout_ms: int = 120_000
) -> MutationPlan:
    engine = discover_mutation_engine(project)
    reasons = () if engine else ("MUTATION_ENGINE_UNAVAILABLE",)
    payload = {"engine": engine, "scope": sorted(changed_scope), "timeout_ms": timeout_ms}
    return MutationPlan(
        "PLANNED" if engine else "BLOCKED",
        engine,
        tuple(sorted(changed_scope)),
        timeout_ms,
        reasons,
        _hash(payload),
    )


def evaluate_mutations(raw: Mapping[str, Any], *, minimum_score: float) -> MutationReport:
    values: dict[str, int] = {}
    reasons: set[str] = set()
    for name in ("killed", "survived", "timed_out", "equivalent"):
        try:
            values[name] = int(raw.get(name, 0))
        except (TypeError, ValueError):
            reasons.add("MUTATION_COUNT_INVALID")
            values[name] = 0
    if any(value < 0 for value in values.values()):
        reasons.add("MUTATION_COUNT_INVALID")
    denominator = values["killed"] + values["survived"] + values["timed_out"]
    score = (100.0 * values["killed"] / denominator) if denominator else None
    if score is None:
        reasons.add("MUTATION_RESULTS_EMPTY")
    elif score < minimum_score:
        reasons.add("MUTATION_SCORE_BELOW_THRESHOLD")
    if values["timed_out"]:
        reasons.add("MUTATION_TIMEOUTS_PRESENT")
    status = (
        "PASS" if score is not None and not reasons else ("BLOCKED" if score is None else "FAIL")
    )
    payload = {
        **values,
        "score": score,
        "minimum_score": minimum_score,
        "reasons": sorted(reasons),
    }
    return MutationReport(
        status,
        values["killed"],
        values["survived"],
        values["timed_out"],
        values["equivalent"],
        score,
        tuple(sorted(reasons)),
        _hash(payload),
    )


class MutationTestAgent:
    def plan(self, request: Mapping[str, Any]) -> MutationPlan:
        return plan_mutation(
            request,
            changed_scope=tuple(request.get("changed_scope", ())),
            timeout_ms=int(request.get("timeout_ms", 120_000)),
        )


__all__ = [
    "MutationPlan",
    "MutationReport",
    "MutationTestAgent",
    "SCHEMA",
    "discover_mutation_engine",
    "evaluate_mutations",
    "plan_mutation",
]
