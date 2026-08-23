"""CI-neutral exit-code and standard report projection."""

from __future__ import annotations

from typing import Any, Mapping

SCHEMA = "simplicio.quality-cli-report/v1"
EXIT_CODES = {"PASS": 0, "FAIL": 1, "BLOCKED": 2}


def project_cli_report(verdict: Mapping[str, Any], *, format_name: str = "json") -> dict[str, Any]:
    status = str(verdict.get("status", "BLOCKED")).upper()
    if status not in EXIT_CODES:
        status = "BLOCKED"
    return {"schema": SCHEMA, "format": format_name, "status": status, "exit_code": EXIT_CODES[status], "findings": list(verdict.get("findings", ())), "reason_codes": list(verdict.get("reason_codes", ())) }


def parse_cli_status(return_code: int) -> str:
    return {0: "PASS", 1: "FAIL", 2: "BLOCKED"}.get(return_code, "BLOCKED")


__all__ = ["EXIT_CODES", "SCHEMA", "parse_cli_status", "project_cli_report"]
