import subprocess
import sys
import unittest
from unittest import mock

from simplicio_loop_quality.loop_invoker import LoopCommand, LoopInvoker, LoopUnavailable
from simplicio_loop_quality.policy import load_strict_policy


class LoopInvokerTest(unittest.TestCase):
    def test_builds_one_authoritative_loop_command(self):
        invoker = LoopInvoker(prefix=("simplicio-loop",))
        policy = load_strict_policy()
        command = invoker.build_command(
            repository=".",
            task_path="task.md",
            max_iterations=7,
            quality_provider="simplicio_loop_quality",
            quality_policy=policy.policy_id,
            quality_policy_hash=policy.canonical_hash,
        )
        self.assertEqual(command.argv.count("simplicio-loop"), 1)
        self.assertIn("--quality-provider", command.argv)
        self.assertIn("simplicio_loop_quality", command.argv)
        self.assertIn("--quality-policy", command.argv)
        self.assertIn("strict-default", command.argv)
        self.assertEqual(command.argv[-1], policy.canonical_hash)

    def test_rejects_invalid_limits_and_delivery(self):
        invoker = LoopInvoker(prefix=("loop",))
        kwargs = {
            "quality_provider": "simplicio_loop_quality",
            "quality_policy": "strict-default",
            "quality_policy_hash": "a" * 64,
        }
        with self.assertRaises(ValueError):
            invoker.build_command(
                repository=".", task_path="task.md", max_iterations=0, **kwargs
            )
        with self.assertRaises(ValueError):
            invoker.build_command(
                repository=".", task_path="task.md", delivery="deployed", **kwargs
            )
        for field, value in (
            ("quality_provider", ""),
            ("quality_policy", ""),
            ("quality_policy_hash", "short"),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                invalid = {**kwargs, field: value}
                invoker.build_command(repository=".", task_path="task.md", **invalid)

    def test_executor_is_injected_and_receives_no_shell(self):
        calls = []

        def fake_executor(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0)

        command = LoopCommand(("simplicio-loop", "run"), "/tmp")
        result = LoopInvoker(prefix=("simplicio-loop",)).run(command, executor=fake_executor)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls[0][0], ["simplicio-loop", "run"])
        self.assertNotIn("shell", calls[0][1])
        self.assertFalse(calls[0][1]["check"])

    @mock.patch("simplicio_loop_quality.loop_invoker.shutil.which", return_value="/other/loop")
    @mock.patch(
        "simplicio_loop_quality.loop_invoker.importlib.util.find_spec",
        return_value=object(),
    )
    def test_discovery_prefers_the_inspected_python_runtime(self, _find_spec, _which):
        self.assertEqual(
            LoopInvoker._discover_prefix(),
            (sys.executable, "-m", "simplicio_loop.cli"),
        )

    @mock.patch(
        "simplicio_loop_quality.loop_invoker.importlib.util.find_spec",
        return_value=None,
    )
    @mock.patch("simplicio_loop_quality.loop_invoker.shutil.which", return_value="/bin/loop")
    def test_discovery_can_use_a_standalone_binary(self, _which, _find_spec):
        self.assertEqual(LoopInvoker._discover_prefix(), ("/bin/loop",))

    @mock.patch(
        "simplicio_loop_quality.loop_invoker.importlib.util.find_spec",
        return_value=None,
    )
    @mock.patch("simplicio_loop_quality.loop_invoker.shutil.which", return_value=None)
    def test_discovery_fails_closed_when_loop_is_absent(self, _which, _find_spec):
        with self.assertRaises(LoopUnavailable):
            LoopInvoker._discover_prefix()
