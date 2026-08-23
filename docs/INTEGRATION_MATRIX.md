# Ecosystem integration matrix

The ecosystem_matrix module defines the reproducible matrix for the quality
extension. The base case is loop+quality; optional components are runtime,
mapper, dev-cli and agent. The planner expands every subset, so isolated,
partial and full combinations are represented without a hidden happy path.

Each result is bound to the exact source SHA and resolved policy hash. A result
without evidence, with a stale binding, with a duplicate case, or with a
non-PASS status cannot satisfy the matrix. Missing optional components are
represented by a planned case and an explicit BLOCKED result, not silently
removed from the denominator.

Run the focused contract check:

    PYTHONPATH=src python -m unittest -v tests/unit/test_ecosystem_matrix.py

The complete multi-repository matrix still requires the corresponding
Loop-managed environments and published component artifacts. Until those are
available, the evaluator intentionally reports BLOCKED or FAIL.
