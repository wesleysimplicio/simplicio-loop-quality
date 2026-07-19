# simplicio-loop-quality — agent contract

## Mission

Apply the complete testing and quality layer to any project by invoking `simplicio-loop` as the
single execution authority.

## Architectural boundary

This repository owns only:

- quality policies and applicability decisions;
- specialized quality-agent definitions;
- test-tool adapters and quality plans;
- quality evidence, findings, reports and fail-closed gates;
- a thin invocation/extension bridge to `simplicio-loop`.

This repository must never implement or own:

- a scheduler, queue, worker pool, Hub, daemon or process supervisor;
- worktree creation, leases, fencing, heartbeats, retry or backpressure;
- a second run journal, delivery pipeline or terminal state;
- direct issue closure, merge or release authority.

All execution is submitted to the Loop Hub. The Loop Completion Oracle is the only authority that
may accept the evidence and declare completion.

## Agent rules

1. The agent that authors a test cannot independently approve the same evidence.
2. Quality agents may modify test code, fixtures, test configuration, quality CI and testability
   seams explicitly authorized by the quality plan.
3. Product defects become structured findings for the Loop recovery/implementation stage.
4. No agent or test-tool adapter may invoke `subprocess`, create threads/process pools or manage
   concurrency directly; tool execution is delegated through the Loop execution port. The sole
   exception is the thin top-level invoker starting exactly one authoritative Loop process.
5. Every result is bound to run, task, attempt, source SHA, policy hash and tool version.
6. `skipped`, `xfailed`, flaky, timed out, missing or unverifiable never means pass.
7. `N/A` requires a reason code, technical justification and independent approval.
8. Missing metrics are `null` plus a machine-readable reason, never zero or an estimate.

## Definition of Done

No work item is complete until every applicable quality lane is `PASS`, every `N/A` is independently
approved, coverage thresholds are measured, performance has a real baseline when applicable, all
evidence is fresh for the exact commit, and an independent Quality Gate emits a passing receipt for
the Loop Completion Oracle.
