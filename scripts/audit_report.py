#!/usr/bin/env python3
"""Validate a commit-bound issue-audit ledger without network access."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SCHEMA = "simplicio.quality-issue-audit/v1"
DECISIONS = {"IMPLEMENTED", "BLOCKED", "SPEC", "NEEDS-IMPLEMENTATION"}


def audit_backlog(
    backlog: Mapping[str, Any], ledger: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    reasons: list[str] = []
    issues = backlog.get("issues")
    if not isinstance(issues, list) or not issues:
        reasons.append("BACKLOG_MISSING")
        issues = []
    expected = {str(item.get("id")) for item in issues if isinstance(item, Mapping)}
    missing = sorted(expected - set(ledger))
    unexpected = sorted(set(ledger) - expected)
    if missing:
        reasons.append("LEDGER_ENTRY_MISSING")
    if unexpected:
        reasons.append("LEDGER_ENTRY_UNEXPECTED")
    for issue_id, entry in ledger.items():
        if not isinstance(entry, Mapping):
            reasons.append("LEDGER_ENTRY_INVALID")
            continue
        decision = str(entry.get("decision", ""))
        if decision not in DECISIONS:
            reasons.append("DECISION_INVALID")
        for field in ("implementation_refs", "test_refs", "evidence_refs"):
            if not isinstance(entry.get(field), list) or not entry[field]:
                reasons.append(f"{issue_id}_{field.upper()}_MISSING")
        if decision == "BLOCKED" and not entry.get("blocker"):
            reasons.append(f"{issue_id}_BLOCKER_MISSING")
    return {
        "schema": SCHEMA,
        "status": "PASS" if not reasons else "BLOCKED",
        "issue_count": len(expected),
        "missing_entries": missing,
        "unexpected_entries": unexpected,
        "reason_codes": sorted(set(reasons)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issues", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()
    backlog = json.loads(args.issues.read_text(encoding="utf-8"))
    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    report = audit_backlog(backlog, ledger)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
