"""First-party C/C++ native build and sanitizer adapter planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-native-adapter/v1"


@dataclass(frozen=True)
class NativeAdapterPlan:
    status: str
    build_system: str | None
    commands: tuple[tuple[str, ...], ...]
    languages: tuple[str, ...]
    sanitizers: tuple[str, ...]
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "build_system": self.build_system, "commands": [list(x) for x in self.commands], "languages": list(self.languages), "sanitizers": list(self.sanitizers), "reason_codes": list(self.reason_codes)}


def plan_native_adapter(files: list[str], *, sanitizers: tuple[str, ...] = ("address", "undefined")) -> NativeAdapterPlan:
    if "CMakeLists.txt" in files:
        build, commands = "cmake", (("cmake", "-S", ".", "-B", "build"), ("cmake", "--build", "build"), ("ctest", "--test-dir", "build"))
    elif "Makefile" in files:
        build, commands = "make", (("make", "test"), ("make", "check"))
    else:
        return NativeAdapterPlan("BLOCKED", None, (), (), (), ("NATIVE_BUILD_SYSTEM_NOT_DETECTED",))
    languages = set()
    if any(path.endswith(".c") for path in files):
        languages.add("c")
    if any(path.endswith((".cc", ".cpp", ".cxx", ".hpp")) for path in files):
        languages.add("cpp")
    return NativeAdapterPlan("PLANNED", build, commands, tuple(sorted(languages)), tuple(sorted(sanitizers)))


def normalize_native_report(report: Mapping[str, Any]) -> dict[str, Any]:
    status = str(report.get("status", "BLOCKED")).upper()
    return {"schema": SCHEMA, "status": status if status in {"PASS", "FAIL", "BLOCKED"} else "BLOCKED", "sanitizer": report.get("sanitizer"), "diagnostics": list(report.get("diagnostics", ())), "evidence_refs": list(report.get("evidence_refs", ())) }


class NativeQualityAdapter:
    def plan(self, request: Mapping[str, Any]) -> NativeAdapterPlan:
        return plan_native_adapter(list(request.get("files", ())), sanitizers=tuple(request.get("sanitizers", ("address", "undefined"))))


__all__ = ["NativeAdapterPlan", "NativeQualityAdapter", "SCHEMA", "normalize_native_report", "plan_native_adapter"]
