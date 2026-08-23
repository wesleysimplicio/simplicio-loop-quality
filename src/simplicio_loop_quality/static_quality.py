"""Planning and normalization for static-code-quality execution lanes.

The agent emits Hub-ready work and normalizes returned findings.  It does not
run arbitrary repository commands in-process, and an absent analyzer is a
blocked lane rather than a false pass.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-static/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Analyzer:
    name: str
    command: tuple[str, ...]
    version_pin: str
    language: str


@dataclass(frozen=True)
class StaticQualityPlan:
    status: str
    analyzers: tuple[Analyzer, ...]
    source_sha: str
    policy_hash: str
    request_id: str
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "status": self.status,
            "analyzers": [{"name": a.name, "command": list(a.command), "version_pin": a.version_pin, "language": a.language} for a in self.analyzers],
            "source_sha": self.source_sha,
            "policy_hash": self.policy_hash,
            "request_id": self.request_id,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class StaticFinding:
    tool: str
    rule: str
    path: str
    line: int
    severity: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _files(project: Mapping[str, Any]) -> list[str]:
    values = project.get("files", project.get("changed_files", ()))
    return sorted(str(item) for item in values if isinstance(item, str))


def discover_analyzers(project: Mapping[str, Any]) -> tuple[Analyzer, ...]:
    files = _files(project)
    tools = project.get("tools", {}) if isinstance(project.get("tools", {}), Mapping) else {}
    result: list[Analyzer] = []
    if any(item.endswith(".py") for item in files):
        if tools.get("ruff", True) is not False:
            result.append(Analyzer("ruff", ("ruff", "check", "."), str(tools.get("ruff_version", "pinned")), "python"))
        if tools.get("mypy", False) is not False and ("pyproject.toml" in files or tools.get("mypy") is True):
            result.append(Analyzer("mypy", ("mypy", "."), str(tools.get("mypy_version", "pinned")), "python"))
    if any(item.endswith(('.js', '.jsx', '.ts', '.tsx')) for item in files):
        if tools.get("eslint", True) is not False:
            result.append(Analyzer("eslint", ("eslint", "."), str(tools.get("eslint_version", "pinned")), "javascript"))
        if tools.get("tsc", False) is True:
            result.append(Analyzer("tsc", ("tsc", "--noEmit"), str(tools.get("tsc_version", "pinned")), "typescript"))
    if any(item.endswith(".rs") for item in files):
        result.append(Analyzer("cargo-clippy", ("cargo", "clippy", "--all-targets"), str(tools.get("cargo_version", "pinned")), "rust"))
    if any(item.endswith(".go") for item in files):
        result.append(Analyzer("go-vet", ("go", "vet", "./..."), str(tools.get("go_version", "pinned")), "go"))
    return tuple(sorted(result, key=lambda item: item.name))


def plan_static_quality(project: Mapping[str, Any], *, source_sha: str, policy_hash: str) -> StaticQualityPlan:
    analyzers = discover_analyzers(project)
    payload = {"source_sha": source_sha, "policy_hash": policy_hash, "analyzers": [a.__dict__ for a in analyzers]}
    return StaticQualityPlan(
        "PLANNED" if analyzers else "BLOCKED",
        analyzers,
        source_sha,
        policy_hash,
        _hash(payload),
        () if analyzers else ("STATIC_TOOLS_UNAVAILABLE",),
    )


def normalize_findings(raw: Mapping[str, Any] | list[Mapping[str, Any]], *, source_sha: str, policy_hash: str) -> dict[str, Any]:
    """Normalize SARIF-like or flat findings while preserving tool failure."""

    if isinstance(raw, Mapping) and raw.get("status") in {"BLOCKED", "FAILED"}:
        return {"schema": SCHEMA, "status": str(raw["status"]), "reason_codes": list(raw.get("reason_codes", ())), "findings": [], "source_sha": source_sha, "policy_hash": policy_hash}
    records = raw.get("findings", ()) if isinstance(raw, Mapping) else raw
    findings: list[StaticFinding] = []
    for item in records or ():
        location = item.get("location", {}) if isinstance(item, Mapping) else {}
        physical = location.get("physicalLocation", {}) if isinstance(location, Mapping) else {}
        artifact = physical.get("artifactLocation", {}) if isinstance(physical, Mapping) else {}
        region = physical.get("region", {}) if isinstance(physical, Mapping) else {}
        findings.append(StaticFinding(
            str(item.get("tool", item.get("ruleId", "unknown-tool"))), str(item.get("rule", item.get("ruleId", "unknown-rule"))),
            str(item.get("path", artifact.get("uri", "unknown"))), int(item.get("line", region.get("startLine", 0)) or 0),
            str(item.get("severity", item.get("level", "warning"))), str(item.get("message", item.get("text", ""))),
        ))
    return {"schema": SCHEMA, "status": "PASS" if not findings else "FAIL", "findings": [f.to_dict() for f in sorted(findings, key=lambda x: (x.path, x.line, x.rule, x.message))], "source_sha": source_sha, "policy_hash": policy_hash}


class StaticCodeQualityAgent:
    """Hub-facing planner; execution is delegated to the configured adapter."""

    def plan(self, request: Mapping[str, Any]) -> StaticQualityPlan:
        return plan_static_quality(request, source_sha=str(request.get("source_sha", "")), policy_hash=str(request.get("policy_hash", "")))


__all__ = ["Analyzer", "SCHEMA", "StaticCodeQualityAgent", "StaticFinding", "StaticQualityPlan", "discover_analyzers", "normalize_findings", "plan_static_quality"]
