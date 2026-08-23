import unittest

from simplicio_loop_quality.contract_quality import compare_contracts, validate_contract


class ContractQualityTest(unittest.TestCase):
    def setUp(self):
        self.document = {
            "schema": "simplicio.quality-stage-result/v1", "identity": {"source_sha": "a", "policy_hash": "p"},
            "stage_id": "stage-1", "lane": "contract", "status": "PASS", "evidence": ["ev-1"],
        }

    def test_valid_contract_passes(self):
        self.assertEqual(validate_contract(self.document, expected_source_sha="a", expected_policy_hash="p").status, "PASS")

    def test_missing_stale_and_pass_without_evidence_fail(self):
        invalid = {"status": "PASS", "identity": {"source_sha": "old", "policy_hash": "old"}}
        result = validate_contract(invalid, expected_source_sha="new", expected_policy_hash="new")
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(result.findings)

    def test_conflicting_same_stage_documents_are_detected(self):
        conflict = {**self.document, "status": "FAIL", "evidence": []}
        self.assertEqual(compare_contracts([self.document, conflict])[0].code, "CONTRADICTION")


if __name__ == "__main__":
    unittest.main()
