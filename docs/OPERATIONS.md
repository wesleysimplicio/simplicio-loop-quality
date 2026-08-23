# Operations and recovery runbook

## Boundary and setup

This repository is a Loop extension. The Loop owns slots, scheduling, processes,
retries, cancellation, delivery and terminal completion. Quality only supplies
policy, agents, plans, findings, evidence and a non-terminal gate verdict.

Create an isolated environment, install the package, and run the diagnostic
commands below:

    python -m pip install .
    simplicio-loop-quality doctor
    simplicio-loop-quality agents
    simplicio-loop-quality plan --repo /path/to/project --out quality-task.md

The doctor command must prove the exact Loop/provider handshake before a task is
created. A missing capability produces BLOCKED and does not start a local
runner.

## Evidence and reports

Every PASS lane needs the run, task, attempt, agent, source SHA, policy/config
hash, tool version, command, timing, environment, seed and artifact hashes.
Use cli_reports to inspect structured output; never infer a successful run from
an exit code without the Loop outcome and Completion Oracle receipt.

## Recovery, cancellation and waivers

- Invalid or stale evidence: stop the gate, preserve the original receipt, and
  request a fresh Loop-managed run.
- Timeout or cancellation: retain CANCELLED/BLOCKED and release resources
  through the Loop; do not retry locally.
- Flaky or unavailable lane: record the reason and keep the gate blocked.
- NOT_APPLICABLE: attach an independent waiver with scope, owner, expiry and
  policy hash. A waiver never converts missing evidence into PASS.
- Product defects become structured findings for Loop recovery; this extension
  does not implement unrelated product changes.

## Adapter authoring

Read ADAPTER_AUTHORING.md before adding an adapter. Adapters are immutable data
boundaries: they do not execute commands, schedule work, submit to the Hub or
claim completion. Use Loop ProcessSpec data for command requests.

## Local validation

Run the dependency-free gate from the repository root:

    python scripts/check.py
    python scripts/check_docs.py

The full pytest, coverage, package-build and clean-install lanes require the
declared development dependencies and a network/package index. Missing
dependencies must be reported as BLOCKED, not counted as a passing lane.
