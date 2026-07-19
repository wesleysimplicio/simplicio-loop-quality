import copy
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from simplicio_loop_quality.gate import GateContext, evaluate_receipt
from simplicio_loop_quality.policy import load_strict_policy
from tests.helpers import passing_receipt


class GateTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.artifact_root = Path(self.temporary.name)
        self.policy = load_strict_policy()
        self.receipt = passing_receipt(self.policy, artifact_root=self.artifact_root)
        self.context = GateContext(
            expected_run_id=self.receipt["run_id"],
            expected_task_id=self.receipt["task_id"],
            expected_attempt_id=self.receipt["attempt_id"],
            expected_source_sha=self.receipt["source_sha"],
            expected_diff_hash=self.receipt["diff_hash"],
            expected_policy_hash=self.receipt["policy_hash"],
            artifact_root=self.artifact_root,
            trusted_by_loop=True,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def evaluate(self, receipt=None, policy=None, context=None):
        return evaluate_receipt(
            self.receipt if receipt is None else receipt,
            self.policy if policy is None else policy,
            self.context if context is None else context,
        )

    def test_complete_receipt_passes(self):
        verdict = self.evaluate()
        self.assertTrue(verdict.ready)
        self.assertEqual(verdict.reason_code, "quality_policy_satisfied")
        self.assertEqual(verdict.to_dict()["status"], "PASS")

    def test_gate_requires_trusted_verification_context(self):
        verdict = evaluate_receipt(self.receipt, self.policy)
        self.assertEqual(verdict.status, "BLOCKED")
        self.assertEqual(verdict.reason_code, "verification_context_missing")

    def test_standalone_context_can_validate_but_never_authorize_pass(self):
        context = replace(self.context, trusted_by_loop=False)
        verdict = self.evaluate(context=context)
        self.assertEqual(verdict.status, "BLOCKED")
        self.assertEqual(verdict.reason_code, "verification_context_untrusted")

    def test_receipt_identity_diff_and_policy_bind_to_loop_context(self):
        context = replace(
            self.context,
            expected_run_id="trusted-run",
            expected_diff_hash="e" * 64,
            expected_policy_hash="f" * 64,
        )
        codes = {finding.reason_code for finding in self.evaluate(context=context).findings}
        self.assertTrue(
            {
                "receipt_identity_mismatch",
                "diff_hash_mismatch",
                "policy_context_mismatch",
            }.issubset(codes)
        )

    def test_source_must_match_trusted_loop_context(self):
        context = GateContext(
            expected_run_id=self.receipt["run_id"],
            expected_task_id=self.receipt["task_id"],
            expected_attempt_id=self.receipt["attempt_id"],
            expected_source_sha="b" * 40,
            expected_diff_hash=self.receipt["diff_hash"],
            expected_policy_hash=self.receipt["policy_hash"],
            artifact_root=self.artifact_root,
            trusted_by_loop=True,
        )
        codes = {finding.reason_code for finding in self.evaluate(context=context).findings}
        self.assertIn("source_sha_mismatch", codes)

    def test_source_sha_must_be_a_full_git_digest(self):
        self.receipt["source_sha"] = "short"
        codes = {finding.reason_code for finding in self.evaluate().findings}
        self.assertIn("source_sha_invalid", codes)

    def test_diff_hash_and_timestamp_must_be_canonical(self):
        self.receipt["diff_hash"] = "short"
        for timestamp in ("2026-07-19T12:00:00", "not-a-timestamp"):
            with self.subTest(timestamp=timestamp):
                self.receipt["generated_at"] = timestamp
                codes = {finding.reason_code for finding in self.evaluate().findings}
                self.assertIn("diff_hash_invalid", codes)
                self.assertIn("generated_at_invalid", codes)

    def test_artifact_is_rehashed_and_must_exist(self):
        lane = self.policy.lanes[0]
        evidence = self.receipt["lanes"][lane]["evidence"][0]
        artifact = self.artifact_root / evidence["ref"]
        artifact.write_text("tampered", encoding="utf-8")
        codes = {finding.reason_code for finding in self.evaluate().findings}
        self.assertIn("lane_evidence_hash_mismatch", codes)

        artifact.unlink()
        codes = {finding.reason_code for finding in self.evaluate().findings}
        self.assertIn("lane_evidence_artifact_missing", codes)

    def test_unsafe_artifact_reference_is_rejected(self):
        lane = self.policy.lanes[0]
        self.receipt["lanes"][lane]["evidence"][0]["ref"] = "../outside.json"
        codes = {finding.reason_code for finding in self.evaluate().findings}
        self.assertIn("lane_evidence_ref_unsafe", codes)

    def test_symlink_cannot_escape_artifact_root(self):
        lane = self.policy.lanes[0]
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "external.json"
            external.write_text("outside", encoding="utf-8")
            link = self.artifact_root / "escape-link.json"
            link.symlink_to(external)
            self.receipt["lanes"][lane]["evidence"][0]["ref"] = link.name
            codes = {finding.reason_code for finding in self.evaluate().findings}
        self.assertIn("lane_evidence_ref_unsafe", codes)

    def test_empty_artifact_reference_is_rejected_without_resolution(self):
        lane = self.policy.lanes[0]
        self.receipt["lanes"][lane]["evidence"][0]["ref"] = ""
        codes = {finding.reason_code for finding in self.evaluate().findings}
        self.assertIn("lane_evidence_field_missing", codes)

    def test_evidence_execution_metadata_is_validated(self):
        lane = self.policy.lanes[0]
        evidence = self.receipt["lanes"][lane]["evidence"][0]
        evidence.update(
            {
                "run_id": "another-run",
                "command": [],
                "exit_code": True,
                "duration_ms": -1,
                "sha256": "not-a-digest",
                "environment_hash": "not-a-digest",
            }
        )
        codes = {finding.reason_code for finding in self.evaluate().findings}
        self.assertTrue(
            {
                "lane_evidence_identity_mismatch",
                "lane_evidence_command_invalid",
                "lane_evidence_exit_invalid",
                "lane_evidence_duration_invalid",
                "lane_evidence_hash_invalid",
                "lane_evidence_environment_invalid",
            }.issubset(codes)
        )

    def test_unreadable_artifact_fails_closed(self):
        with mock.patch(
            "simplicio_loop_quality.gate._file_sha256",
            side_effect=OSError("read failed"),
        ):
            codes = {finding.reason_code for finding in self.evaluate().findings}
        self.assertIn("lane_evidence_artifact_unreadable", codes)

    def test_non_object_receipt_blocks(self):
        verdict = self.evaluate([])
        self.assertFalse(verdict.ready)
        self.assertEqual(verdict.status, "BLOCKED")

    def test_missing_lane_fails(self):
        del self.receipt["lanes"][self.policy.lanes[0]]
        verdict = self.evaluate()
        self.assertEqual(verdict.reason_code, "lane_missing")

    def test_pass_without_evidence_fails(self):
        lane = self.policy.lanes[0]
        self.receipt["lanes"][lane]["evidence"] = []
        codes = {
            finding.reason_code
            for finding in self.evaluate().findings
        }
        self.assertIn("lane_evidence_missing", codes)

    def test_malformed_and_unbound_evidence_fail(self):
        lane = self.policy.lanes[0]
        cases = [
            ["not-an-object"],
            [{"ref": "x", "sha256": "", "source_sha": self.receipt["source_sha"]}],
            [{"ref": "x", "sha256": "a", "source_sha": "different"}],
        ]
        expected = [
            "lane_evidence_malformed",
            "lane_evidence_field_missing",
            "lane_evidence_source_mismatch",
        ]
        for evidence, code in zip(cases, expected, strict=True):
            with self.subTest(code=code):
                receipt = copy.deepcopy(self.receipt)
                receipt["lanes"][lane]["evidence"] = evidence
                codes = {f.reason_code for f in self.evaluate(receipt).findings}
                self.assertIn(code, codes)

    def test_na_requires_justification_and_independent_approval(self):
        lane = self.policy.lanes[0]
        self.receipt["lanes"][lane] = {
            "status": "not_applicable",
            "justification": "",
            "approved_by": [self.receipt["producer_agent"]],
        }
        codes = {f.reason_code for f in self.evaluate().findings}
        self.assertIn("na_justification_missing", codes)
        self.assertIn("na_independent_approval_missing", codes)

    def test_valid_na_can_pass(self):
        lane = self.policy.lanes[0]
        self.receipt["lanes"][lane] = {
            "status": "not_applicable",
            "justification": "No executable surface exists for this lane",
            "approved_by": ["independent-reviewer"],
        }
        self.assertTrue(self.evaluate().ready)

    def test_rejected_failed_blocked_and_unknown_statuses_fail(self):
        lane = self.policy.lanes[0]
        expected = {
            "skipped": "lane_rejected_status",
            "fail": "lane_failed",
            "blocked": "lane_blocked",
            "unexpected": "lane_status_invalid",
        }
        for status, code in expected.items():
            with self.subTest(status=status):
                receipt = copy.deepcopy(self.receipt)
                receipt["lanes"][lane]["status"] = status
                codes = {f.reason_code for f in self.evaluate(receipt).findings}
                self.assertIn(code, codes)

    def test_inability_to_execute_is_blocked_not_failed(self):
        lane = self.policy.lanes[0]
        self.receipt["lanes"][lane]["status"] = "blocked"
        verdict = self.evaluate()
        self.assertEqual(verdict.status, "BLOCKED")

        self.receipt = passing_receipt(self.policy, artifact_root=self.artifact_root)
        self.receipt["coverage"] = {
            "global_pct": None,
            "changed_pct": None,
            "critical_pct": None,
            "reason_code": "tool_unavailable",
        }
        self.assertEqual(self.evaluate().status, "BLOCKED")

    def test_coverage_null_is_not_zero_and_below_threshold_fails(self):
        self.receipt["coverage"]["global_pct"] = None
        self.receipt["coverage"]["changed_pct"] = 0
        codes = [f.reason_code for f in self.evaluate().findings]
        self.assertIn("coverage_unmeasured", codes)
        self.assertIn("coverage_below_threshold", codes)
        self.assertEqual(self.evaluate().status, "FAIL")

    def test_coverage_object_is_mandatory(self):
        self.receipt["coverage"] = []
        verdict = self.evaluate()
        self.assertEqual(verdict.reason_code, "coverage_missing")

    def test_na_approval_can_be_disabled_by_an_explicit_policy(self):
        policy = replace(self.policy, na_requires_independent_approval=False)
        receipt = passing_receipt(policy, artifact_root=self.artifact_root)
        receipt["lanes"][policy.lanes[0]] = {
            "status": "not_applicable",
            "justification": "The target has no executable surface for this lane",
            "approved_by": [],
        }
        context = replace(self.context, expected_policy_hash=receipt["policy_hash"])
        self.assertTrue(self.evaluate(receipt, policy, context).ready)

    def test_invalid_coverage_type_and_range_fail(self):
        for value in (True, "90", 101):
            with self.subTest(value=value):
                receipt = copy.deepcopy(self.receipt)
                receipt["coverage"]["global_pct"] = value
                codes = {f.reason_code for f in self.evaluate(receipt).findings}
                self.assertIn("coverage_invalid", codes)

    def test_policy_mismatch_and_self_approval_fail(self):
        self.receipt["policy_hash"] = "wrong"
        self.receipt["audit_agent"] = self.receipt["producer_agent"]
        codes = {f.reason_code for f in self.evaluate().findings}
        self.assertIn("policy_hash_mismatch", codes)
        self.assertIn("self_approval_forbidden", codes)

    def test_missing_top_level_fields_and_lanes_fail(self):
        fields = (
            "schema",
            "run_id",
            "task_id",
            "attempt_id",
            "source_sha",
            "diff_hash",
            "policy_hash",
            "generated_at",
            "producer_agent",
            "audit_agent",
        )
        for field in fields:
            with self.subTest(field=field):
                receipt = copy.deepcopy(self.receipt)
                receipt.pop(field)
                self.assertFalse(self.evaluate(receipt).ready)
        receipt = copy.deepcopy(self.receipt)
        receipt["lanes"] = []
        codes = {f.reason_code for f in self.evaluate(receipt).findings}
        self.assertIn("lanes_missing", codes)
