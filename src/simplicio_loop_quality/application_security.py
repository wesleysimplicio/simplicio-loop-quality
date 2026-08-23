"""Application-security scan planning and fail-closed finding normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-application-security/v1"


@dataclass(frozen=True)
class SecurityPlan:
    status: str
    tools: tuple[str, ...]
    checks: tuple[str, ...]
    reason_codes: tuple[str, ...] = ()


def plan_security(project: Mapping[str, Any]) -> SecurityPlan:
    files = [str(x) for x in project.get("files", ())]
    tools = tuple(sorted(str(x) for x in project.get("tools", ())))
    checks = {"secret_scan", "dependency_sast", "injection", "authz", "path_traversal"}
    if any(path.endswith((".py", ".js", ".ts", ".go", ".rs")) for path in files):
        checks.add("source_analysis")
    reasons = ("SECURITY_TOOL_UNAVAILABLE",) if not tools else ()
    return SecurityPlan("PLANNED" if tools else "BLOCKED", tools, tuple(sorted(checks)), reasons)


def normalize_security_findings(
    findings: list[Mapping[str, Any]], *, source_sha: str
) -> dict[str, Any]:
    normalized = [
        {
            "rule": str(item.get("rule", "unknown")),
            "severity": str(item.get("severity", "high")),
            "path": str(item.get("path", "")),
            "detail": str(item.get("detail", "")),
            "source_sha": source_sha,
        }
        for item in findings
    ]
    return {
        "schema": SCHEMA,
        "status": "PASS" if not normalized else "FAIL",
        "findings": normalized,
        "source_sha": source_sha,
    }


__all__ = ["SCHEMA", "SecurityPlan", "normalize_security_findings", "plan_security"]
