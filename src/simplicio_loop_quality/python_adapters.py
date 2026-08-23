"""First-party Python toolchain adapter plans and report normalizers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-python-adapter/v1"


@dataclass(frozen=True)
class PythonAdapterPlan:
    status: str
    commands: tuple[tuple[str, ...], ...]
    features: tuple[str, ...]
    version_pins: Mapping[str, str]
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "status": self.status,
            "commands": [list(item) for item in self.commands],
            "features": list(self.features),
            "version_pins": dict(self.version_pins),
            "reason_codes": list(self.reason_codes),
        }


def plan_python_adapter(
    files: list[str], *, tools: Mapping[str, str] | None = None
) -> PythonAdapterPlan:
    tools = tools or {}
    pyproject = "pyproject.toml" in files
    python_files = [path for path in files if path.endswith(".py")]
    if not python_files:
        return PythonAdapterPlan("BLOCKED", (), (), {}, ("PYTHON_PROJECT_NOT_DETECTED",))
    commands: list[tuple[str, ...]] = [
        ("pytest", "-q"),
        ("coverage", "run", "-m", "pytest"),
        ("ruff", "check", "."),
    ]
    if pyproject:
        commands.append(("python", "-m", "build", "--wheel", "--sdist"))
    features = {"pytest", "coverage", "lint", "packaging" if pyproject else ""}
    features.discard("")
    if any("async" in path for path in files):
        features.add("async")
    if any(path.count("/") > 2 for path in python_files):
        features.add("monorepo_or_namespace")
    return PythonAdapterPlan(
        "PLANNED", tuple(commands), tuple(sorted(features)), dict(sorted(tools.items()))
    )


def normalize_python_report(report: Mapping[str, Any]) -> dict[str, Any]:
    status = str(report.get("status", "BLOCKED")).upper()
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        status = "BLOCKED"
    return {
        "schema": SCHEMA,
        "status": status,
        "tool": str(report.get("tool", "unknown")),
        "version": str(report.get("version", "unknown")),
        "findings": list(report.get("findings", ())),
        "evidence_refs": list(report.get("evidence_refs", ())),
        "reason_codes": list(report.get("reason_codes", ())),
    }


class PythonQualityAdapter:
    def plan(self, request: Mapping[str, Any]) -> PythonAdapterPlan:
        return plan_python_adapter(list(request.get("files", ())), tools=request.get("tools"))


__all__ = [
    "PythonAdapterPlan",
    "PythonQualityAdapter",
    "SCHEMA",
    "normalize_python_report",
    "plan_python_adapter",
]
