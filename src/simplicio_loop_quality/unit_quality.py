"""Hub-planned unit-test discovery and fail-closed result normalization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-unit/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class UnitSuite:
    framework: str
    command: tuple[str, ...]
    paths: tuple[str, ...]
    version_pin: str


@dataclass(frozen=True)
class UnitTestPlan:
    status: str
    suites: tuple[UnitSuite, ...]
    selected_units: tuple[str, ...]
    source_sha: str
    policy_hash: str
    request_id: str
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "status": self.status,
            "suites": [{"framework": s.framework, "command": list(s.command), "paths": list(s.paths), "version_pin": s.version_pin} for s in self.suites],
            "selected_units": list(self.selected_units),
            "source_sha": self.source_sha,
            "policy_hash": self.policy_hash,
            "request_id": self.request_id,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class UnitTestResult:
    test_id: str
    status: str
    duration_ms: int | float
    evidence_ref: str | None
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"test_id": self.test_id, "status": self.status, "duration_ms": self.duration_ms, "evidence_ref": self.evidence_ref, "reason_codes": list(self.reason_codes)}


def _files(project: Mapping[str, Any]) -> list[str]:
    values = project.get("files", project.get("changed_files", ()))
    return sorted(str(item) for item in values if isinstance(item, str))


def discover_unit_suites(project: Mapping[str, Any]) -> tuple[UnitSuite, ...]:
    files = _files(project)
    tools = project.get("tools", {}) if isinstance(project.get("tools", {}), Mapping) else {}
    suites: list[UnitSuite] = []
    python_tests = [path for path in files if path.startswith("tests/") and path.endswith(".py")]
    if python_tests or any(path.endswith(".py") for path in files):
        framework = "pytest" if "pytest.ini" in files or "pyproject.toml" in files or not python_tests else "unittest"
        command = ("pytest", "-q") if framework == "pytest" else ("python", "-m", "unittest")
        suites.append(UnitSuite(framework, command, tuple(python_tests or ("tests",)), str(tools.get("pytest_version", "pinned"))))
    js_tests = [path for path in files if ".test." in path or ".spec." in path]
    if js_tests:
        framework = "vitest" if tools.get("vitest") is True else "jest"
        suites.append(UnitSuite(framework, (framework, "run", "--runInBand"), tuple(js_tests), str(tools.get(f"{framework}_version", "pinned"))))
    if any(path.endswith(".rs") for path in files):
        suites.append(UnitSuite("cargo-test", ("cargo", "test", "--all-targets"), ("." ,), str(tools.get("cargo_version", "pinned"))))
    if any(path.endswith(".go") for path in files):
        suites.append(UnitSuite("go-test", ("go", "test", "./..."), (".",), str(tools.get("go_version", "pinned"))))
    return tuple(sorted(suites, key=lambda item: item.framework))


def plan_unit_tests(project: Mapping[str, Any], *, changed_files: tuple[str, ...] = (), source_sha: str, policy_hash: str) -> UnitTestPlan:
    suites = discover_unit_suites(project)
    selected = tuple(sorted(changed_files or project.get("changed_files", ()) or ()))
    payload = {"source_sha": source_sha, "policy_hash": policy_hash, "suites": [suite.__dict__ for suite in suites], "selected": selected}
    return UnitTestPlan("PLANNED" if suites else "BLOCKED", suites, selected, source_sha, policy_hash, _hash(payload), () if suites else ("UNIT_SUITE_UNAVAILABLE",))


def normalize_unit_results(results: list[Mapping[str, Any]] | None, *, source_sha: str, policy_hash: str) -> dict[str, Any]:
    """Require per-test identity, duration, and evidence; empty output blocks."""

    if not results:
        return {"schema": SCHEMA, "status": "BLOCKED", "reason_codes": ["UNIT_RESULTS_EMPTY"], "results": [], "source_sha": source_sha, "policy_hash": policy_hash}
    normalized: list[UnitTestResult] = []
    for item in results:
        test_id = str(item.get("test_id", ""))
        status = str(item.get("status", "BLOCKED")).upper()
        reasons: list[str] = []
        if not test_id:
            reasons.append("TEST_ID_MISSING")
        if status not in {"PASS", "FAIL", "BLOCKED", "TIMEOUT"}:
            status, reasons = "BLOCKED", ["STATUS_INVALID"]
        evidence = item.get("evidence_ref")
        if not evidence:
            reasons.append("EVIDENCE_MISSING")
        if reasons:
            status = "BLOCKED"
        normalized.append(UnitTestResult(test_id, status, item.get("duration_ms", 0), str(evidence) if evidence else None, tuple(sorted(set(reasons)))))
    overall = "PASS" if normalized and all(item.status == "PASS" for item in normalized) else "FAIL"
    if any(item.status == "BLOCKED" for item in normalized):
        overall = "BLOCKED"
    return {"schema": SCHEMA, "status": overall, "results": [item.to_dict() for item in sorted(normalized, key=lambda x: x.test_id)], "source_sha": source_sha, "policy_hash": policy_hash}


class UnitTestAgent:
    def plan(self, request: Mapping[str, Any]) -> UnitTestPlan:
        return plan_unit_tests(request, changed_files=tuple(request.get("changed_files", ())), source_sha=str(request.get("source_sha", "")), policy_hash=str(request.get("policy_hash", "")))


__all__ = ["SCHEMA", "UnitSuite", "UnitTestAgent", "UnitTestPlan", "UnitTestResult", "discover_unit_suites", "normalize_unit_results", "plan_unit_tests"]
