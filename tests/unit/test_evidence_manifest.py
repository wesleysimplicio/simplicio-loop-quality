import copy
import json
import tempfile
import unittest
from pathlib import Path

from simplicio_loop_quality.contract_validation import validate_contract_document
from simplicio_loop_quality.evidence import (
    ArtifactMissingError,
    ArtifactTamperedError,
    EvidenceBinding,
    EvidenceManifest,
    EvidenceStore,
    ReplayMismatchError,
    RetentionPolicy,
)


class EvidenceManifestTest(unittest.TestCase):
    def setUp(self):
        self.binding = EvidenceBinding(
            source_sha="a" * 40,
            policy_hash="b" * 64,
            tool_name="fixture-runner",
            tool_version="1.2.3",
            command=("fixture-runner", "--token", "secret-value"),
            environment_hash="c" * 64,
            seed=17,
        )

    def test_fixture_validates_as_the_current_manifest_contract(self):
        fixture = Path(__file__).parents[1] / "fixtures" / "evidence-manifest-v1.json"
        value = json.loads(fixture.read_text(encoding="utf-8"))
        self.assertEqual(validate_contract_document(value), [])
        self.assertEqual(EvidenceManifest.from_mapping(value).to_dict(), value)

    def test_sha256_storage_is_immutable_and_verifiable(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(tmp)
            record = store.put(b"hello", binding=self.binding)
            self.assertEqual(record.sha256, "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")
            self.assertEqual(Path(tmp, record.ref).read_bytes(), b"hello")
            manifest = store.build_manifest([record])
            self.assertEqual(store.verify(manifest).status, "VERIFIED")
            Path(tmp, record.ref).write_bytes(b"tampered")
            self.assertEqual(store.verify(manifest).status, "TAMPERED")
            with self.assertRaises(ArtifactTamperedError):
                store.replay(manifest, lambda _provenance: b"hello")

    def test_identical_content_is_deduplicated_without_losing_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(tmp)
            first = store.put(b"same", binding=self.binding)
            second_binding = EvidenceBinding(
                source_sha="d" * 40,
                policy_hash="e" * 64,
                tool_name="other-runner",
                tool_version="9.0",
                command=("other-runner",),
                environment_hash="f" * 64,
                seed=None,
            )
            second = store.put(b"same", binding=second_binding)
            self.assertEqual(first.ref, second.ref)
            manifest = store.build_manifest([second, first, first])
            self.assertEqual(len(manifest.artifacts), 1)
            self.assertEqual(len(manifest.artifacts[0]["provenance"]), 2)
            self.assertEqual(manifest, store.build_manifest([first, second]))

    def test_secrets_are_redacted_before_manifest_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(tmp)
            record = store.put(
                b"output",
                binding=self.binding,
                metadata={"api_key": "do-not-persist", "note": "Authorization: Bearer do-not-persist"},
            )
            manifest = store.build_manifest([record])
            path = store.write_manifest(manifest)
            serialized = path.read_text(encoding="utf-8")
            self.assertNotIn("secret-value", serialized)
            self.assertNotIn("do-not-persist", serialized)
            self.assertIn("[REDACTED]", serialized)

    def test_missing_artifact_blocks_verification_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(tmp)
            record = store.put(b"missing", binding=self.binding)
            manifest = store.build_manifest([record])
            Path(tmp, record.ref).unlink()
            result = store.verify(manifest)
            self.assertEqual(result.status, "MISSING")
            self.assertIn("artifact_missing", result.findings[0])
            with self.assertRaises(ArtifactMissingError):
                store.replay(manifest, lambda _provenance: b"missing")

    def test_manifest_only_retention_is_explicitly_not_replayable(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(tmp)
            record = store.put(b"retained", binding=self.binding)
            manifest = store.build_manifest(
                [record], retention=RetentionPolicy(mode="manifest_only", retain_until="2026-01-01T00:00:00Z")
            )
            Path(tmp, record.ref).unlink()
            result = store.verify(manifest)
            self.assertEqual(result.status, "MISSING")
            self.assertIn("artifact_not_retained", result.findings[0])

    def test_replay_requires_the_same_artifact_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(tmp)
            record = store.put(b"replay-me", binding=self.binding)
            manifest = store.build_manifest([record])
            result = store.replay(manifest, lambda _provenance: b"replay-me")
            self.assertEqual(result.status, "REPLAYED")
            with self.assertRaises(ReplayMismatchError):
                store.replay(manifest, lambda _provenance: b"different")

    def test_manifest_tampering_is_rejected_before_artifact_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(tmp)
            record = store.put(b"content", binding=self.binding)
            manifest = store.build_manifest([record])
            tampered = manifest.to_dict()
            tampered["artifacts"][0]["size"] += 1
            result = store.verify(tampered)
            self.assertEqual(result.status, "INVALID")

    def test_manifest_order_and_redaction_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvidenceStore(tmp)
            first = store.put(b"a", binding=self.binding, metadata={"secret": "x"})
            second = store.put(b"b", binding=self.binding)
            left = store.build_manifest([second, first])
            right = store.build_manifest([first, second])
            self.assertEqual(left.to_dict(), right.to_dict())
            self.assertEqual(left.to_dict(), json.loads(json.dumps(left.to_dict(), sort_keys=True)))
