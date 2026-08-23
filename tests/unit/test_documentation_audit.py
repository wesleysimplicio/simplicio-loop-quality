import tempfile
import unittest
from pathlib import Path

from scripts.check_docs import check_docs


class DocumentationAuditTest(unittest.TestCase):
    def test_repository_docs_have_required_contract_markers(self):
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(check_docs(root), [])

    def test_missing_document_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            self.assertTrue(check_docs(root))


if __name__ == "__main__":
    unittest.main()
