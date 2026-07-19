# Implementation backlog

`issues.json` is the canonical, machine-readable backlog for `simplicio-loop-quality`.

It contains 73 granular issues grouped into six milestones:

| Milestone | Scope | Issues |
| --- | --- | --- |
| M0 | contracts, package, policy and SDK | QLT-001–007 |
| M1 | centralized integration with the Loop Hub and lifecycle | QLT-008–012 |
| M2 | planning, evidence, governance and core test agents | QLT-013–031 |
| M3 | advanced assurance and universal project adapters | QLT-032–055 |
| M4 | CI, Simplicio ecosystem, dogfood, documentation and release | QLT-056–062 |
| M5 | split ecosystem adapters and universal quality completion | QLT-063–073 |

Run the structural check:

```bash
python scripts/backlog.py check
```

Render one GitHub issue body:

```bash
python scripts/backlog.py render QLT-001
```

Export the complete idempotency-friendly GitHub creation plan as JSON Lines:

```bash
python scripts/backlog.py export > github-issues.jsonl
```

Every rendered body carries a stable `backlog-id` marker; the export also derives the milestone,
priority label and epic label used to reconcile reruns without duplicating issues.

The common Definition of Done stored in the manifest is appended to every rendered issue.

## Upstream blockers already recorded in simplicio-loop

- [#612 — Completion Oracle must be the only path to done](https://github.com/wesleysimplicio/simplicio-loop/issues/612)
- [#613 — required quality provider hook](https://github.com/wesleysimplicio/simplicio-loop/issues/613)
- [#614 — production StageGraphExtension registry/composition](https://github.com/wesleysimplicio/simplicio-loop/issues/614)
- [#615 — StageAgentCoordinator to Hub bridge](https://github.com/wesleysimplicio/simplicio-loop/issues/615)
- [#616 — real concurrent execution of independent waves](https://github.com/wesleysimplicio/simplicio-loop/issues/616)
- [#617 — evidence invalidation after mutations](https://github.com/wesleysimplicio/simplicio-loop/issues/617)
- [#618 — complete quality-matrix/v2 contract](https://github.com/wesleysimplicio/simplicio-loop/issues/618)
- [#619 — authoritative run outcome and exit status](https://github.com/wesleysimplicio/simplicio-loop/issues/619)
- [#620 — Loop-owned hermetic environments](https://github.com/wesleysimplicio/simplicio-loop/issues/620)
- [#621 — exact-runtime extension handshake](https://github.com/wesleysimplicio/simplicio-loop/issues/621)
