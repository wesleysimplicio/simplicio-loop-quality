import copy
import json
import math
import unittest
from dataclasses import replace
from importlib import resources

from hypothesis import given
from hypothesis import strategies as st

from simplicio_loop_quality.policy import (
    CoverageThresholds,
    PerformanceBudget,
    PolicyError,
    QualityPolicy,
    RiskPolicy,
    ensure_authoritative_policy,
    load_strict_policy,
    resolve_policy,
)


def valid_policy_mapping():
    return {
        "schema": "simplicio.quality-policy/v1",
        "policy_id": "test",
        "coverage": {
            "global_min_pct": 85,
            "changed_min_pct": 90,
            "critical_min_pct": 100,
        },
        "performance": {
            "max_duration_ms": 900000,
            "max_peak_memory_mb": 4096,
        },
        "risk": {
            "level": "high",
            "mandatory_lanes": ["invariants", "application_security", "evidence_audit"],
        },
        "na_requires_independent_approval": True,
        "reject_statuses": ["skipped", "xfail", "flaky", "not_run", "unknown"],
        "lanes": [
            "unit",
            "integration",
            "invariants",
            "application_security",
            "evidence_audit",
        ],
    }


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.raw = valid_policy_mapping()

    def test_packaged_policy_and_schema_are_strict_and_stable(self):
        policy = load_strict_policy()
        schema_resource = resources.files("simplicio_loop_quality.contracts").joinpath(
            "quality-policy-v1.schema.json"
        )
        schema = json.loads(schema_resource.read_text(encoding="utf-8"))
        self.assertEqual(schema["$id"], policy.schema)
        self.assertGreaterEqual(len(policy.lanes), 25)
        self.assertEqual(policy.coverage.changed_min_pct, 90)
        self.assertEqual(policy.risk.level, "high")
        self.assertEqual(policy.canonical_hash, load_strict_policy().canonical_hash)

    def test_unknown_and_missing_fields_fail_closed(self):
        cases = []
        unknown = copy.deepcopy(self.raw)
        unknown["surprise"] = True
        cases.append(unknown)
        unknown_coverage = copy.deepcopy(self.raw)
        unknown_coverage["coverage"]["extra"] = 1
        cases.append(unknown_coverage)
        missing_coverage = copy.deepcopy(self.raw)
        del missing_coverage["coverage"]["global_min_pct"]
        cases.append(missing_coverage)
        missing_risk = copy.deepcopy(self.raw)
        del missing_risk["risk"]
        cases.append(missing_risk)
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(PolicyError):
                QualityPolicy.from_mapping(payload)

    def test_duplicate_or_empty_string_arrays_fail(self):
        mutations = [
            ("lanes", ["unit", "unit"]),
            ("lanes", ["unit", ""]),
            ("lanes", []),
            ("reject_statuses", ["Skipped", "skipped"]),
        ]
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                payload = copy.deepcopy(self.raw)
                payload[field] = value
                with self.assertRaises(PolicyError):
                    QualityPolicy.from_mapping(payload)

    def test_non_finite_and_out_of_range_numbers_fail(self):
        for value in (-1, 101, True, "90", math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                payload = copy.deepcopy(self.raw)
                payload["coverage"]["global_min_pct"] = value
                with self.assertRaises(PolicyError):
                    QualityPolicy.from_mapping(payload)
        for value in (0, -1, math.nan, math.inf):
            with self.subTest(performance=value):
                payload = copy.deepcopy(self.raw)
                payload["performance"]["max_duration_ms"] = value
                with self.assertRaises(PolicyError):
                    QualityPolicy.from_mapping(payload)

    def test_schema_shape_and_cross_field_risk_are_required(self):
        cases = [
            {**self.raw, "schema": "wrong"},
            {**self.raw, "policy_id": 7},
            {**self.raw, "coverage": []},
            {**self.raw, "performance": []},
            {**self.raw, "risk": {"level": "extreme", "mandatory_lanes": []}},
            {**self.raw, "risk": {"level": "critical", "mandatory_lanes": []}},
            {**self.raw, "reject_statuses": "skipped"},
            {**self.raw, "na_requires_independent_approval": "yes"},
        ]
        missing_lane = copy.deepcopy(self.raw)
        missing_lane["risk"]["mandatory_lanes"].append("missing")
        cases.append(missing_lane)
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(PolicyError):
                QualityPolicy.from_mapping(payload)

    def test_authoritative_policy_cannot_weaken_any_strict_floor(self):
        strict = load_strict_policy()
        weak_policies = [
            replace(strict, lanes=strict.lanes[1:]),
            replace(strict, coverage=CoverageThresholds(0, 0, 0)),
            replace(strict, performance=PerformanceBudget(900001, 4096)),
            replace(strict, risk=RiskPolicy("medium", strict.risk.mandatory_lanes)),
            replace(strict, reject_statuses=frozenset()),
            replace(strict, na_requires_independent_approval=False),
        ]
        for weak in weak_policies:
            with self.subTest(weak=weak), self.assertRaisesRegex(PolicyError, "weakens"):
                ensure_authoritative_policy(weak)

    def test_resolution_precedence_is_monotonic_and_records_provenance(self):
        resolution = resolve_policy(
            global_policy={"coverage": {"global_min_pct": 86}},
            project_policy={
                "coverage": {"global_min_pct": 87, "changed_min_pct": 92},
                "performance": {"max_duration_ms": 800000},
            },
            cli_policy={
                "coverage": {"global_min_pct": 88},
                "performance": {"max_duration_ms": 700000},
                "risk": {
                    "level": "critical",
                    "mandatory_lanes": [
                        "invariants",
                        "application_security",
                        "evidence_audit",
                        "fault_injection",
                    ],
                },
            },
        )
        policy = resolution.policy
        self.assertEqual(policy.coverage.global_min_pct, 88)
        self.assertEqual(policy.coverage.changed_min_pct, 92)
        self.assertEqual(policy.performance.max_duration_ms, 700000)
        self.assertEqual(policy.risk.level, "critical")
        self.assertIn("fault_injection", policy.risk.mandatory_lanes)
        self.assertEqual(
            [source.layer for source in resolution.sources],
            ["strict-default", "global", "project", "cli"],
        )
        self.assertTrue(all(len(source.digest) == 64 for source in resolution.sources))
        self.assertEqual(resolution.to_dict()["policy_hash"], policy.canonical_hash)

    def test_each_layer_rejects_weakening_and_weak_baseline(self):
        weak_overlays = [
            {"coverage": {"global_min_pct": 84}},
            {"performance": {"max_duration_ms": 900001}},
            {"risk": {"level": "medium"}},
            {"risk": {"level": "critical"}},
            {"na_requires_independent_approval": False},
            {"reject_statuses": ["skipped"]},
            {
                "reject_statuses": [
                    "skipped",
                    "SKIPPED",
                    "xfail",
                    "flaky",
                    "not_run",
                    "unknown",
                ]
            },
        ]
        for layer in ("global_policy", "project_policy", "cli_policy"):
            for overlay in weak_overlays:
                with self.subTest(layer=layer, overlay=overlay), self.assertRaises(PolicyError):
                    resolve_policy(**{layer: overlay})
        strict = load_strict_policy()
        weak = replace(strict, coverage=CoverageThresholds(0, 0, 0))
        with self.assertRaises(PolicyError):
            resolve_policy(baseline=weak)

    @given(st.floats(min_value=0, max_value=84.999, allow_nan=False, allow_infinity=False))
    def test_property_any_lower_global_coverage_is_rejected(self, value):
        with self.assertRaises(PolicyError):
            resolve_policy(cli_policy={"coverage": {"global_min_pct": value}})

    @given(st.floats(min_value=85, max_value=100, allow_nan=False, allow_infinity=False))
    def test_property_any_stronger_global_coverage_is_preserved(self, value):
        policy = resolve_policy(cli_policy={"coverage": {"global_min_pct": value}}).policy
        self.assertEqual(policy.coverage.global_min_pct, value)
