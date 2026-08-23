"""Accessibility lane planning and violation normalization."""

from __future__ import annotations

from typing import Any, Mapping

SCHEMA = "simplicio.quality-accessibility/v1"


def plan_accessibility(
    routes: list[str], *, standards: tuple[str, ...] = ("WCAG2.2-AA",)
) -> dict[str, Any]:
    reasons = [] if routes else ["ACCESSIBILITY_ROUTES_MISSING"]
    checks = ("keyboard", "name_role_value", "contrast", "focus", "screen_reader")
    return {
        "schema": SCHEMA,
        "status": "PLANNED" if routes else "BLOCKED",
        "routes": tuple(sorted(routes)),
        "standards": standards,
        "checks": checks,
        "reason_codes": reasons,
    }


def normalize_accessibility(findings: list[Mapping[str, Any]]) -> dict[str, Any]:
    values = [
        {
            "rule": str(item.get("rule", "unknown")),
            "path": str(item.get("path", "")),
            "impact": str(item.get("impact", "serious")),
            "detail": str(item.get("detail", "")),
        }
        for item in findings
    ]
    return {"schema": SCHEMA, "status": "PASS" if not values else "FAIL", "findings": values}


__all__ = ["SCHEMA", "normalize_accessibility", "plan_accessibility"]
