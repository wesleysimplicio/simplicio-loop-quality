"""Privacy and sensitive-data quality checks."""

from __future__ import annotations

from typing import Any, Mapping

SCHEMA = "simplicio.quality-privacy/v1"


def scan_privacy(findings: list[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = []
    reasons = []
    for finding in findings:
        item = {
            "path": str(finding.get("path", "")),
            "category": str(finding.get("category", "unknown")),
            "classification": str(finding.get("classification", "")),
            "retention": str(finding.get("retention", "")),
            "consent": bool(finding.get("consent", False)),
        }
        normalized.append(item)
        if not item["classification"]:
            reasons.append("DATA_CLASSIFICATION_MISSING")
        if not item["retention"]:
            reasons.append("RETENTION_POLICY_MISSING")
        if item["category"] in {"pii", "secret", "sensitive"} and not item["consent"]:
            reasons.append("CONSENT_EVIDENCE_MISSING")
    return {
        "schema": SCHEMA,
        "status": "PASS" if not reasons else "BLOCKED",
        "findings": normalized,
        "reason_codes": sorted(set(reasons)),
    }


__all__ = ["SCHEMA", "scan_privacy"]
