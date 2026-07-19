# Architecture

## Decision

`simplicio-loop-quality` is a thin `simplicio.loop-extension/v1` provider. It specializes quality;
it does not fork orchestration.

## Ownership

| Concern | Owner |
| --- | --- |
| Quality policy, test applicability and test agents | `simplicio-loop-quality` |
| Test plans, findings, evidence and reports | `simplicio-loop-quality` |
| Queue, waves, scheduling, fairness and resource budgets | `simplicio-loop` Hub |
| Processes, worktrees, leases, retries and cancellation | `simplicio-loop` |
| Delivery and terminal completion | `simplicio-loop` Completion Oracle |

## Control flow

1. The quality CLI probes the installed Loop and validates the extension manifest.
2. It renders one canonical task describing only the testing/quality work.
3. It invokes one `simplicio-loop run` for the target repository.
4. The Loop loads quality role bindings and assigns specialized agents through its stage-agent
   coordinator and Hub.
5. Agents create and run tests, returning structured receipts to the Loop ledger.
6. An independent evidence auditor recomputes hashes and freshness.
7. The Quality Gate creates a full report and a compatible `quality-matrix.json` projection.
8. The Loop Completion Oracle alone decides whether the source work item may complete.

## Fail-closed behavior

- Loop unavailable or incompatible: `BLOCKED`.
- Required quality hook unavailable: `BLOCKED`.
- Hub unavailable: `BLOCKED`; no local subprocess fallback.
- Missing or malformed evidence: `FAIL`.
- Stale commit/diff binding: `FAIL`.
- Unsupported toolchain without an authorized external harness: `BLOCKED`.
- Metric unavailable: value `null` plus a reason; any gate needing it remains blocked.

## Agent topology

The extension contributes agent profiles for planning, test infrastructure, unit/component,
integration/contract, system/E2E, regression, real installation, property/fuzz, mutation,
invariants, concurrency/reliability, security, performance, compatibility, evidence auditing and
the terminal quality gate. These are roles executed by Loop; they are not local worker processes.
