# Adapter authoring guide

An adapter describes how a quality agent can translate immutable request data
into structured evidence. It is not a worker and it is not an orchestration
port.

## Required contract

1. Declare one stable adapter id and the supported quality-adapter/v1 API.
2. Declare capabilities, output fields and resource requirements explicitly.
3. Accept immutable request data and return structured output or an explicit
   adapter error.
4. Include source, policy, configuration and toolchain bindings in evidence.
5. Represent commands as Loop ProcessSpec data; never run subprocesses here.
6. Preserve cancellation, crash and invalid-output states as non-success.

## Review checklist

- The adapter has focused unit tests for valid, invalid, cancelled and crashed
  results.
- No import or filesystem change adds a scheduler, retry loop, worker pool or
  terminal completion state.
- Evidence is independently auditable and contains artifact references.
- Unsupported versions and duplicate adapter ids fail closed.

Use the existing adapters.py and agent_sdk.py contracts as the implementation
reference. A new adapter is ready only when the Loop integration lane can
exercise it through the authoritative Hub path.
