"""Thin process boundary that starts exactly one authoritative simplicio-loop run."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


class LoopUnavailable(RuntimeError):
    """The authoritative Loop entrypoint is not installed."""


@dataclass(frozen=True)
class LoopCommand:
    argv: tuple[str, ...]
    cwd: str


Executor = Callable[..., subprocess.CompletedProcess[str]]


class LoopInvoker:
    """Build and execute the single allowed orchestration command.

    Test tools are never launched here.  The only subprocess started by this
    package is the core Loop process itself; all quality commands then flow through
    the Loop Hub.
    """

    def __init__(self, prefix: Sequence[str] | None = None) -> None:
        self._prefix = tuple(prefix) if prefix else self._discover_prefix()

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
        quality_policy_hash: str,
    ) -> LoopCommand:
        repo = Path(repository).resolve()
        task = Path(task_path).resolve()
        if max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        if delivery != "verified":
            raise ValueError("quality-only runs require delivery='verified'")
        if not quality_provider.strip() or not quality_policy.strip():
            raise ValueError("quality provider and policy IDs are required")
        if len(quality_policy_hash) != 64 or any(
            character not in "0123456789abcdefABCDEF" for character in quality_policy_hash
        ):
            raise ValueError("quality policy hash must be a full SHA-256 digest")
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
            "--quality-policy-hash",
            quality_policy_hash.lower(),
        )
        return LoopCommand(argv=argv, cwd=str(repo))

    def run(
        self,
        command: LoopCommand,
        *,
        executor: Executor = subprocess.run,
    ) -> subprocess.CompletedProcess[str]:
        return executor(
            list(command.argv),
            cwd=command.cwd,
            text=True,
            check=False,
        )
