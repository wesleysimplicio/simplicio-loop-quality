# Simplicio-EVO benchmark lane

The benchmark is designed for release-sized changes rather than isolated
single-file fixes. Its dataset contract requires at least 12 tasks across
three repositories and three task classes, with immutable base SHAs,
specifications and independent tests.

Every task is evaluated in S0 baseline, S1 runtime, S2 runtime plus Loop,
S3 full stack and S4 Loop plus Fast standalone scenarios. Runs require ten
repetitions when determinism permits, raw samples, equal budgets and receipts.

Metrics that cannot be observed are null with an explicit reason. They are
never replaced with zero or an estimate. The evaluator also requires
fail-to-pass and pass-to-pass evidence and preserves holdout provenance.

This repository supplies the contract and evaluator. A complete scorecard
requires curated tasks and the corresponding Runtime, Mapper, Fast, Loop and
Dev CLI environments.
