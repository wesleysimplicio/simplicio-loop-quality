"""First-party .NET solution adapter planning and TRX-like normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-dotnet-adapter/v1"


@dataclass(frozen=True)
class DotnetAdapterPlan:
    status: str
    commands: tuple[tuple[str, ...], ...]
    projects: tuple[str, ...]
    target_frameworks: tuple[str, ...]
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "commands": [list(item) for item in self.commands], "projects": list(self.projects), "target_frameworks": list(self.target_frameworks), "reason_codes": list(self.reason_codes)}


def plan_dotnet_adapter(files: list[str], *, target_frameworks: tuple[str, ...] = ()) -> DotnetAdapterPlan:
    projects = tuple(sorted(path for path in files if path.endswith((".csproj", ".fsproj", ".sln"))))
    if not projects:
        return DotnetAdapterPlan("BLOCKED", (), (), target_frameworks, ("DOTNET_PROJECT_NOT_DETECTED",))
    commands = (("dotnet", "test", "--logger", "trx"), ("dotnet", "build", "--no-restore"), ("dotnet", "pack", "--no-restore"))
    return DotnetAdapterPlan("PLANNED", commands, projects, tuple(sorted(target_frameworks)))


def normalize_dotnet_report(report: Mapping[str, Any]) -> dict[str, Any]:
    status = str(report.get("status", "BLOCKED")).upper()
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        status = "BLOCKED"
    return {"schema": SCHEMA, "status": status, "format": str(report.get("format", "trx")), "version": str(report.get("version", "unknown")), "tests": list(report.get("tests", ())), "diagnostics": list(report.get("diagnostics", ())), "evidence_refs": list(report.get("evidence_refs", ())), "reason_codes": list(report.get("reason_codes", ())) }


class DotnetQualityAdapter:
    def plan(self, request: Mapping[str, Any]) -> DotnetAdapterPlan:
        return plan_dotnet_adapter(list(request.get("files", ())), target_frameworks=tuple(request.get("target_frameworks", ())))


__all__ = ["DotnetAdapterPlan", "DotnetQualityAdapter", "SCHEMA", "normalize_dotnet_report", "plan_dotnet_adapter"]
