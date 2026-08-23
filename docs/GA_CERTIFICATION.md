# Universal quality GA certification

GA certification is a matrix, not a single green command. Each declared
profile must provide unit, integration, system, regression, real-fixture,
changed-branch coverage, seeded golden defect, clean control, install and
rollback evidence.

The gate binds every result to the exact source SHA and requires an evidence
reference. Changed-branch coverage below 90 percent, missing cases, stale
results, failed lanes, false clean controls or unavailable evidence prevent
promotion.

The quality extension can plan and evaluate this matrix. Execution of the
authoritative matrix belongs to the Loop Hub and requires the published
component environments. Until that external evidence exists, the certification
must remain BLOCKED.

Run the focused contract check:

    PYTHONPATH=src python -m unittest -v tests/unit/test_ga_certification.py
