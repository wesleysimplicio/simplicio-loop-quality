import unittest
from unittest import mock

from simplicio_loop.extension_handshake import ExtensionHandshakeError

from simplicio_loop_quality import cli


class LoopCapabilitiesTest(unittest.TestCase):
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
        self.assertIn("runtime_fingerprint", result["reason_code"])
