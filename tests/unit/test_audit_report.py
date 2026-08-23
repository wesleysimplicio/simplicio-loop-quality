import unittest

from scripts.audit_report import audit_backlog


def backlog():
    return {"issues": [{"id": "QLT-001"}, {"id": "QLT-002"}]}


def entry(decision="IMPLEMENTED"):
    return {
        "decision": decision,
        "implementation_refs": ["commit"],
        "test_refs": ["test"],
        "evidence_refs": ["receipt"],
        **({"blocker": "upstream"} if decision == "BLOCKED" else {}),
    }


class AuditReportTest(unittest.TestCase):
    def test_complete_ledger_passes(self):
        result = audit_backlog(
            backlog(),
            {"QLT-001": entry(), "QLT-002": entry("BLOCKED")},
        )
        self.assertEqual(result["status"], "PASS")

    def test_missing_entry_blocks(self):
        result = audit_backlog(backlog(), {"QLT-001": entry()})
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("LEDGER_ENTRY_MISSING", result["reason_codes"])

    def test_blocked_entry_requires_reason(self):
        blocked = entry("BLOCKED")
        blocked.pop("blocker")
        result = audit_backlog(
            {"issues": [{"id": "QLT-001"}]},
            {"QLT-001": blocked},
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("QLT-001_BLOCKER_MISSING", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
