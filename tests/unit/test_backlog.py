import copy
import unittest

from scripts.backlog import export_records, load_backlog, render_issue, validate_backlog


class BacklogTest(unittest.TestCase):
    def setUp(self):
        self.payload = load_backlog()

    def test_canonical_backlog_is_valid_and_granular(self):
        self.assertEqual(validate_backlog(self.payload), [])
        self.assertEqual(len(self.payload["issues"]), 73)

    def test_every_issue_renders_steps_acceptance_tests_and_dod(self):
        for issue in self.payload["issues"]:
            with self.subTest(issue=issue["id"]):
                body = render_issue(self.payload, issue["id"])
                self.assertIn("## Scope and implementation steps", body)
                self.assertIn("## Acceptance criteria", body)
                self.assertIn("## Required tests and evidence", body)
                self.assertIn("## Common Definition of Done", body)
                self.assertIn(f"<!-- backlog-id: {issue['id']} -->", body)

    def test_forward_dependency_is_rejected(self):
        broken = copy.deepcopy(self.payload)
        broken["issues"][0]["depends_on"] = ["QLT-002"]
        self.assertTrue(any("later issue" in error for error in validate_backlog(broken)))

    def test_unknown_issue_cannot_render(self):
        with self.assertRaisesRegex(ValueError, "unknown issue"):
            render_issue(self.payload, "QLT-999")

    def test_invalid_metadata_and_list_values_are_rejected_without_crashing(self):
        broken = copy.deepcopy(self.payload)
        broken["issues"][0]["priority"] = "URGENT"
        broken["issues"][0]["epic"] = "Unknown"
        broken["issues"][0]["steps"] = [None, ""]
        broken["issues"][1]["depends_on"] = [{}, "QLT-001", "QLT-001"]
        broken["issues"][1]["blocked_by"] = ["not-an-issue"]
        errors = validate_backlog(broken)
        self.assertTrue(any("priority" in error for error in errors))
        self.assertTrue(any("epic" in error for error in errors))
        self.assertTrue(any("non-empty strings" in error for error in errors))
        self.assertTrue(any("duplicates" in error for error in errors))
        self.assertTrue(any("GitHub issue URL" in error for error in errors))

    def test_milestones_must_cover_every_issue_exactly_once(self):
        broken = copy.deepcopy(self.payload)
        broken["milestones"][-1]["issues"] = "QLT-064..QLT-073"
        self.assertTrue(
            any("cover every issue" in error for error in validate_backlog(broken))
        )

    def test_export_is_stable_and_ready_for_idempotent_reconciliation(self):
        records = export_records(self.payload)
        self.assertEqual(len(records), 73)
        self.assertEqual(records[0]["backlog_id"], "QLT-001")
        self.assertTrue(records[0]["title"].startswith("[QLT-001]"))
        self.assertIn("priority:p0", records[0]["labels"])
        self.assertEqual(records[0]["milestone"], "Contracts")
        self.assertIn("<!-- backlog-id: QLT-001 -->", records[0]["body"])
