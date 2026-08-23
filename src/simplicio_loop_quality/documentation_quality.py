"""Documentation completeness and executable-example checks."""

from __future__ import annotations

from typing import Any, Mapping

SCHEMA = "simplicio.quality-documentation/v1"
REQUIRED_SECTIONS = ("overview", "quickstart", "api", "examples", "troubleshooting")


def plan_documentation(documents: Mapping[str, Any]) -> dict[str, Any]:
    missing = sorted(name for name in REQUIRED_SECTIONS if not documents.get(name))
    return {
        "schema": SCHEMA,
        "status": "PLANNED" if not missing else "BLOCKED",
        "required_sections": REQUIRED_SECTIONS,
        "missing_sections": missing,
        "reason_codes": ["DOCUMENTATION_INCOMPLETE"] if missing else [],
    }


def normalize_documentation(findings: list[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = [
        {
            "kind": str(item.get("kind", "unknown")),
            "location": str(item.get("location", "")),
            "detail": str(item.get("detail", "")),
        }
        for item in findings
    ]
    reasons = [
        "DOCUMENTATION_FINDING"
        for item in normalized
        if item["kind"] in {"broken_link", "invalid_command", "missing_api_reference"}
    ]
    return {
        "schema": SCHEMA,
        "status": "PASS" if not reasons else "FAIL",
        "findings": normalized,
        "reason_codes": sorted(set(reasons)),
    }


__all__ = ["REQUIRED_SECTIONS", "SCHEMA", "normalize_documentation", "plan_documentation"]
