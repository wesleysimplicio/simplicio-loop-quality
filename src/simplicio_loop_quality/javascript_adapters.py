"""First-party JavaScript/TypeScript adapter discovery and normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-javascript-adapter/v1"


@dataclass(frozen=True)
class JavaScriptAdapterPlan:
    status: str
    package_manager: str | None
    module_mode: str
    commands: tuple[tuple[str, ...], ...]
    workspace: bool
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "package_manager": self.package_manager, "module_mode": self.module_mode, "commands": [list(item) for item in self.commands], "workspace": self.workspace, "reason_codes": list(self.reason_codes)}


def plan_javascript_adapter(files: list[str], package: Mapping[str, Any] | None = None) -> JavaScriptAdapterPlan:
    package = package or {}
    if "package.json" not in files:
        return JavaScriptAdapterPlan("BLOCKED", None, "unknown", (), False, ("JAVASCRIPT_PROJECT_NOT_DETECTED",))
    manager = "pnpm" if "pnpm-lock.yaml" in files else "yarn" if "yarn.lock" in files else "npm" if "package-lock.json" in files else None
    if manager is None:
        return JavaScriptAdapterPlan("BLOCKED", None, "unknown", (), False, ("PACKAGE_MANAGER_LOCK_MISSING",))
    mode = "esm" if package.get("type") == "module" else "cjs"
    commands = ((manager, "test"), (manager, "run", "lint"), (manager, "run", "coverage"))
    workspace = bool(package.get("workspaces")) or any(path.startswith("packages/") for path in files)
    return JavaScriptAdapterPlan("PLANNED", manager, mode, commands, workspace)


def normalize_javascript_report(report: Mapping[str, Any]) -> dict[str, Any]:
    status = str(report.get("status", "BLOCKED")).upper()
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        status = "BLOCKED"
    return {"schema": SCHEMA, "status": status, "runner": str(report.get("runner", "unknown")), "version": str(report.get("version", "unknown")), "findings": list(report.get("findings", ())), "evidence_refs": list(report.get("evidence_refs", ())), "reason_codes": list(report.get("reason_codes", ())) }


class JavaScriptQualityAdapter:
    def plan(self, request: Mapping[str, Any]) -> JavaScriptAdapterPlan:
        return plan_javascript_adapter(list(request.get("files", ())), request.get("package"))


__all__ = ["JavaScriptAdapterPlan", "JavaScriptQualityAdapter", "SCHEMA", "normalize_javascript_report", "plan_javascript_adapter"]
