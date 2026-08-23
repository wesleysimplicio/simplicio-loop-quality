"""First-party Ruby Bundler/RSpec/Minitest adapter planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-ruby-adapter/v1"


@dataclass(frozen=True)
class RubyAdapterPlan:
    status: str
    commands: tuple[tuple[str, ...], ...]
    framework: str | None
    engine: str | None
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "status": self.status,
            "commands": [list(x) for x in self.commands],
            "framework": self.framework,
            "engine": self.engine,
            "reason_codes": list(self.reason_codes),
        }


def plan_ruby_adapter(
    files: list[str], *, framework: str = "rspec", engine: str | None = None
) -> RubyAdapterPlan:
    if "Gemfile" not in files:
        return RubyAdapterPlan("BLOCKED", (), None, engine, ("RUBY_PROJECT_NOT_DETECTED",))
    if "Gemfile.lock" not in files:
        return RubyAdapterPlan("BLOCKED", (), framework, engine, ("BUNDLER_LOCK_MISSING",))
    if framework not in {"rspec", "minitest"}:
        return RubyAdapterPlan("BLOCKED", (), None, engine, ("RUBY_TEST_FRAMEWORK_UNSUPPORTED",))
    runner = "bundle exec rspec" if framework == "rspec" else "bundle exec ruby -Itest"
    commands = (
        ("bundle", "check"),
        tuple(runner.split()),
        ("bundle", "exec", "rubocop"),
        ("bundle", "exec", "simplecov"),
    )
    return RubyAdapterPlan("PLANNED", commands, framework, engine or "ruby")


def normalize_ruby_report(report: Mapping[str, Any]) -> dict[str, Any]:
    status = str(report.get("status", "BLOCKED")).upper()
    return {
        "schema": SCHEMA,
        "status": status if status in {"PASS", "FAIL", "BLOCKED"} else "BLOCKED",
        "format": str(report.get("format", "junit")),
        "findings": list(report.get("findings", ())),
        "evidence_refs": list(report.get("evidence_refs", ())),
    }


class RubyQualityAdapter:
    def plan(self, request: Mapping[str, Any]) -> RubyAdapterPlan:
        return plan_ruby_adapter(
            list(request.get("files", ())),
            framework=str(request.get("framework", "rspec")),
            engine=request.get("engine"),
        )


__all__ = [
    "RubyAdapterPlan",
    "RubyQualityAdapter",
    "SCHEMA",
    "normalize_ruby_report",
    "plan_ruby_adapter",
]
