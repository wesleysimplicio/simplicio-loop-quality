"""Fast Python/Rust/off conformance matrix and invariant checks."""

from __future__ import annotations

from itertools import product
from typing import Any, Mapping

SCHEMA = "simplicio.quality-fast-conformance/v1"
ENGINES = ("off", "python", "rust")
MODES = ("full", "loop-standalone")
LANES = (
    "conformance",
    "corruption",
    "generation-drift",
    "engine-selection",
    "fallback",
    "crash-recovery",
    "benchmark-integrity",
)
SLOT_COUNTS = (1, 20, 100)


def build_conformance_matrix() -> dict[str, Any]:
    cases = tuple(
        (engine, mode, lane, slots)
        for engine, mode, lane, slots in product(ENGINES, MODES, LANES, SLOT_COUNTS)
    )
    return {
        "schema": SCHEMA,
        "status": "PLANNED",
        "engines": ENGINES,
        "modes": MODES,
        "lanes": LANES,
        "slot_counts": SLOT_COUNTS,
        "cases": cases,
    }


def evaluate_conformance(
    results: list[Mapping[str, Any]],
    *,
    expected_cases: tuple[tuple[str, str, str, int], ...],
    source_sha: str,
    policy_hash: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    seen: set[tuple[str, str, str, int]] = set()
    for result in results:
        case = (
            str(result.get("engine", "")),
            str(result.get("mode", "")),
            str(result.get("lane", "")),
            int(result.get("slots", 0)),
        )
        if case in seen:
            reasons.append("DUPLICATE_CASE")
        seen.add(case)
        if result.get("source_sha") != source_sha:
            reasons.append("SOURCE_BINDING_MISMATCH")
        if result.get("policy_hash") != policy_hash:
            reasons.append("POLICY_BINDING_MISMATCH")
        if not result.get("evidence_refs"):
            reasons.append("EVIDENCE_MISSING")
        if result.get("engine") == "rust" and result.get("python_loaded"):
            reasons.append("RUST_LOADED_PYTHON")
        if result.get("engine") == "rust" and result.get("fallback_used"):
            reasons.append("RUST_FALLBACK_USED")
        if int(result.get("shadow_duplicates", 0)) != 0:
            reasons.append("SHADOW_DUPLICATE_EFFECT")
        if not result.get("rollback_exercised"):
            reasons.append("ROLLBACK_NOT_EXERCISED")
        if str(result.get("status", "")).upper() != "PASS":
            reasons.append("CASE_NOT_PASS")
    missing = sorted(set(expected_cases) - seen)
    if missing:
        reasons.append("CONFORMANCE_CASE_MISSING")
    status = "PASS" if not reasons else "BLOCKED" if "EVIDENCE_MISSING" in reasons else "FAIL"
    return {
        "schema": SCHEMA,
        "status": status,
        "missing_cases": missing,
        "reason_codes": sorted(set(reasons)),
    }


__all__ = [
    "ENGINES",
    "LANES",
    "MODES",
    "SCHEMA",
    "SLOT_COUNTS",
    "build_conformance_matrix",
    "evaluate_conformance",
]
