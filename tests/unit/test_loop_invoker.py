import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from simplicio_loop_quality.loop_invoker import LoopCommand, LoopInvoker, LoopUnavailable


def invoker(prefix=("loop",)):
    return LoopInvoker._for_test(prefix)


def outcome(command, **changes):
    value = {
        "schema": "simplicio.run-outcome/v1",
        "outcome": "COMPLETE",
        "exit_code": 0,
        "source": {"kind": "local", "identity": command.task_path, "digest": ""},
        "oracle": {"verdict": "COMPLETE", "authorized": True},
    }
    value.update(changes)
    return value


class LoopInvokerTest(unittest.TestCase):
    def command(self, tmp, prefix=("loop",)):
        task = Path(tmp) / "task.md"
        task.write_text("task", encoding="utf-8")
        return invoker(prefix).build_command(
            repository=tmp,
            task_path=task,
            max_iterations=7,
            quality_provider="simplicio_loop_quality",
            quality_policy="strict-default",
            handshake_fingerprint="sha256:" + "a" * 64,
        )

    def test_builds_one_authoritative_loop_command_with_fresh_result_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.command(tmp)
            second = self.command(tmp)
        self.assertEqual(first.argv.count("loop"), 1)
        self.assertIn("--result-file", first.argv)
        self.assertIn("--require-handshake-fingerprint", first.argv)
        self.assertNotEqual(first.result_path, second.result_path)
        self.assertFalse(Path(first.result_path).exists())

    def test_rejects_invalid_limits_and_delivery(self):
        kwargs = {
            "quality_provider": "quality",
            "quality_policy": "strict",
            "handshake_fingerprint": "sha256:" + "a" * 64,
        }
        with self.assertRaises(ValueError):
            invoker().build_command(repository=".", task_path="task.md", max_iterations=0, **kwargs)
        with self.assertRaises(ValueError):
            invoker().build_command(
                repository=".", task_path="task.md", delivery="deployed", **kwargs
            )

    def run_with(self, command, payload, code=0):
        def executor(argv, **kwargs):
            Path(command.result_path).write_text(json.dumps(payload), encoding="utf-8")
            return subprocess.CompletedProcess(argv, code)

        return invoker().run(command, executor=executor)

    def test_executor_requires_oracle_authorized_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = self.command(tmp)
            self.assertEqual(self.run_with(command, outcome(command)).returncode, 0)

    def test_stale_result_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = self.command(tmp)
            Path(command.result_path).write_text(json.dumps(outcome(command)), encoding="utf-8")
            executor = mock.Mock()
            with self.assertRaises(LoopUnavailable):
                invoker().run(command, executor=executor)
            executor.assert_not_called()

    def test_source_mismatch_and_unauthorized_zero_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = self.command(tmp)
            wrong = outcome(command, source={"kind": "local", "identity": "other"})
            with self.assertRaises(LoopUnavailable):
                self.run_with(command, wrong)
            command = self.command(tmp)
            denied = outcome(command, oracle={"verdict": "UNAVAILABLE", "authorized": False})
            with self.assertRaises(LoopUnavailable):
                self.run_with(command, denied)

    @mock.patch(
        "simplicio_loop_quality.loop_invoker.importlib.util.find_spec", return_value=object()
    )
    def test_discovery_prefers_inspected_python(self, _find_spec):
        self.assertEqual(
            LoopInvoker._discover_prefix(), (sys.executable, "-m", "simplicio_loop.cli")
        )

    def test_rejects_noncanonical_command_prefix(self):
        command = LoopCommand(("other", "run"), ".", "outcome.json", "task.md")
        with self.assertRaises(LoopUnavailable):
            invoker().run(command)
