"""Fail-closed integration-matrix planning and result evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations
from typing import Any

SCHEMA = "simplicio.quality-ecosystem-matrix/v1"
CORE = ("loop", "quality")
OPTIONAL = ("agent", "dev-cli", "mapper", "runtime")


def build_integration_matrix(
    *, optional_components: tuple[str, ...] = OPTIONAL
) -> dict[str, Any]:
    components = tuple(sorted(set(optional_components)))
    cases = []
    for size in range(len(components) + 1):
        for extra in combinations(components, size):
            cases.append("+".join(CORE + extra))
    return {
        "schema": SCHEMA,
        "status": "PLANNED",
        "components": CORE + components,
        "cases": tuple(cases),
        "reason_codes": [],
    }


def evaluate_matrix_results(
    results: list[Mapping[str, Any]],
    *,
    expected_cases: tuple[str, ...],
    source_sha: str,
    policy_hash: str,
) -> dict[str, Any]:
    by_case: dict[str, Mapping[str, Any]] = {}
    reasons: list[str] = []
    for result in results:
        case = str(result.get("case", ""))
        if case in by_case:
            reasons.append("DUPLICATE_CASE")
        by_case[case] = result
        if str(result.get("source_sha", "")) != source_sha:
            reasons.append("SOURCE_BINDING_MISMATCH")
        if str(result.get("policy_hash", "")) != policy_hash:
            reasons.append("POLICY_BINDING_MISMATCH")
        if not result.get("evidence_refs"):
            reasons.append("EVIDENCE_MISSING")
        if str(result.get("status", "")).upper() != "PASS":
            reasons.append("CASE_NOT_PASS")
    missing = sorted(set(expected_cases) - set(by_case))
    unexpected = sorted(set(by_case) - set(expected_cases))
    if missing:
        reasons.append("MATRIX_CASE_MISSING")
    if unexpected:
        reasons.append("MATRIX_CASE_UNEXPECTED")
    status = "PASS" if not reasons else "BLOCKED" if "EVIDENCE_MISSING" in reasons else "FAIL"
    return {
        "schema": SCHEMA,
        "status": status,
        "expected_cases": list(expected_cases),
        "missing_cases": missing,
        "unexpected_cases": unexpected,
        "reason_codes": sorted(set(reasons)),
    }


__all__ = [
    "CORE",
    "OPTIONAL",
    "SCHEMA",
    "build_integration_matrix",
    "evaluate_matrix_results",
]
