# Issue audit ledger

The repository backlog is a specification, while GitHub state and merged PRs
are execution evidence. The audit tool keeps those concerns separate: it
requires one ledger entry for every QLT issue and rejects entries without
implementation, test and evidence references.

An entry is one of IMPLEMENTED, BLOCKED, SPEC or NEEDS-IMPLEMENTATION. A
BLOCKED entry must name the blocker. The tool is intentionally offline so the
ledger can be reviewed from a commit-bound artifact instead of silently
trusting a network response.

Generate and validate the final ledger only after recording the actual issue
state, PR or commit, test command and evidence handle:

    python scripts/backlog.py check
    python scripts/audit_report.py --issues backlog/issues.json --ledger docs/issue-audit-ledger.json

The audit is complete only when the command returns PASS and the ledger is
reviewed against GitHub. Missing upstream runtime, clean-install or
multi-repository evidence remains BLOCKED with an explicit reason.

Run the focused validator tests:

    PYTHONPATH=src python -m unittest -v tests/unit/test_audit_report.py
