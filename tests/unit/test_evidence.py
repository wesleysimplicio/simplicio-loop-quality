import json
import tempfile
import unittest
from pathlib import Path

from simplicio_loop_quality.evidence import canonical_json, evidence_hash, write_json_atomic


class EvidenceTest(unittest.TestCase):
    def test_hash_is_order_independent(self):
        left = {"b": 2, "a": 1}
        right = {"a": 1, "b": 2}
        self.assertEqual(canonical_json(left), canonical_json(right))
        self.assertEqual(evidence_hash(left), evidence_hash(right))

    def test_atomic_writer_creates_valid_json_and_no_temp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "receipt.json"
            result = write_json_atomic(target, {"ok": True})
            self.assertEqual(result, target)
            self.assertEqual(json.loads(target.read_text()), {"ok": True})
            self.assertEqual(list(target.parent.glob("*.tmp")), [])
