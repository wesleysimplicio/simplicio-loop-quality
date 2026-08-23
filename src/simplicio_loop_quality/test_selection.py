"""Independent validation that selected tests cover the impact map."""

from __future__ import annotations

from typing import Any, Mapping

SCHEMA = "simplicio.quality-test-selection/v1"


def validate_test_selection(impact: Mapping[str, Any], selected: list[Mapping[str, Any]]) -> dict[str, Any]:
    impacted = {str(x) for x in impact.get("impacted_files", ())}
    covered = {str(path) for item in selected for path in item.get("paths", ())}
    missing = sorted(impacted - covered)
    test_ids = [str(item.get("test_id")) for item in selected if item.get("test_id")]
    duplicates = sorted({test_id for test_id in test_ids if test_ids.count(test_id) > 1})
    reasons = []
    if missing:
        reasons.append("IMPACT_UNCOVERED")
    if duplicates:
        reasons.append("TEST_ID_DUPLICATE")
    if not selected:
        reasons.append("TEST_SELECTION_EMPTY")
    return {
        "schema": SCHEMA,
        "status": "PASS" if not reasons else "BLOCKED",
        "missing_paths": missing,
        "duplicate_test_ids": duplicates,
        "reason_codes": reasons,
    }


__all__ = ["SCHEMA", "validate_test_selection"]
