import unittest

from simplicio_loop_quality.privacy import scan_privacy


class PrivacyTest(unittest.TestCase):
    def test_classified_data_with_retention_and_consent_passes(self):
        result = scan_privacy(
            [
                {
                    "path": "db/users",
                    "category": "pii",
                    "classification": "restricted",
                    "retention": "30d",
                    "consent": True,
                }
            ]
        )
        self.assertEqual(result["status"], "PASS")

    def test_unclassified_sensitive_data_blocks(self):
        result = scan_privacy([{"path": "logs/app", "category": "secret"}])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("DATA_CLASSIFICATION_MISSING", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
