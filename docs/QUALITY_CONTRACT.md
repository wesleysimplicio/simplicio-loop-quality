# Strict quality contract

Every lane has one of four evidence states:

- `PASS`: the command ran successfully and has fresh, commit-bound evidence.
- `FAIL`: the command or assertion failed.
- `BLOCKED`: the required validation could not run or could not be verified.
- `NOT_APPLICABLE`: structurally irrelevant, with reason and independent approval.

`SKIPPED`, `XFAIL`, `FLAKY`, `NOT_RUN`, `UNKNOWN` and missing are never terminal success states.

The packaged strict policy is the minimum authoritative floor. Project policy may add lanes,
rejections or stricter thresholds, but it may not remove required lanes, lower coverage, accept a
rejected status or disable independent `N/A` approval. Until Loop supports content-addressed policy
delivery, custom policies are diagnostic-only.

## Versioned policy resolution

`quality-policy/v1` is closed to unknown fields and resolves, in order, the packaged strict floor,
global overlay, project overlay and CLI overlay. Later layers may only strengthen the result:
coverage floors increase, performance ceilings decrease, rejection sets and lanes grow, and risk
never decreases. Escalating to `critical` must add at least one mandatory lane.

Run `simplicio-loop-quality policy` with optional `--global-policy`, `--project-policy` and
`--policy` overlays to print the resolved policy, its canonical SHA-256, and the ordered source
digests. Invalid or ambiguous input exits nonzero before a task or gate is submitted. The gate binds
evidence to this locally resolved hash instead of trusting a hash asserted by the receipt.

## Default coverage policy

- global line/branch coverage: at least 85%;
- changed-code coverage: at least 90%;
- critical gates and invariants: 100%;
- no unexplained coverage decrease.

## Evidence minimum

Each passing lane must record:

- run, task, attempt and agent identity;
- repository and exact source SHA;
- policy/configuration hash;
- tool name and version;
- structured command specification and exit code;
- start/end time and duration;
- random seed where relevant;
- environment fingerprint;
- artifact references and SHA-256 hashes;
- independent audit identity when required.

Benchmarks additionally require warm-up, raw samples, baseline, repetitions, p50/p95/p99,
variability and environment controls. No saving or speed claim is valid without direct evidence.
