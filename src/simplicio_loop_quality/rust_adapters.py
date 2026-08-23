"""First-party Rust workspace adapter planning and output normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-rust-adapter/v1"


@dataclass(frozen=True)
class RustAdapterPlan:
    status: str
    commands: tuple[tuple[str, ...], ...]
    workspace: bool
    features: tuple[str, ...]
    target: str | None
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "commands": [list(item) for item in self.commands], "workspace": self.workspace, "features": list(self.features), "target": self.target, "reason_codes": list(self.reason_codes)}


def plan_rust_adapter(files: list[str], *, features: tuple[str, ...] = (), target: str | None = None) -> RustAdapterPlan:
    if "Cargo.toml" not in files:
        return RustAdapterPlan("BLOCKED", (), False, (), target, ("RUST_PROJECT_NOT_DETECTED",))
    workspace = "Cargo.lock" in files or any(path.count("/") > 1 and path.endswith("Cargo.toml") for path in files)
    commands = [("cargo", "test"), ("cargo", "clippy", "--all-targets"), ("cargo", "fmt", "--", "--check"), ("cargo", "audit")]
    if target:
        commands = [tuple(item) + ("--target", target) for item in commands if item[1] != "fmt"] + [commands[2]]
    detected = set(features)
    if workspace:
        detected.add("workspace")
    if any(path.endswith(".rs") and "/bin/" in path for path in files):
        detected.add("binary")
    return RustAdapterPlan("PLANNED", tuple(commands), workspace, tuple(sorted(detected)), target)


def normalize_rust_report(report: Mapping[str, Any]) -> dict[str, Any]:
    status = str(report.get("status", "BLOCKED")).upper()
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        status = "BLOCKED"
    return {"schema": SCHEMA, "status": status, "tool": str(report.get("tool", "cargo")), "version": str(report.get("version", "unknown")), "diagnostics": list(report.get("diagnostics", ())), "evidence_refs": list(report.get("evidence_refs", ())), "reason_codes": list(report.get("reason_codes", ())) }


class RustQualityAdapter:
    def plan(self, request: Mapping[str, Any]) -> RustAdapterPlan:
        return plan_rust_adapter(list(request.get("files", ())), features=tuple(request.get("features", ())), target=request.get("target"))


__all__ = ["RustAdapterPlan", "RustQualityAdapter", "SCHEMA", "normalize_rust_report", "plan_rust_adapter"]
