"""Commands and result normalization for a clean install smoke test."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = "simplicio.quality-install-smoke/v1"


@dataclass(frozen=True)
class InstallSmokePlan:
    python: str
    commands: tuple[tuple[str, ...], ...]
    working_directory: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "python": self.python, "commands": [list(x) for x in self.commands], "working_directory": self.working_directory}


def build_install_smoke_plan(repository: str | Path, *, python: str = "python") -> InstallSmokePlan:
    root = str(Path(repository).resolve())
    commands = (
        (python, "-m", "venv", ".quality-smoke-venv"),
        (".quality-smoke-venv/bin/python", "-m", "pip", "install", "--no-cache-dir", "."),
        (".quality-smoke-venv/bin/python", "-m", "simplicio_loop_quality", "--help"),
    )
    return InstallSmokePlan(python, commands, root)


def normalize_install_smoke(*, return_code: int, stdout: str, stderr: str) -> dict[str, Any]:
    status = "PASS" if return_code == 0 else "FAIL"
    return {"schema": SCHEMA, "status": status, "return_code": return_code, "stdout": stdout, "stderr": stderr, "reason_codes": [] if status == "PASS" else ["CLEAN_INSTALL_SMOKE_FAILED"]}


__all__ = ["InstallSmokePlan", "SCHEMA", "build_install_smoke_plan", "normalize_install_smoke"]
