import unittest
from dataclasses import replace

from simplicio_loop_quality.policy import (
    CoverageThresholds,
    PolicyError,
    QualityPolicy,
    ensure_authoritative_policy,
    load_strict_policy,
)


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.raw = {
            "schema": "simplicio.quality-policy/v1",
            "policy_id": "test",
            "coverage": {
                "global_min_pct": 85,
                "changed_min_pct": 90,
                "critical_min_pct": 100,
            },
            "na_requires_independent_approval": True,
            "reject_statuses": ["skipped"],
            "lanes": ["unit", "integration"],
        }

    def test_packaged_policy_is_strict_and_stable(self):
        policy = load_strict_policy()
        self.assertGreaterEqual(len(policy.lanes), 25)
        self.assertEqual(policy.coverage.changed_min_pct, 90)
        self.assertEqual(policy.canonical_hash, load_strict_policy().canonical_hash)

    def test_unknown_policy_field_fails(self):
        self.raw["surprise"] = True
        with self.assertRaisesRegex(PolicyError, "unknown policy fields"):
            QualityPolicy.from_mapping(self.raw)

    def test_unknown_coverage_field_fails(self):
        self.raw["coverage"]["extra"] = 1
        with self.assertRaisesRegex(PolicyError, "unknown coverage fields"):
            QualityPolicy.from_mapping(self.raw)

    def test_missing_coverage_field_fails(self):
        del self.raw["coverage"]["global_min_pct"]
        with self.assertRaisesRegex(PolicyError, "missing coverage fields"):
            QualityPolicy.from_mapping(self.raw)

    def test_duplicate_or_empty_lanes_fail(self):
        for lanes in (["unit", "unit"], ["unit", ""], []):
            with self.subTest(lanes=lanes):
                self.raw["lanes"] = lanes
                with self.assertRaises(PolicyError):
                    QualityPolicy.from_mapping(self.raw)

    def test_invalid_coverage_values_fail(self):
        for value in (-1, 101, True, "90"):
            with self.subTest(value=value):
                self.raw["coverage"]["global_min_pct"] = value
                with self.assertRaises(PolicyError):
                    QualityPolicy.from_mapping(self.raw)

    def test_schema_and_shape_are_required(self):
        cases = [
            {**self.raw, "schema": "wrong"},
            {**self.raw, "policy_id": ""},
            {**self.raw, "coverage": []},
            {**self.raw, "reject_statuses": "skipped"},
            {**self.raw, "na_requires_independent_approval": "yes"},
        ]
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(PolicyError):
                QualityPolicy.from_mapping(payload)

    def test_authoritative_policy_cannot_weaken_strict_floor(self):
        strict = load_strict_policy()
        weak = replace(
            strict,
            lanes=strict.lanes[1:],
            coverage=CoverageThresholds(0, 0, 0),
            reject_statuses=frozenset(),
            na_requires_independent_approval=False,
        )
        with self.assertRaisesRegex(PolicyError, "weakens strict-default"):
            ensure_authoritative_policy(weak, strict)

    def test_equal_or_stronger_authoritative_policy_passes(self):
        strict = load_strict_policy()
        stronger = replace(
            strict,
            lanes=(*strict.lanes, "project_specific"),
            coverage=CoverageThresholds(90, 95, 100),
            reject_statuses=strict.reject_statuses | {"project_rejected"},
        )
        self.assertIs(ensure_authoritative_policy(stronger, strict), stronger)
