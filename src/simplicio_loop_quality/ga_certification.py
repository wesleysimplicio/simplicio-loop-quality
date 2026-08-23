"""Expanded universal-quality GA matrix and certification gate."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SCHEMA = "simplicio.quality-ga-certification/v1"
LANES = (
    "unit",
    "integration",
    "system",
    "regression",
    "real_fixture",
    "changed_branch_coverage",
    "golden_defect",
    "clean_control",
    "install",
    "rollback",
)


def build_ga_matrix(profiles: tuple[str, ...]) -> dict[str, Any]:
    profiles = tuple(sorted(set(profiles)))
    cases = tuple((profile, lane) for profile in profiles for lane in LANES)
    return {
        "schema": SCHEMA,
        "status": "PLANNED" if profiles else "BLOCKED",
        "profiles": profiles,
        "lanes": LANES,
        "cases": cases,
        "reason_codes": [] if profiles else ["PROFILES_MISSING"],
    }


def evaluate_ga_results(
    results: list[Mapping[str, Any]],
    *,
    expected_cases: tuple[tuple[str, str], ...],
    source_sha: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    seen: set[tuple[str, str]] = set()
    for result in results:
        case = (str(result.get("profile", "")), str(result.get("lane", "")))
        if case in seen:
            reasons.append("DUPLICATE_CASE")
        seen.add(case)
        if str(result.get("source_sha", "")) != source_sha:
            reasons.append("SOURCE_BINDING_MISMATCH")
        if not result.get("evidence_refs"):
            reasons.append("EVIDENCE_MISSING")
        if str(result.get("status", "")).upper() != "PASS":
            reasons.append("LANE_NOT_PASS")
        if case[1] == "changed_branch_coverage" and float(result.get("percent", 0)) < 90:
            reasons.append("CHANGED_BRANCH_COVERAGE_BELOW_90")
    missing = sorted(set(expected_cases) - seen)
    if missing:
        reasons.append("GA_CASE_MISSING")
    status = ("BLOCKED" if "EVIDENCE_MISSING" in reasons else "FAIL") if reasons else "PASS"
    return {
        "schema": SCHEMA,
        "status": status,
        "missing_cases": missing,
        "reason_codes": sorted(set(reasons)),
    }


__all__ = ["LANES", "SCHEMA", "build_ga_matrix", "evaluate_ga_results"]
