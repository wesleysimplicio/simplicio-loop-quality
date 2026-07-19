import json
import unittest
from importlib import resources
from pathlib import Path


class ExtensionManifestTest(unittest.TestCase):
    def test_source_and_packaged_manifests_are_identical(self):
        source = json.loads(Path("simplicio-loop-extension.json").read_text(encoding="utf-8"))
        packaged = json.loads(
            resources.files("simplicio_loop_quality.contracts")
            .joinpath("loop-extension.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(source, packaged)
        self.assertEqual(source["domain"], "quality")
        self.assertFalse(
            {"scheduler", "queue", "worktree_manager", "process_supervisor"}
            & set(source)
        )

    def test_manifest_conforms_to_installed_loop_contract_when_available(self):
        try:
            from simplicio_loop.extension_manifest import validate_manifest
        except ImportError:
            self.skipTest("simplicio-loop package is not installed in this local bootstrap")
        manifest = json.loads(Path("simplicio-loop-extension.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_manifest(manifest), [])

    def test_advertised_quality_contracts_are_packaged(self):
        contract_dir = resources.files("simplicio_loop_quality.contracts")
        filenames = {
            "quality-plan-v1.schema.json",
            "quality-evidence-v1.schema.json",
            "quality-gate-verdict-v1.schema.json",
        }
        schema_ids = {
            json.loads(contract_dir.joinpath(name).read_text(encoding="utf-8"))["$id"]
            for name in filenames
        }
        self.assertEqual(
            schema_ids,
            {
                "simplicio.quality-plan/v1",
                "simplicio.quality-evidence/v1",
                "simplicio.quality-gate-verdict/v1",
            },
        )
