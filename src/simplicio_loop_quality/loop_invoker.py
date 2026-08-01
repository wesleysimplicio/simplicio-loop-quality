"""Thin process boundary that starts exactly one authoritative simplicio-loop run."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


class LoopUnavailable(RuntimeError):
    """The authoritative Loop entrypoint or outcome is unavailable."""


@dataclass(frozen=True)
class LoopCommand:
    argv: tuple[str, ...]
    cwd: str
    result_path: str
    task_path: str


Executor = Callable[..., subprocess.CompletedProcess[str]]


class LoopInvoker:
    """Start one core Loop process and consume only its Oracle-bound outcome."""

    def __init__(self) -> None:
        self._prefix = self._discover_prefix()

    @classmethod
    def _for_test(cls, prefix: Sequence[str]) -> LoopInvoker:
        instance = object.__new__(cls)
        instance._prefix = tuple(prefix)
        return instance

    @staticmethod
    def _discover_prefix() -> tuple[str, ...]:
        if importlib.util.find_spec("simplicio_loop.cli") is not None:
            return (sys.executable, "-m", "simplicio_loop.cli")
        binary = shutil.which("simplicio-loop")
        if binary:
            return (binary,)
        raise LoopUnavailable(
            "simplicio-loop is unavailable; strict mode forbids a local execution fallback"
        )

    def build_command(
        self,
        *,
        repository: str | Path,
        task_path: str | Path,
        delivery: str = "verified",
        max_iterations: int = 20,
        quality_provider: str,
        quality_policy: str,
        handshake_fingerprint: str,
    ) -> LoopCommand:
        repo = Path(repository).resolve()
        task = Path(task_path).resolve()
        result = (
            Path(tempfile.mkdtemp(prefix="simplicio-loop-quality-outcome-")) / "run-outcome.json"
        )
        if max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        if delivery != "verified":
            raise ValueError("quality-only runs require delivery='verified'")
        if not quality_provider.strip() or not quality_policy.strip():
            raise ValueError("quality provider and policy IDs are required")
        if (
            not isinstance(handshake_fingerprint, str)
            or not handshake_fingerprint.startswith("sha256:")
            or len(handshake_fingerprint) != 71
            or any(
                character not in "0123456789abcdefABCDEF" for character in handshake_fingerprint[7:]
            )
        ):
            raise ValueError("a full runtime handshake fingerprint is required")
        argv = self._prefix + (
            "run",
            "--task",
            str(task),
            "--repo",
            str(repo),
            "--delivery",
            delivery,
            "--max-iterations",
            str(max_iterations),
            "--quality-provider",
            quality_provider,
            "--quality-policy",
            quality_policy,
            "--require-handshake-fingerprint",
            handshake_fingerprint,
            "--result-file",
            str(result),
        )
        return LoopCommand(tuple(argv), str(repo), str(result), str(task))

    @staticmethod
    def _validate_outcome(
        completed: subprocess.CompletedProcess[str], command: LoopCommand
    ) -> None:
        try:
            outcome = json.loads(Path(command.result_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise LoopUnavailable("Loop did not produce a valid run-outcome artifact") from exc
        if not isinstance(outcome, Mapping):
            raise LoopUnavailable("Loop run-outcome must be an object")
        code = outcome.get("exit_code")
        expected_codes = {
            "COMPLETE": 0,
            "BLOCKED": 20,
            "CANCELLED": 21,
            "PARTIAL": 22,
            "INVALID_RECEIPT": 23,
            "INFRASTRUCTURE_FAILURE": 24,
        }
        source = outcome.get("source")
        if (
            outcome.get("schema") != "simplicio.run-outcome/v1"
            or not isinstance(code, int)
            or isinstance(code, bool)
            or expected_codes.get(outcome.get("outcome")) != code
            or code != completed.returncode
            or not isinstance(source, Mapping)
            or source.get("identity") != command.task_path
        ):
            raise LoopUnavailable("Loop run-outcome is not bound to this process and task")
        if code == 0 and outcome.get("oracle") != {"verdict": "COMPLETE", "authorized": True}:
            raise LoopUnavailable("Loop exit 0 was not authorized by the Completion Oracle")

    def run(
        self, command: LoopCommand, *, executor: Executor = subprocess.run
    ) -> subprocess.CompletedProcess[str]:
        action_index = len(self._prefix)
        if (
            tuple(command.argv[:action_index]) != self._prefix
            or len(command.argv) <= action_index
            or command.argv[action_index] != "run"
        ):
            raise LoopUnavailable("command does not use the canonical Loop run entrypoint")
        if Path(command.result_path).exists():
            raise LoopUnavailable("Loop result path must be fresh for this invocation")
        completed = executor(list(command.argv), cwd=command.cwd, text=True, check=False)
        self._validate_outcome(completed, command)
        return completed
