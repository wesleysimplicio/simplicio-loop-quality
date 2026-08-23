import unittest
from datetime import datetime, timedelta, timezone

from simplicio_loop_quality.risk_selection import (
    RiskSelectionError,
    assess_risk,
    is_monotonic,
    select_quality_suites,
)


def _impact(*, api=False, unknowns=(), impacted=1):
    return {
        "changed_files": ["src/api/routes.py"] if api else ["src/core.py"],
        "impacted_files": [f"src/file-{index}.py" for index in range(impacted)],
        "unknowns": list(unknowns),
        "risk_surfaces": [{"kind": "public_api"}] if api else [],
    }


class RiskSelectionTest(unittest.TestCase):
    def test_golden_risk_table(self):
        low = select_quality_suites(_impact())
        high = select_quality_suites(_impact(api=True, impacted=10))
        self.assertEqual(low.policy_level, "low")
        self.assertIn("contract", high.mandatory_lanes)
        self.assertIn("integration", high.mandatory_lanes)
        self.assertGreaterEqual(high.assessment.category_scores["api"], 0.65)

    def test_selection_is_monotonic_when_impact_increases(self):
        base = select_quality_suites(_impact())
        expanded = select_quality_suites(_impact(api=True, unknowns=("missing map",), impacted=12))
        self.assertTrue(is_monotonic(base, expanded))

    def test_exclusion_requires_scoped_independent_unexpired_waiver(self):
        expires = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        waiver = {
            "waiver_id": "W-1",
            "justification": "The repository has no public API.",
            "approver": "reviewer",
            "created_by": "author",
            "scope": "contract",
            "expires_at": expires,
            "source_sha": "a" * 40,
        }
        selection = select_quality_suites(_impact(api=True), exclusions={"contract": waiver}, source_sha="a" * 40)
        self.assertNotIn("contract", selection.mandatory_lanes)
        with self.assertRaises(RiskSelectionError):
            select_quality_suites(_impact(api=True), exclusions={"contract": {**waiver, "scope": "*"}}, source_sha="a" * 40)


if __name__ == "__main__":
    unittest.main()
