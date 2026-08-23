"""Declarative generic command/container profile validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping

SCHEMA = "simplicio.quality-generic-profile/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class GenericCommand:
    command_id: str
    lane: str
    command: tuple[str, ...]
    parser: str
    artifacts: tuple[str, ...]
    env_allowlist: tuple[str, ...]


@dataclass(frozen=True)
class GenericProfileResult:
    status: str
    commands: tuple[GenericCommand, ...]
    findings: tuple[str, ...]
    profile_id: str


def _safe_path(value: str) -> bool:
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts


def validate_profile(profile: Mapping[str, Any]) -> GenericProfileResult:
    findings: list[str] = []
    commands: list[GenericCommand] = []
    raw_commands = profile.get("commands", ())
    if not isinstance(raw_commands, list) or not raw_commands:
        findings.append("COMMANDS_MISSING")
    for index, raw in enumerate(raw_commands if isinstance(raw_commands, list) else ()):
        if not isinstance(raw, Mapping):
            findings.append(f"COMMAND_{index}_INVALID")
            continue
        command = raw.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg for arg in command):
            findings.append(f"COMMAND_{index}_INVALID")
            continue
        artifacts = tuple(str(path) for path in raw.get("artifacts", ()))
        if any(not _safe_path(path) for path in artifacts):
            findings.append(f"COMMAND_{index}_ARTIFACT_PATH_UNSAFE")
        env = tuple(str(name) for name in raw.get("env_allowlist", ()))
        if any(not name.isidentifier() for name in env):
            findings.append(f"COMMAND_{index}_ENV_INVALID")
        commands.append(GenericCommand(str(raw.get("id", f"command-{index}")), str(raw.get("lane", "generic")), tuple(command), str(raw.get("parser", "text")), artifacts, env))
    if profile.get("container") is not None:
        container = profile.get("container")
        if not isinstance(container, Mapping) or not str(container.get("image", "")).strip():
            findings.append("CONTAINER_INVALID")
    status = "PASS" if commands and not findings else "BLOCKED"
    payload = {"schema": SCHEMA, "profile": profile, "findings": sorted(findings)}
    return GenericProfileResult(status, tuple(sorted(commands, key=lambda item: item.command_id)), tuple(sorted(findings)), _hash(payload))


def onboarding_profile(*, commands: list[Mapping[str, Any]], container_image: str | None = None) -> dict[str, Any]:
    profile: dict[str, Any] = {"schema": SCHEMA, "commands": [dict(command) for command in commands]}
    if container_image:
        profile["container"] = {"image": container_image, "network": "none"}
    return profile


class GenericQualityProfile:
    def validate(self, profile: Mapping[str, Any]) -> GenericProfileResult:
        return validate_profile(profile)


__all__ = ["GenericCommand", "GenericProfileResult", "GenericQualityProfile", "SCHEMA", "onboarding_profile", "validate_profile"]
