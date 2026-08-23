"""Deterministic repository and changed-surface impact analysis.

The Loop owns execution and change-set acquisition.  This module only consumes
an explicit change set (or Loop-provided name-status text) and reads repository
metadata.  It deliberately does not invoke git, a build tool, a mapper, or any
other process.  Missing inputs are represented as unknowns in the returned
impact map instead of being guessed.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal


IMPACT_SCHEMA = "simplicio.quality-impact/v1"
Freshness = Literal["fresh", "stale", "invalid", "missing", "unknown"]
ChangeStatus = Literal["added", "copied", "modified", "deleted", "renamed", "unknown"]

_LANGUAGE_BY_SUFFIX = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".cs": "C#",
    ".fs": "F#",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hh": "C++",
    ".h": "C/C++",
    ".c": "C",
    ".swift": "Swift",
    ".rb": "Ruby",
    ".php": "PHP",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hrl": "Erlang",
    ".scala": "Scala",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".sql": "SQL",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".dart": "Dart",
    ".r": "R",
    ".lua": "Lua",
}

_BUILD_MARKERS: dict[str, str] = {
    "pyproject.toml": "Python packaging",
    "setup.py": "Python packaging",
    "setup.cfg": "Python packaging",
    "requirements.txt": "Python requirements",
    "poetry.lock": "Poetry",
    "Cargo.toml": "Cargo",
    "Cargo.lock": "Cargo",
    "package.json": "Node.js package",
    "pnpm-workspace.yaml": "pnpm workspace",
    "yarn.lock": "Yarn",
    "package-lock.json": "npm",
    "bun.lock": "Bun",
    "go.mod": "Go modules",
    "go.work": "Go workspace",
    "pom.xml": "Maven",
    "build.gradle": "Gradle",
    "build.gradle.kts": "Gradle Kotlin",
    "settings.gradle": "Gradle",
    "settings.gradle.kts": "Gradle Kotlin",
    "Gemfile": "Bundler",
    "composer.json": "Composer",
    "mix.exs": "Mix",
    "Package.swift": "Swift Package Manager",
    "CMakeLists.txt": "CMake",
    "Makefile": "Make",
    "meson.build": "Meson",
    "Dockerfile": "Docker",
}

_TEST_MARKERS = {
    "pytest.ini": "pytest",
    "tox.ini": "tox",
    "noxfile.py": "nox",
    "jest.config.js": "Jest",
    "jest.config.ts": "Jest",
    "vitest.config.ts": "Vitest",
    "playwright.config.ts": "Playwright",
    "cypress.config.ts": "Cypress",
    "karma.conf.js": "Karma",
    "phpunit.xml": "PHPUnit",
    "Makefile": "Make test target (configuration requires inspection)",
}

_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "vendor",
        "target",
        "dist",
        "build",
        "coverage",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)

_GENERATED_DIRS = frozenset({"generated", "gen", "_generated", "dist", "build", "target"})
_GENERATED_NAME_RE = re.compile(
    r"(?:^|[._-])(?:generated|designer|autogen|g|gen)(?:[._-]|$)|(?:\.min|\.bundle)\.",
    re.IGNORECASE,
)
_GENERATED_TEXT_RE = re.compile(
    r"(?:do not edit|do not modify|generated (?:file|by)|auto[- ]generated|code generated)",
    re.IGNORECASE,
)

_IMPORT_RE = re.compile(
    r"(?:\bfrom\s+([.A-Za-z_][\w.]*)\s+import|\bimport\s+([.A-Za-z_][\w.]*)|"
    r"\b(?:from|import|require)\s*\(??\s*[\"']([^\"']+)[\"']\s*\)?|"
    r"\buse\s+crate::([A-Za-z_][\w:]*)|^\s*mod\s+([A-Za-z_][\w]*)\s*;)",
    re.MULTILINE,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _json_value(value: Any) -> Any:
    """Convert dataclass output to stable JSON-compatible values."""

    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _relpath(root: Path, path: str | Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"path is outside repository: {path}") from exc
    normalized = PurePosixPath(candidate.as_posix())
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError(f"path escapes repository: {path}")
    if str(normalized) in {"", "."}:
        raise ValueError("path must identify a file")
    return normalized.as_posix()


def _confidence(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


@dataclass(frozen=True)
class Signal:
    """A detected fact with its evidence and confidence."""

    name: str
    evidence: tuple[str, ...] = ()
    confidence: float = 0.0
    scope: str = "."

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True)
class UnknownFact:
    """An unavailable or ambiguous fact; unknown is never treated as empty."""

    kind: str
    reason_code: str
    detail: str
    scope: str = "."

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: ChangeStatus = "modified"
    old_path: str | None = None
    generated: bool | None = None
    generated_reason: str | None = None
    component: str = "."

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True)
class ProjectMapStatus:
    path: str | None
    available: bool
    freshness: Freshness
    generated_at: str | None = None
    source_sha: str | None = None
    age_seconds: float | None = None
    reason_code: str | None = None
    used_for: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True)
class ComponentBoundary:
    id: str
    root: str
    manifests: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    build_systems: tuple[str, ...] = ()
    file_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True)
class RepositoryProfile:
    languages: tuple[Signal, ...] = ()
    build_systems: tuple[Signal, ...] = ()
    public_apis: tuple[Signal, ...] = ()
    test_infrastructure: tuple[Signal, ...] = ()
    components: tuple[ComponentBoundary, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "languages": [item.to_dict() for item in self.languages],
            "build_systems": [item.to_dict() for item in self.build_systems],
            "public_apis": [item.to_dict() for item in self.public_apis],
            "test_infrastructure": [item.to_dict() for item in self.test_infrastructure],
            "components": [item.to_dict() for item in self.components],
        }


@dataclass(frozen=True)
class RiskSurface:
    kind: str
    paths: tuple[str, ...]
    score: float
    reasons: tuple[str, ...] = ()
    component: str = "."

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True)
class ImpactMap:
    repository: str
    profile: RepositoryProfile
    project_map: ProjectMapStatus
    changed_files: tuple[ChangedFile, ...]
    dependencies: dict[str, tuple[str, ...]]
    reverse_dependents: dict[str, tuple[str, ...]]
    impacted_files: tuple[str, ...]
    risk_surfaces: tuple[RiskSurface, ...]
    unknowns: tuple[UnknownFact, ...]
    confidence: float
    schema: str = IMPACT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "repository": self.repository,
            "profile": self.profile.to_dict(),
            "project_map": self.project_map.to_dict(),
            "changed_files": [item.to_dict() for item in self.changed_files],
            "dependencies": {key: list(value) for key, value in sorted(self.dependencies.items())},
            "reverse_dependents": {
                key: list(value) for key, value in sorted(self.reverse_dependents.items())
            },
            "impacted_files": list(self.impacted_files),
            "risk_surfaces": [item.to_dict() for item in self.risk_surfaces],
            "unknowns": [item.to_dict() for item in self.unknowns],
            "confidence": self.confidence,
        }

    def json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


class ImpactAnalysisError(ValueError):
    """Raised when an explicit analysis input is malformed."""


def parse_changed_files(
    value: str | bytes | Iterable[ChangedFile | Mapping[str, Any] | str],
    *,
    root: str | Path = ".",
) -> tuple[ChangedFile, ...]:
    """Normalize Loop change metadata or git ``--name-status`` output.

    ``git diff --name-status`` and its NUL-delimited variant are accepted as
    data.  The function does not execute git.  A plain path means ``modified``.
    """

    repository = Path(root).resolve()
    if isinstance(value, bytes):
        return _parse_nul_name_status(value.decode("utf-8", errors="replace"), repository)
    if isinstance(value, str):
        if "\x00" in value:
            return _parse_nul_name_status(value, repository)
        return _parse_name_status(value, repository)

    result: list[ChangedFile] = []
    for item in value:
        if isinstance(item, ChangedFile):
            path = _relpath(repository, item.path)
            old = _relpath(repository, item.old_path) if item.old_path else None
            result.append(
                ChangedFile(path, item.status, old, item.generated, item.generated_reason, item.component)
            )
            continue
        if isinstance(item, str):
            result.append(ChangedFile(_relpath(repository, item)))
            continue
        if not isinstance(item, Mapping):
            raise ImpactAnalysisError(f"unsupported changed-file entry: {type(item).__name__}")
        status = str(item.get("status", "modified")).lower()
        status = {"m": "modified", "a": "added", "d": "deleted", "r": "renamed"}.get(
            status[:1], status
        )
        if status not in {"added", "copied", "modified", "deleted", "renamed", "unknown"}:
            status = "unknown"
        raw_path = item.get("path", item.get("new_path", item.get("new")))
        if not isinstance(raw_path, (str, Path)):
            raise ImpactAnalysisError("changed-file entry requires path or new_path")
        raw_old = item.get("old_path", item.get("old"))
        old_path = _relpath(repository, raw_old) if raw_old else None
        result.append(
            ChangedFile(
                _relpath(repository, raw_path),
                status,  # type: ignore[arg-type]
                old_path,
                item.get("generated") if isinstance(item.get("generated"), bool) else None,
                str(item["generated_reason"]) if item.get("generated_reason") else None,
                str(item.get("component", ".")),
            )
        )
    return _deduplicate_changed(result)


def _parse_name_status(text: str, root: Path) -> tuple[ChangedFile, ...]:
    result: list[ChangedFile] = []
    for raw_line in text.splitlines():
        line = raw_line.strip("\r")
        if not line.strip():
            continue
        parts = line.split("\t")
        code = parts[0].strip()
        letter = code[:1].upper()
        if letter in {"R", "C"} and len(parts) >= 3:
            result.append(
                ChangedFile(
                    _relpath(root, parts[2]),
                    "renamed" if letter == "R" else "copied",
                    _relpath(root, parts[1]),
                )
            )
        elif letter in {"A", "D", "M"} and len(parts) >= 2:
            result.append(
                ChangedFile(
                    _relpath(root, parts[1]),
                    {"A": "added", "D": "deleted", "M": "modified"}[letter],  # type: ignore[arg-type]
                )
            )
        elif line.startswith("?? "):
            result.append(ChangedFile(_relpath(root, line[3:]), "added"))
        else:
            path = parts[-1].strip()
            if path:
                result.append(ChangedFile(_relpath(root, path), "unknown"))
    return _deduplicate_changed(result)


def _parse_nul_name_status(text: str, root: Path) -> tuple[ChangedFile, ...]:
    """Parse ``git diff --name-status -z`` without losing rename pairs."""

    tokens = [token for token in text.split("\x00") if token]
    result: list[ChangedFile] = []
    index = 0
    while index < len(tokens):
        code = tokens[index].strip()
        letter = code[:1].upper()
        if letter in {"R", "C"} and index + 2 < len(tokens):
            result.append(
                ChangedFile(
                    _relpath(root, tokens[index + 2]),
                    "renamed" if letter == "R" else "copied",
                    _relpath(root, tokens[index + 1]),
                )
            )
            index += 3
        elif letter in {"A", "D", "M"} and index + 1 < len(tokens):
            result.append(
                ChangedFile(
                    _relpath(root, tokens[index + 1]),
                    {"A": "added", "D": "deleted", "M": "modified"}[letter],  # type: ignore[arg-type]
                )
            )
            index += 2
        else:
            result.append(ChangedFile(_relpath(root, tokens[index]), "unknown"))
            index += 1
    return _deduplicate_changed(result)


def _deduplicate_changed(items: Iterable[ChangedFile]) -> tuple[ChangedFile, ...]:
    unique: dict[tuple[str, str, str | None], ChangedFile] = {}
    for item in items:
        unique[(item.path, item.status, item.old_path)] = item
    return tuple(unique[key] for key in sorted(unique))


def _iter_files(root: Path) -> tuple[str, ...]:
    files: list[str] = []
    try:
        candidates = root.rglob("*")
    except OSError:
        return ()
    for candidate in candidates:
        if not candidate.is_file() or candidate.is_symlink():
            continue
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            continue
        if any(part in _IGNORED_DIRS for part in relative.parts):
            continue
        files.append(relative.as_posix())
    return tuple(sorted(files))


def _read_text(root: Path, relative: str, limit: int = 512_000) -> str | None:
    try:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            return None
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except (OSError, UnicodeError):
        return None


def _language(path: str) -> str | None:
    name = PurePosixPath(path).name
    suffix = PurePosixPath(path).suffix.lower()
    if name in {"Dockerfile", "Containerfile"}:
        return "Dockerfile"
    return _LANGUAGE_BY_SUFFIX.get(suffix)


def _signal(name: str, evidence: Iterable[str], confidence: float, scope: str = ".") -> Signal:
    return Signal(name, tuple(sorted(set(evidence))), _confidence(confidence), scope)


def _find_project_map(root: Path, requested: str | Path | None) -> Path | None:
    candidates: list[Path] = []
    if requested:
        requested_path = Path(requested)
        candidates.append(requested_path if requested_path.is_absolute() else root / requested_path)
    else:
        candidates.extend(
            root / relative
            for relative in ("project-map.json", ".simplicio/project-map.json", ".mapper/project-map.json")
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _load_project_map(
    root: Path,
    requested: str | Path | None,
    *,
    observed_at: datetime,
    source_sha: str | None,
    max_age: timedelta,
) -> tuple[ProjectMapStatus, dict[str, Any] | None, list[UnknownFact]]:
    path = _find_project_map(root, requested)
    if path is None:
        return (
            ProjectMapStatus(None, False, "missing", reason_code="MAPPER_ABSENT"),
            None,
            [
                UnknownFact(
                    "project_map",
                    "MAPPER_ABSENT",
                    "project-map.json was not supplied or found in the supported locations",
                )
            ],
        )
    relative = path.relative_to(root).as_posix()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return (
            ProjectMapStatus(relative, True, "invalid", reason_code="PROJECT_MAP_INVALID"),
            None,
            [UnknownFact("project_map", "PROJECT_MAP_INVALID", f"could not parse {relative}: {exc}")],
        )
    if not isinstance(payload, dict):
        return (
            ProjectMapStatus(relative, True, "invalid", reason_code="PROJECT_MAP_INVALID"),
            None,
            [UnknownFact("project_map", "PROJECT_MAP_INVALID", f"{relative} must contain a JSON object")],
        )
    generated_at = payload.get("generated_at")
    parsed = _parse_timestamp(generated_at)
    if parsed is None:
        return (
            ProjectMapStatus(
                relative,
                True,
                "invalid",
                generated_at=str(generated_at) if generated_at else None,
                reason_code="PROJECT_MAP_TIMESTAMP_MISSING_OR_INVALID",
            ),
            payload,
            [
                UnknownFact(
                    "project_map_freshness",
                    "PROJECT_MAP_TIMESTAMP_MISSING_OR_INVALID",
                    "freshness cannot be established without a valid generated_at timestamp",
                    relative,
                )
            ],
        )

    age = (observed_at - parsed).total_seconds()
    reasons: list[str] = []
    freshness: Freshness = "fresh"
    if age < -60:
        freshness = "stale"
        reasons.append("PROJECT_MAP_TIMESTAMP_IN_FUTURE")
    elif age > max_age.total_seconds():
        freshness = "stale"
        reasons.append("PROJECT_MAP_TOO_OLD")

    map_source_sha = _first_string(payload, "source_sha", "revision", "commit", "source_revision")
    if source_sha and map_source_sha and source_sha != map_source_sha:
        freshness = "stale"
        reasons.append("PROJECT_MAP_SOURCE_MISMATCH")

    map_file_hashes = {
        str(entry.get("path")): str(entry.get("file_hash"))
        for entry in payload.get("files", [])
        if isinstance(entry, Mapping) and entry.get("path") and entry.get("file_hash")
    }
    for map_file, expected_hash in sorted(map_file_hashes.items()):
        current = root / map_file
        if not current.is_file():
            freshness = "stale"
            reasons.append("PROJECT_MAP_FILE_MISSING")
            break
        try:
            actual_hash = hashlib.sha256(current.read_bytes()).hexdigest()
        except OSError:
            continue
        if actual_hash != expected_hash:
            freshness = "stale"
            reasons.append("PROJECT_MAP_FILE_HASH_MISMATCH")
            break

    status = ProjectMapStatus(
        relative,
        True,
        freshness,
        str(generated_at),
        map_source_sha,
        round(max(0.0, age), 3),
        ";".join(sorted(set(reasons))) or None,
        ("changed_files", "dependencies", "component_boundaries") if freshness == "fresh" else (),
    )
    unknowns = [
        UnknownFact("project_map_freshness", reason, f"project map {relative} is not fresh", relative)
        for reason in sorted(set(reasons))
    ]
    return status, payload, unknowns


def _first_string(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _manifest_paths(files: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in files:
        name = PurePosixPath(path).name
        if name in _BUILD_MARKERS or PurePosixPath(path).suffix in {".csproj", ".fsproj", ".sln"}:
            result[path] = _BUILD_MARKERS.get(name, "MSBuild")
    return result


def _component_roots(root: Path, files: Sequence[str], map_payload: Mapping[str, Any] | None) -> set[str]:
    roots = {"."}
    manifest_paths = _manifest_paths(files)
    for path in files:
        if path in manifest_paths:
            roots.add(str(PurePosixPath(path).parent))
    for path in (path for path in files if PurePosixPath(path).name == "package.json"):
        payload = _read_json(root, path)
        if isinstance(payload, Mapping):
            workspaces = payload.get("workspaces", ())
            if isinstance(workspaces, Mapping):
                workspaces = workspaces.get("packages", ())
            if isinstance(workspaces, list):
                for pattern in workspaces:
                    if isinstance(pattern, str):
                        roots.update(
                            candidate.relative_to(root).as_posix()
                            for candidate in root.glob(pattern)
                            if candidate.is_dir()
                        )
    for path in (path for path in files if PurePosixPath(path).name == "pnpm-workspace.yaml"):
        text = _read_text(root, path)
        if text:
            for pattern in re.findall(r"^\s*-\s*[\"']?([^\"']+)[\"']?\s*$", text, re.MULTILINE):
                roots.update(
                    candidate.relative_to(root).as_posix()
                    for candidate in root.glob(pattern)
                    if candidate.is_dir()
                )
    for path in (path for path in files if PurePosixPath(path).name == "Cargo.toml"):
        payload = _read_toml(root, path)
        workspace = payload.get("workspace") if isinstance(payload, Mapping) else None
        members = workspace.get("members", ()) if isinstance(workspace, Mapping) else ()
        if isinstance(members, list):
            for pattern in members:
                if isinstance(pattern, str):
                    roots.update(
                        candidate.relative_to(root).as_posix()
                        for candidate in (root / PurePosixPath(path).parent).glob(pattern)
                        if candidate.is_dir()
                    )
    if map_payload:
        for key in ("components", "modules"):
            entries = map_payload.get(key)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                raw = entry.get("root", entry.get("path"))
                if isinstance(raw, str):
                    candidate = PurePosixPath(raw)
                    if candidate.as_posix() in {"", "."}:
                        roots.add(".")
                    elif (root / candidate).is_dir():
                        roots.add(candidate.as_posix())
                elif isinstance(entry.get("files"), list):
                    file_paths = [
                        PurePosixPath(str(item))
                        for item in entry["files"]
                        if isinstance(item, str) and item
                    ]
                    if file_paths:
                        common = _common_directory(file_paths)
                        if common and (root / common).is_dir():
                            roots.add(common)
    return roots


def _common_directory(paths: Sequence[PurePosixPath]) -> str | None:
    if not paths:
        return None
    first = paths[0].parts[:-1]
    common: list[str] = []
    for index, part in enumerate(first):
        if all(len(path.parts) > index + 1 and path.parts[index] == part for path in paths):
            common.append(part)
        else:
            break
    return PurePosixPath(*common).as_posix() if common else "."


def _read_json(root: Path, relative: str) -> Mapping[str, Any] | None:
    text = _read_text(root, relative)
    if text is None:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, Mapping) else None


def _read_toml(root: Path, relative: str) -> Mapping[str, Any]:
    text = _read_text(root, relative)
    if text is None:
        return {}
    try:
        payload = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _component_for(path: str, roots: Iterable[str]) -> str:
    candidates = [root for root in roots if root == "." or path == root or path.startswith(root + "/")]
    if not candidates:
        return "."
    return sorted(candidates, key=lambda item: (len(PurePosixPath(item).parts), item), reverse=True)[0]


def _detect_profile(
    root: Path,
    files: Sequence[str],
    map_payload: Mapping[str, Any] | None,
) -> tuple[RepositoryProfile, dict[str, str], list[UnknownFact]]:
    unknowns: list[UnknownFact] = []
    languages: dict[str, list[str]] = defaultdict(list)
    for path in files:
        language = _language(path)
        if language:
            languages[language].append(path)
    if not languages:
        unknowns.append(UnknownFact("languages", "NO_RECOGNIZED_SOURCE_FILES", "no supported source suffix was found"))

    manifests = _manifest_paths(files)
    build_evidence: dict[str, list[str]] = defaultdict(list)
    for path, system in manifests.items():
        build_evidence[system].append(path)
    if not build_evidence:
        unknowns.append(UnknownFact("build_systems", "NO_BUILD_MARKER", "no supported build or packaging marker was found"))

    test_evidence: dict[str, list[str]] = defaultdict(list)
    for path in files:
        name = PurePosixPath(path).name
        if name in _TEST_MARKERS:
            test_evidence[_TEST_MARKERS[name]].append(path)
        if any(part.lower() in {"test", "tests", "spec", "specs", "__tests__"} for part in PurePosixPath(path).parts):
            test_evidence["test-file-layout"].append(path)
        if name.startswith("test_") or name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts")):
            test_evidence["test-file-naming"].append(path)
    ci_paths = [path for path in files if path.startswith(".github/workflows/")]
    if ci_paths:
        test_evidence["CI workflow"].extend(ci_paths)
    if not test_evidence:
        unknowns.append(UnknownFact("test_infrastructure", "NO_TEST_INFRASTRUCTURE_DETECTED", "no test markers or test files were found"))

    public_evidence: dict[str, list[str]] = defaultdict(list)
    for path in files:
        name = PurePosixPath(path).name
        lower = path.lower()
        if name in {"__init__.py", "lib.rs", "mod.rs"} or any(
            token in PurePosixPath(path).parts for token in {"api", "public", "include"}
        ):
            public_evidence["public-module-or-api-directory"].append(path)
        text = _read_text(root, path)
        if text and (
            re.search(r"^\s*__all__\s*=", text, re.MULTILINE)
            or re.search(r"^\s*export\b", text, re.MULTILINE)
            or re.search(r"^\s*pub\s+(?:fn|struct|enum|trait|mod|use)\b", text, re.MULTILINE)
            or re.search(r"\bpublic\s+(?:class|interface|record|enum)\b", text)
        ):
            public_evidence["exported-symbols"].append(path)
        if name in {"package.json", "pyproject.toml"}:
            public_evidence["package-entry-metadata"].append(path)
        if lower.endswith((".proto", ".graphql", ".gql", ".openapi.yml", ".openapi.yaml", ".openapi.json")):
            public_evidence["interface-definition"].append(path)
    if not public_evidence:
        unknowns.append(UnknownFact("public_apis", "NO_PUBLIC_API_SIGNAL", "no public API marker was detected"))

    roots = _component_roots(root, files, map_payload)
    component_files: dict[str, list[str]] = defaultdict(list)
    component_manifests: dict[str, list[str]] = defaultdict(list)
    component_languages: dict[str, set[str]] = defaultdict(set)
    component_build: dict[str, set[str]] = defaultdict(set)
    for path in files:
        component = _component_for(path, roots)
        component_files[component].append(path)
        if path in manifests:
            component_manifests[component].append(path)
            component_build[component].add(manifests[path])
        language = _language(path)
        if language:
            component_languages[component].add(language)
    boundaries = tuple(
        ComponentBoundary(
            component,
            component,
            tuple(sorted(component_manifests[component])),
            tuple(sorted(component_languages[component])),
            tuple(sorted(component_build[component])),
            len(component_files[component]),
        )
        for component in sorted(component_files)
    )
    path_components = {path: _component_for(path, roots) for path in files}

    profile = RepositoryProfile(
        tuple(_signal(name, evidence, 0.98) for name, evidence in sorted(languages.items())),
        tuple(_signal(name, evidence, 0.99) for name, evidence in sorted(build_evidence.items())),
        tuple(_signal(name, evidence, 0.85) for name, evidence in sorted(public_evidence.items())),
        tuple(_signal(name, evidence, 0.9) for name, evidence in sorted(test_evidence.items())),
        boundaries,
    )
    return profile, path_components, unknowns


def _map_entries(map_payload: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not map_payload or not isinstance(map_payload.get("files"), list):
        return {}
    return {
        str(entry["path"]): entry
        for entry in map_payload["files"]
        if isinstance(entry, Mapping) and isinstance(entry.get("path"), str)
    }


def _generated_info(
    root: Path,
    path: str,
    map_entry: Mapping[str, Any] | None,
) -> tuple[bool | None, str | None]:
    if map_entry:
        roles = map_entry.get("roles")
        if isinstance(map_entry.get("generated"), bool):
            return map_entry["generated"], "project-map"
        if isinstance(roles, list) and any("generated" in str(role).lower() for role in roles):
            return True, "project-map-role"
    parts = PurePosixPath(path).parts
    if any(part.lower() in _GENERATED_DIRS for part in parts):
        return True, "path-pattern"
    if _GENERATED_NAME_RE.search(PurePosixPath(path).name):
        return True, "name-pattern"
    text = _read_text(root, path, 4096)
    if text and _GENERATED_TEXT_RE.search(text):
        return True, "file-header"
    return None, None


def _resolve_changed(
    root: Path,
    changed: tuple[ChangedFile, ...],
    map_entries: Mapping[str, Mapping[str, Any]],
    path_components: Mapping[str, str],
    unknowns: list[UnknownFact],
) -> tuple[ChangedFile, ...]:
    result: list[ChangedFile] = []
    for item in changed:
        generated = item.generated
        generated_reason = item.generated_reason
        if generated is None:
            generated, generated_reason = _generated_info(root, item.path, map_entries.get(item.path))
        component = path_components.get(item.path, item.component or ".")
        if item.status == "unknown":
            unknowns.append(UnknownFact("changed_file_status", "UNKNOWN_CHANGE_STATUS", f"status for {item.path} is unknown", item.path))
        if item.status in {"deleted", "renamed"} and item.path not in map_entries and not (root / item.path).exists():
            unknowns.append(UnknownFact("changed_file", "PATH_NOT_PRESENT_IN_CURRENT_TREE", f"{item.path} is not present in the current tree", item.path))
        if item.old_path and item.old_path not in map_entries and not (root / item.old_path).exists():
            unknowns.append(UnknownFact("changed_file", "OLD_PATH_NOT_PRESENT", f"rename source {item.old_path} is not present in the current tree or map", item.old_path))
        result.append(ChangedFile(item.path, item.status, item.old_path, generated, generated_reason, component))
    return _deduplicate_changed(result)


def _resolve_import_target(source: str, imported: str, known: set[str]) -> str | None:
    source_path = PurePosixPath(source)
    candidates: list[str] = []
    if imported.startswith("."):
        base = source_path.parent / imported
        candidates.extend(_module_candidates(base))
    elif "/" in imported and not imported.startswith(("http:", "https:")):
        candidates.extend(_module_candidates(PurePosixPath(imported)))
    else:
        dotted = imported.replace("::", "/").replace(".", "/")
        candidates.extend(_module_candidates(PurePosixPath(dotted)))
    for candidate in candidates:
        normalized = PurePosixPath(candidate).as_posix()
        if normalized in known:
            return normalized
    return None


def _module_candidates(base: PurePosixPath) -> list[str]:
    normalized = base.as_posix()
    suffix = PurePosixPath(normalized).suffix
    if suffix:
        return [normalized]
    return [
        normalized,
        *(normalized + extension for extension in (".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".rs", ".go")),
        *(f"{normalized}/index{extension}" for extension in (".js", ".jsx", ".ts", ".tsx")),
        f"{normalized}/__init__.py",
        f"{normalized}/mod.rs",
    ]


def _dependencies(
    root: Path,
    files: Sequence[str],
    map_entries: Mapping[str, Mapping[str, Any]],
    unknowns: list[UnknownFact],
) -> dict[str, tuple[str, ...]]:
    known = set(files) | set(map_entries)
    graph: dict[str, set[str]] = {path: set() for path in sorted(known)}
    for source in sorted(known):
        entry = map_entries.get(source)
        imports: list[str] = []
        if entry and isinstance(entry.get("imports"), list):
            imports.extend(str(item) for item in entry["imports"] if item)
        text = _read_text(root, source)
        if text:
            for groups in _IMPORT_RE.findall(text):
                imports.extend(group for group in groups if group)
        if not imports and text and _language(source) in {"Python", "JavaScript", "TypeScript", "Rust", "Go"}:
            # An empty import list is a known fact.  We only report unknown when
            # the source could not be read, because absence of imports is valid.
            pass
        if not text and source in files and _language(source):
            unknowns.append(UnknownFact("dependencies", "SOURCE_UNREADABLE", f"could not read {source}", source))
        for imported in imports:
            target = _resolve_import_target(source, imported, known)
            if target and target != source:
                graph[source].add(target)
    return {path: tuple(sorted(targets)) for path, targets in sorted(graph.items())}


def _reverse_graph(graph: Mapping[str, Sequence[str]]) -> dict[str, tuple[str, ...]]:
    reverse: dict[str, set[str]] = {key: set() for key in graph}
    for source, targets in graph.items():
        for target in targets:
            reverse.setdefault(target, set()).add(source)
    return {key: tuple(sorted(value)) for key, value in sorted(reverse.items())}


def _affected_files(
    changed: Sequence[ChangedFile],
    reverse: Mapping[str, Sequence[str]],
) -> tuple[str, ...]:
    roots = {item.path for item in changed}
    roots.update(item.old_path for item in changed if item.old_path)
    seen = set(roots)
    queue = deque(sorted(roots))
    while queue:
        current = queue.popleft()
        for dependent in reverse.get(current, ()):
            if dependent not in seen:
                seen.add(dependent)
                queue.append(dependent)
    return tuple(sorted(seen))


def _risk_surfaces(
    changed: Sequence[ChangedFile],
    impacted: Sequence[str],
    profile: RepositoryProfile,
    map_status: ProjectMapStatus,
    path_components: Mapping[str, str],
) -> tuple[RiskSurface, ...]:
    changed_paths = {item.path for item in changed}
    public_paths = {
        path
        for signal in profile.public_apis
        for path in signal.evidence
    }
    test_paths = {
        path
        for signal in profile.test_infrastructure
        for path in signal.evidence
    }
    build_paths = {path for signal in profile.build_systems for path in signal.evidence}
    surfaces: list[RiskSurface] = []

    def add(kind: str, paths: Iterable[str], score: float, reasons: Iterable[str]) -> None:
        normalized = tuple(sorted(set(paths)))
        if normalized:
            surfaces.append(
                RiskSurface(kind, normalized, _confidence(score), path_components.get(normalized[0], "."))
            )
            surfaces[-1] = RiskSurface(
                kind,
                normalized,
                _confidence(score),
                tuple(sorted(set(reasons))),
                path_components.get(normalized[0], "."),
            )

    add("changed", changed_paths, 0.45, ("explicit_change_set",))
    add("reverse_dependents", set(impacted) - changed_paths, 0.7, ("dependency_graph",))
    add("public_api", changed_paths & public_paths, 0.95, ("public_api_signal",))
    add("build_or_packaging", changed_paths & build_paths, 0.9, ("build_marker_changed",))
    add("test_infrastructure", changed_paths & test_paths, 0.6, ("test_infrastructure_changed",))
    add(
        "generated_artifacts",
        (item.path for item in changed if item.generated is True),
        0.65,
        ("generated_file_signal", "source_of_truth_requires_confirmation"),
    )
    add(
        "deletion_or_rename",
        (item.path for item in changed if item.status in {"deleted", "renamed"}),
        0.85,
        ("destructive_or_identity_change",),
    )
    if map_status.freshness in {"missing", "stale", "invalid", "unknown"}:
        add(
            "mapper_uncertainty",
            changed_paths or (".",),
            0.8,
            (f"project_map_{map_status.freshness}", "impact_context_is_incomplete"),
        )
    return tuple(sorted(surfaces, key=lambda item: (item.kind, item.paths)))


def analyze_repository(
    repository: str | Path,
    *,
    changed_files: str | bytes | Iterable[ChangedFile | Mapping[str, Any] | str] | None = None,
    diff_name_status: str | bytes | None = None,
    project_map: str | Path | None = None,
    source_sha: str | None = None,
    observed_at: datetime | None = None,
    project_map_max_age: timedelta = timedelta(days=7),
) -> ImpactMap:
    """Build an impact map from repository evidence.

    The caller should pass the Loop's authoritative change set.  If no change
    set is supplied, the output contains ``CHANGED_FILES_NOT_SUPPLIED`` and an
    empty change list; it never treats the whole repository as changed.
    """

    root = Path(repository).resolve()
    if not root.is_dir():
        raise ImpactAnalysisError(f"repository is not a directory: {repository}")
    observed = (observed_at or _utc_now()).astimezone(timezone.utc)
    files = _iter_files(root)
    map_status, map_payload, unknowns = _load_project_map(
        root,
        project_map,
        observed_at=observed,
        source_sha=source_sha,
        max_age=project_map_max_age,
    )
    profile, path_components, profile_unknowns = _detect_profile(root, files, map_payload)
    unknowns.extend(profile_unknowns)

    raw_changed = diff_name_status if diff_name_status is not None else changed_files
    if raw_changed is None:
        changed = ()
        unknowns.append(
            UnknownFact(
                "changed_files",
                "CHANGED_FILES_NOT_SUPPLIED",
                "the Loop did not provide a change set; no paths were inferred",
            )
        )
    else:
        changed = parse_changed_files(raw_changed, root=root)
    map_entries = _map_entries(map_payload)
    changed = _resolve_changed(root, changed, map_entries, path_components, unknowns)
    graph = _dependencies(root, files, map_entries, unknowns)
    reverse = _reverse_graph(graph)
    impacted = _affected_files(changed, reverse)
    surfaces = _risk_surfaces(changed, impacted, profile, map_status, path_components)

    score_parts = [0.9 if changed_files is not None or diff_name_status is not None else 0.0]
    score_parts.append({"fresh": 1.0, "stale": 0.65, "invalid": 0.35, "missing": 0.5, "unknown": 0.25}[map_status.freshness])
    if graph:
        score_parts.append(0.85)
    if any(item.reason_code in {"SOURCE_UNREADABLE", "UNKNOWN_CHANGE_STATUS"} for item in unknowns):
        score_parts.append(0.35)
    confidence = _confidence(sum(score_parts) / len(score_parts))
    return ImpactMap(
        root.as_posix(),
        profile,
        map_status,
        changed,
        graph,
        reverse,
        impacted,
        surfaces,
        tuple(sorted(set(unknowns), key=lambda item: (item.kind, item.scope, item.reason_code, item.detail))),
        confidence,
    )


__all__ = [
    "ChangedFile",
    "ComponentBoundary",
    "ImpactAnalysisError",
    "ImpactMap",
    "ProjectMapStatus",
    "RepositoryProfile",
    "RiskSurface",
    "Signal",
    "UnknownFact",
    "analyze_repository",
    "parse_changed_files",
]
