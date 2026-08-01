import unittest
from argparse import Namespace
from unittest import mock

from simplicio_loop.extension_handshake import ExtensionHandshakeError

from simplicio_loop_quality import cli


class LoopCapabilitiesTest(unittest.TestCase):
    def test_blocked_negotiation_prevents_task_write_and_loop_invocation(self):
        args = Namespace(
            global_policy="",
            project_policy="",
            policy="",
            repo=".",
            issue="",
            out="",
            delivery="verified",
            max_iterations=1,
        )
        with (
            mock.patch.object(
                cli,
                "_loop_capabilities",
                return_value={"ready": False, "reason_code": "CORE_VERSION_FUTURE_UNKNOWN"},
            ),
            mock.patch.object(cli, "_write_task") as write_task,
            mock.patch.object(cli, "LoopInvoker") as invoker,
        ):
            self.assertEqual(cli.cmd_run(args), 3)
        write_task.assert_not_called()
        invoker.assert_not_called()

    def test_unregistered_provider_is_explicitly_blocked(self):
        error = ExtensionHandshakeError("PROVIDER_UNREGISTERED", "not registered")
        with mock.patch(
            "simplicio_loop.extension_handshake.extension_handshake", side_effect=error
        ):
            result = cli._loop_capabilities()
        self.assertFalse(result["ready"])
        self.assertFalse(result["quality_provider_hook"])
        self.assertEqual(result["provider_reason_code"], "PROVIDER_UNREGISTERED")

    def test_malformed_core_handshake_never_advertises_terminal_authority(self):
        provider = {
            "schema": "simplicio.extension-handshake/v1",
            "status": "PASS",
            "provider": {"id": "simplicio_loop_quality", "policy": "strict-default"},
            "runtime": {"fingerprint": "sha256:" + "a" * 64},
        }
        with (
            mock.patch("simplicio_loop.extension_manifest.extension_handshake", return_value={}),
            mock.patch(
                "simplicio_loop.extension_handshake.extension_handshake", return_value=provider
            ),
        ):
            result = cli._loop_capabilities()
        self.assertFalse(result["ready"])
        self.assertFalse(result["extension_handshake"])
        self.assertFalse(result["completion_oracle"])
        self.assertFalse(result["terminal_run_outcome"])

    def test_provider_without_runtime_fingerprint_is_not_ready(self):
        provider = {
            "schema": "simplicio.extension-handshake/v1",
            "status": "PASS",
            "provider": {"id": "simplicio_loop_quality", "policy": "strict-default"},
            "runtime": {},
        }
        with mock.patch(
            "simplicio_loop.extension_handshake.extension_handshake", return_value=provider
        ):
            result = cli._loop_capabilities()
        self.assertFalse(result["ready"])
        self.assertIn("RUNTIME_FINGERPRINT_MISSING", result["reason_codes"])

    def test_distribution_and_loaded_module_version_mismatch_blocks(self):
        with (
            mock.patch.object(cli.metadata, "version", return_value="3.38.26"),
            mock.patch("simplicio_loop.__version__", "3.38.27"),
        ):
            result = cli._loop_capabilities()
        self.assertFalse(result["ready"])
        self.assertEqual(result["module_version"], "3.38.27")
        self.assertEqual(result["distribution_version"], "3.38.26")
        self.assertIn("CORE_VERSION_METADATA_MISMATCH", result["reason_codes"])
