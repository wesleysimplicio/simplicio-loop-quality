"""First-party PHP Composer and PHPUnit adapter planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-php-adapter/v1"


@dataclass(frozen=True)
class PHPAdapterPlan:
    status: str
    commands: tuple[tuple[str, ...], ...]
    framework: str | None
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "commands": [list(x) for x in self.commands], "framework": self.framework, "reason_codes": list(self.reason_codes)}


def plan_php_adapter(files: list[str], *, framework: str = "phpunit") -> PHPAdapterPlan:
    if "composer.json" not in files:
        return PHPAdapterPlan("BLOCKED", (), None, ("PHP_PROJECT_NOT_DETECTED",))
    if framework not in {"phpunit", "pest"}:
        return PHPAdapterPlan("BLOCKED", (), None, ("PHP_TEST_FRAMEWORK_UNSUPPORTED",))
    runner = "vendor/bin/phpunit" if framework == "phpunit" else "vendor/bin/pest"
    return PHPAdapterPlan("PLANNED", (("composer", "validate"), (runner,), ("vendor/bin/phpstan",)), framework)


def normalize_php_report(report: Mapping[str, Any]) -> dict[str, Any]:
    status = str(report.get("status", "BLOCKED")).upper()
    return {"schema": SCHEMA, "status": status if status in {"PASS", "FAIL", "BLOCKED"} else "BLOCKED", "format": str(report.get("format", "junit")), "failures": list(report.get("failures", ())), "evidence_refs": list(report.get("evidence_refs", ())) }


class PHPQualityAdapter:
    def plan(self, request: Mapping[str, Any]) -> PHPAdapterPlan:
        return plan_php_adapter(list(request.get("files", ())), framework=str(request.get("framework", "phpunit")))


__all__ = ["PHPAdapterPlan", "PHPQualityAdapter", "SCHEMA", "normalize_php_report", "plan_php_adapter"]
