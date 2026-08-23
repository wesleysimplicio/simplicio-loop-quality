"""First-party Java/Kotlin build and test adapter planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-jvm-adapter/v1"


@dataclass(frozen=True)
class JVMAdapterPlan:
    status: str
    build_system: str | None
    commands: tuple[tuple[str, ...], ...]
    languages: tuple[str, ...]
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "status": self.status,
            "build_system": self.build_system,
            "commands": [list(x) for x in self.commands],
            "languages": list(self.languages),
            "reason_codes": list(self.reason_codes),
        }


def plan_jvm_adapter(files: list[str]) -> JVMAdapterPlan:
    if "pom.xml" in files:
        build, commands = "maven", (("mvn", "test"), ("mvn", "verify"), ("mvn", "package"))
    elif "build.gradle" in files or "build.gradle.kts" in files:
        build, commands = "gradle", (("gradle", "test"), ("gradle", "check"), ("gradle", "build"))
    else:
        return JVMAdapterPlan("BLOCKED", None, (), (), ("JVM_BUILD_SYSTEM_NOT_DETECTED",))
    languages = set()
    if any(path.endswith(".java") for path in files):
        languages.add("java")
    if any(path.endswith(".kt") for path in files):
        languages.add("kotlin")
    return JVMAdapterPlan("PLANNED", build, commands, tuple(sorted(languages)))


def normalize_jvm_report(report: Mapping[str, Any]) -> dict[str, Any]:
    status = str(report.get("status", "BLOCKED")).upper()
    return {
        "schema": SCHEMA,
        "status": status if status in {"PASS", "FAIL", "BLOCKED"} else "BLOCKED",
        "format": str(report.get("format", "junit")),
        "findings": list(report.get("findings", ())),
        "evidence_refs": list(report.get("evidence_refs", ())),
    }


class JVMQualityAdapter:
    def plan(self, request: Mapping[str, Any]) -> JVMAdapterPlan:
        return plan_jvm_adapter(list(request.get("files", ())))


__all__ = [
    "JVMAdapterPlan",
    "JVMQualityAdapter",
    "SCHEMA",
    "normalize_jvm_report",
    "plan_jvm_adapter",
]
