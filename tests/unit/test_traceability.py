import unittest

from simplicio_loop_quality.traceability import evaluate_traceability, parse_markdown_issue


def _valid_document():
    identity = {
        "run_id": "run-1",
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "source_sha": "a" * 40,
        "diff_hash": "b" * 64,
        "policy_hash": "c" * 64,
    }
    return {
        "identity": identity,
        "criteria": [
            {
                "id": "AC-1",
                "text": "The quality gate rejects missing evidence.",
                "required": True,
                "planned_test_ids": ["TEST-1"],
                "evidence_types": ["test-log"],
            }
        ],
        "tests": [
            {
                "id": "TEST-1",
                "name": "missing evidence is rejected",
                "criterion_ids": ["AC-1"],
                "evidence_types": ["test-log"],
            }
        ],
        "evidence": [
            {
                "ref": "artifacts/test-1.json",
                "test_id": "TEST-1",
                "criterion_ids": ["AC-1"],
                "evidence_type": "test-log",
                "accepted": True,
                "status": "PASS",
                "producer_agent": "executor-1",
                "audit_agent": "auditor-1",
                "identity": identity,
            }
        ],
    }


class TraceabilityTest(unittest.TestCase):
    def test_valid_document_builds_deterministic_mapping(self):
        source = _valid_document()
        first = evaluate_traceability(source, expected_identity=source["identity"])
        second = evaluate_traceability(source, expected_identity=source["identity"])

        self.assertEqual(first.status, "PASS")
        self.assertEqual(first.mapping, second.mapping)
        self.assertEqual(first.mapping_sha256, second.mapping_sha256)
        self.assertEqual(first.mapping[0]["evidence_refs"], ["artifacts/test-1.json"])

    def test_missing_evidence_and_orphan_test_are_fail_closed(self):
        source = _valid_document()
        source["evidence"] = []
        source["tests"].append(
            {
                "id": "TEST-ORPHAN",
                "name": "unplanned test",
                "criterion_ids": [],
                "evidence_types": ["test-log"],
            }
        )

        verdict = evaluate_traceability(source)
        codes = {finding.reason_code for finding in verdict.findings}
        self.assertEqual(verdict.status, "FAIL")
        self.assertIn("required_criterion_unproven", codes)
        self.assertIn("irrelevant_test", codes)

    def test_duplicate_and_contradictory_criteria_block(self):
        source = _valid_document()
        source["criteria"].append({**source["criteria"][0], "text": "A contradictory statement."})

        verdict = evaluate_traceability(source)
        self.assertEqual(verdict.status, "BLOCKED")
        self.assertIn("contradictory_criterion", {item.reason_code for item in verdict.findings})

    def test_self_approved_evidence_is_blocked(self):
        source = _valid_document()
        source["evidence"][0]["audit_agent"] = source["evidence"][0]["producer_agent"]

        verdict = evaluate_traceability(source)
        self.assertEqual(verdict.status, "BLOCKED")
        self.assertIn("evidence_self_approval", {item.reason_code for item in verdict.findings})

    def test_loop_binding_requires_every_identity_field(self):
        source = _valid_document()
        del source["identity"]["attempt_id"]

        verdict = evaluate_traceability(source, expected_identity=_valid_document()["identity"])
        self.assertEqual(verdict.status, "BLOCKED")
        self.assertIn("traceability_identity_missing", {item.reason_code for item in verdict.findings})

    def test_markdown_requires_stable_ids_and_links(self):
        markdown = """# Acceptance Criteria
- [ ] AC-1: Build a deterministic trace.
  Tests: TEST-1
  Evidence: test-log

# Planned Tests
- `TEST-1`: traceability unit test
  Criteria: AC-1
  Evidence: test-log
"""
        parsed = parse_markdown_issue(markdown)
        self.assertEqual(parsed["criteria"][0]["id"], "AC-1")
        self.assertEqual(parsed["criteria"][0]["planned_test_ids"], ["TEST-1"])
        self.assertEqual(parsed["tests"][0]["criterion_ids"], ["AC-1"])


if __name__ == "__main__":
    unittest.main()
