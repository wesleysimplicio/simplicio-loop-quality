# simplicio-loop-quality

Agent-driven, fail-closed testing and quality assurance for any repository, executed through
`simplicio-loop`.

`simplicio-loop-quality` is a **domain extension**, not a second orchestrator. It decides what must
be tested, contributes specialized quality-agent profiles, and produces auditable evidence. The
core Loop remains the only owner of queues, scheduling, worktrees, processes, leases, retries,
resource limits, cancellation, recovery, delivery, and the terminal completion decision.

> Status: architectural bootstrap. The public extension contract and first fail-closed gate are
> present. A production run must remain blocked until the upstream required-quality hook and
> completion-oracle integration are available.

## Target execution path

```text
simplicio-loop-quality
  -> renders a strict quality task and declarative quality-agent profiles
  -> invokes exactly one simplicio-loop run
  -> simplicio-loop owns Hub, resources, isolation and agent execution
  -> quality agents author/run/audit the complete testing layer
  -> quality evidence is projected to quality-matrix.json
  -> the simplicio-loop Completion Oracle decides COMPLETE or BLOCKED
```

This repository intentionally contains no scheduler, queue, process pool, worktree manager, lease
manager, retry engine, daemon, or alternative `done` state.

## Quality layers

The strict policy covers:

- unit, component, integration, contract, system and end-to-end tests;
- regression, smoke, packaged-artifact and real-runtime tests;
- implementation completeness and independent code review;
- negative paths, timeout, retry, cancellation, idempotency and recovery;
- property testing, fuzzing, mutation testing and invariant review;
- concurrency, race, deadlock, leak and fault-injection testing;
- static quality, application security and supply-chain security;
- performance, load, stress, spike and soak measurements;
- line, branch, condition, changed-code and critical-path coverage;
- compatibility, installation, upgrade, downgrade and migration testing;
- test-selection validation, accessibility, operational readiness, privacy and executable docs;
- evidence freshness, commit binding, independent audit and reproducibility.

An inapplicable layer is never silently skipped. It needs a structured reason and independent
approval. A skipped, flaky, unexecuted, stale, unverifiable, or missing result is a failure. An
unavailable metric is `null` with a reason code, never zero and never an estimate.

## CLI bootstrap

```bash
pip install -e .

simplicio-loop-quality doctor
simplicio-loop-quality agents
simplicio-loop-quality plan --repo /path/to/project --out quality-task.md
simplicio-loop-quality run --repo /path/to/project
simplicio-loop-quality gate \
  --receipt quality-evidence.json \
  --source-sha "$LOOP_SOURCE_SHA" \
  --artifact-root "$LOOP_ARTIFACT_ROOT"
```

When `doctor` proves every required upstream capability, `run` creates the quality task outside the
target worktree and delegates it to `simplicio-loop run --delivery verified`. Until then it exits
`BLOCKED` before starting work. It never starts local workers itself.

The standalone `gate` command is a diagnostic contract verifier: it rehashes referenced artifacts
and compares the receipt with an expected source SHA, but deliberately returns `BLOCKED` because a
CLI caller cannot establish Loop-ledger provenance. Authoritative PASS requires the internal Loop
provider path, independent re-execution and the Completion Oracle.

## Non-negotiable scope

Quality agents may create or improve tests, fixtures, test configuration, quality CI and evidence.
They do not implement unrelated product features. A product defect found by testing becomes a
structured finding returned to the Loop recovery/implementation stage.

See [Architecture](docs/ARCHITECTURE.md), [Quality contract](docs/QUALITY_CONTRACT.md), and the
[upstream blockers](docs/UPSTREAM_REQUIREMENTS.md).

## Development

```bash
python scripts/check.py
pytest --cov=simplicio_loop_quality --cov-branch --cov-fail-under=85
```

## License

MIT
