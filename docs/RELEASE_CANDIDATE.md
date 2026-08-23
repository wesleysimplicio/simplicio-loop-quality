# Release-candidate process

The release candidate is built once from one source SHA. The candidate record
must contain artifact names, SHA-256 digests, sizes, SBOM, provenance,
signature and the results of every required check.

Required checks are golden suite, clean install, canary, upgrade, rollback and
tamper detection. A missing or unavailable check is BLOCKED. A false check is
FAIL. Only a complete record with every check true is PASS.

The evaluator does not build or publish artifacts and does not treat a local
wheel as proof of a clean install. The release workflow must attach the raw
logs and commit-bound evidence before promotion.

Run the focused check:

    PYTHONPATH=src python -m unittest -v tests/unit/test_release_candidate.py

The current workspace cannot claim a published clean-environment run unless
the build dependencies, package index and target Loop runtime are available.
