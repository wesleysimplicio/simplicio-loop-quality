"""First-party Go module adapter planning and JSON-event normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-go-adapter/v1"


@dataclass(frozen=True)
class GoAdapterPlan:
    status: str
    commands: tuple[tuple[str, ...], ...]
    workspace: bool
    cgo: bool
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "commands": [list(item) for item in self.commands], "workspace": self.workspace, "cgo": self.cgo, "reason_codes": list(self.reason_codes)}


def plan_go_adapter(files: list[str], *, cgo: bool = False) -> GoAdapterPlan:
    if "go.mod" not in files and "go.work" not in files:
        return GoAdapterPlan("BLOCKED", (), False, cgo, ("GO_MODULE_NOT_DETECTED",))
    workspace = "go.work" in files
    commands = (("go", "test", "-json", "./..."), ("go", "test", "-race", "./..."), ("go", "test", "-coverprofile=coverage.out", "./..."), ("go", "vet", "./..."))
    return GoAdapterPlan("PLANNED", commands, workspace, cgo)


def normalize_go_events(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    findings = []
    statuses = []
    for event in events:
        action = str(event.get("Action", event.get("action", ""))).lower()
        if action in {"fail", "panic"}:
            findings.append({"package": event.get("Package"), "test": event.get("Test"), "action": action, "output": event.get("Output", "")})
        if action in {"pass", "fail"}:
            statuses.append(action)
    status = "PASS" if statuses and not findings and all(item == "pass" for item in statuses) else ("FAIL" if findings else "BLOCKED")
    return {"schema": SCHEMA, "status": status, "events": len(events), "findings": findings}


class GoQualityAdapter:
    def plan(self, request: Mapping[str, Any]) -> GoAdapterPlan:
        return plan_go_adapter(list(request.get("files", ())), cgo=bool(request.get("cgo", False)))


__all__ = ["GoAdapterPlan", "GoQualityAdapter", "SCHEMA", "normalize_go_events", "plan_go_adapter"]
