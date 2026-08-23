"""Golden defect/clean-control matrix planning."""

from __future__ import annotations

from typing import Any, Mapping

SCHEMA = "simplicio.quality-golden-defects/v1"


def build_golden_matrix(profiles: list[str]) -> dict[str, Any]:
    profiles = sorted(set(str(x) for x in profiles))
    cases = tuple((profile, "seeded-defect") for profile in profiles) + tuple((profile, "clean-control") for profile in profiles)
    return {"schema": SCHEMA, "status": "PLANNED" if profiles else "BLOCKED", "profiles": tuple(profiles), "cases": cases, "reason_codes": [] if profiles else ["PROFILES_EMPTY"]}


def evaluate_golden_results(results: list[Mapping[str, Any]]) -> dict[str, Any]:
    failures = [item for item in results if str(item.get("status", "BLOCKED")).upper() != "PASS"]
    clean_false_gaps = [item for item in results if item.get("case_type") == "clean-control" and item.get("findings")]
    status = "PASS" if results and not failures and not clean_false_gaps else "FAIL" if results else "BLOCKED"
    return {"schema": SCHEMA, "status": status, "failures": failures, "clean_control_false_gaps": clean_false_gaps}


__all__ = ["SCHEMA", "build_golden_matrix", "evaluate_golden_results"]
