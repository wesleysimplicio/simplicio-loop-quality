"""Fail-closed release-candidate evidence validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SCHEMA = "simplicio.quality-release-candidate/v1"
REQUIRED_CHECKS = (
    "golden_suite",
    "clean_install",
    "canary",
    "upgrade",
    "rollback",
    "tamper_detection",
)


def evaluate_release_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if not str(candidate.get("version", "")).strip():
        reasons.append("VERSION_MISSING")
    if not str(candidate.get("source_sha", "")).strip():
        reasons.append("SOURCE_SHA_MISSING")
    artifacts = candidate.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        reasons.append("ARTIFACTS_MISSING")
    else:
        for artifact in artifacts:
            if not artifact.get("name") or not artifact.get("sha256"):
                reasons.append("ARTIFACT_DIGEST_MISSING")
            if not artifact.get("size"):
                reasons.append("ARTIFACT_SIZE_MISSING")
    for field in ("sbom", "provenance", "signature"):
        if not candidate.get(field):
            reasons.append(f"{field.upper()}_MISSING")
    checks = candidate.get("checks")
    if not isinstance(checks, Mapping):
        reasons.append("CHECKS_MISSING")
        checks = {}
    for name in REQUIRED_CHECKS:
        value = checks.get(name)
        if value is None:
            reasons.append(f"{name.upper()}_UNAVAILABLE")
        elif value is not True:
            reasons.append(f"{name.upper()}_FAILED")
    if reasons:
        unavailable = any(
            reason.endswith("_MISSING") or reason.endswith("_UNAVAILABLE")
            for reason in reasons
        )
        status = "BLOCKED" if unavailable else "FAIL"
    else:
        status = "PASS"
    return {
        "schema": SCHEMA,
        "status": status,
        "version": str(candidate.get("version", "")),
        "source_sha": str(candidate.get("source_sha", "")),
        "reason_codes": sorted(set(reasons)),
    }


__all__ = ["REQUIRED_CHECKS", "SCHEMA", "evaluate_release_candidate"]
