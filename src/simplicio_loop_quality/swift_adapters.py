"""First-party Swift Package Manager adapter planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-swift-adapter/v1"


@dataclass(frozen=True)
class SwiftAdapterPlan:
    status: str
    commands: tuple[tuple[str, ...], ...]
    platforms: tuple[str, ...]
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "commands": [list(x) for x in self.commands], "platforms": list(self.platforms), "reason_codes": list(self.reason_codes)}


def plan_swift_adapter(files: list[str], *, platforms: tuple[str, ...] = ()) -> SwiftAdapterPlan:
    if "Package.swift" not in files:
        return SwiftAdapterPlan("BLOCKED", (), platforms, ("SWIFT_PACKAGE_NOT_DETECTED",))
    commands = (("swift", "test"), ("swift", "build"), ("swift", "package", "show-dependencies"))
    return SwiftAdapterPlan("PLANNED", commands, tuple(sorted(platforms)))


def normalize_swift_report(report: Mapping[str, Any]) -> dict[str, Any]:
    status = str(report.get("status", "BLOCKED")).upper()
    return {"schema": SCHEMA, "status": status if status in {"PASS", "FAIL", "BLOCKED"} else "BLOCKED", "diagnostics": list(report.get("diagnostics", ())), "evidence_refs": list(report.get("evidence_refs", ())) }


class SwiftQualityAdapter:
    def plan(self, request: Mapping[str, Any]) -> SwiftAdapterPlan:
        return plan_swift_adapter(list(request.get("files", ())), platforms=tuple(request.get("platforms", ())))


__all__ = ["SCHEMA", "SwiftAdapterPlan", "SwiftQualityAdapter", "normalize_swift_report", "plan_swift_adapter"]
