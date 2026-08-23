"""Canonical hashing and content-addressed evidence persistence.

The Loop owns execution and its journal.  This module only stores immutable
evidence bytes and the one manifest that binds those bytes to reproducibility
inputs.  It intentionally does not start commands, schedule work, or maintain
a second run ledger.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


REDACTED = "[REDACTED]"
MANIFEST_SCHEMA = "simplicio.quality-evidence-manifest/v1"
_SOURCE_SHA = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
_DIGEST = re.compile(r"^[0-9a-fA-F]{64}$")
_SECRET_KEY = re.compile(
    r"(?:api[-_]?key|access[-_]?key|auth(?:orization)?|cookie|credential|private[-_]?key|password|secret|token)",
    re.IGNORECASE,
)
_SECRET_OPTION = re.compile(
    r"^(?:--?)?(?:api[-_]?key|access[-_]?key|auth(?:orization)?|cookie|credential|private[-_]?key|password|secret|token)(?:[=:].*)?$",
    re.IGNORECASE,
)
_SECRET_TEXT = re.compile(
    r"(?i)(\b(?:api[-_]?key|access[-_]?key|authorization|cookie|password|secret|token)\b"
    r"\s*(?:[:=]|\s)\s*(?:bearer\s+)?)([\"']?)([^\s,;\"']+)(\2)"
)


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def evidence_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def _redact_text(value: str) -> str:
    """Redact common ``key=value``/header forms without changing other text."""

    return _SECRET_TEXT.sub(lambda match: f"{match.group(1)}{REDACTED}", value)


def redact_secrets(value: Any) -> Any:
    """Return a JSON-compatible copy with secret values removed.

    Redaction happens before provenance is serialized.  Mapping keys remain
    visible for diagnostics, while values under sensitive keys and values
    following sensitive command options are replaced with ``[REDACTED]``.
    """

    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if _SECRET_KEY.search(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        redacted: list[Any] = []
        redact_next = False
        for item in value:
            if redact_next:
                redacted.append(REDACTED)
                redact_next = False
                continue
            redacted_item = redact_secrets(item)
            redacted.append(redacted_item)
            redact_next = isinstance(item, str) and _SECRET_OPTION.fullmatch(item.strip()) is not None
        return redacted
    if isinstance(value, str):
        return _redact_text(value)
    return value


class EvidenceError(ValueError):
    """Base class for invalid, unverifiable, or unreplayable evidence."""


class EvidenceValidationError(EvidenceError):
    """Raised when an evidence binding or manifest is malformed."""


class ArtifactMissingError(EvidenceError):
    """Raised when a required content-addressed artifact is absent."""


class ArtifactTamperedError(EvidenceError):
    """Raised when bytes no longer match their recorded digest."""


class ReplayMismatchError(EvidenceError):
    """Raised when replay output differs from the recorded artifact."""


@dataclass(frozen=True)
class EvidenceBinding:
    """Inputs that make an evidence item reproducible and auditable."""

    source_sha: str
    policy_hash: str
    tool_name: str
    tool_version: str
    command: tuple[str, ...]
    environment_hash: str
    seed: int | None = None

    def __post_init__(self) -> None:
        if not _SOURCE_SHA.fullmatch(self.source_sha):
            raise EvidenceValidationError("source_sha must be a 40- or 64-character digest")
        if not _DIGEST.fullmatch(self.policy_hash):
            raise EvidenceValidationError("policy_hash must be a SHA-256 digest")
        if not self.tool_name.strip() or not self.tool_version.strip():
            raise EvidenceValidationError("tool_name and tool_version are required")
        if not self.command or not all(isinstance(part, str) and part.strip() for part in self.command):
            raise EvidenceValidationError("command must contain at least one non-empty argument")
        if not _DIGEST.fullmatch(self.environment_hash):
            raise EvidenceValidationError("environment_hash must be a SHA-256 digest")
        if isinstance(self.seed, bool) or (self.seed is not None and not isinstance(self.seed, int)):
            raise EvidenceValidationError("seed must be an integer or null")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceBinding":
        if not isinstance(value, Mapping):
            raise EvidenceValidationError("binding must be an object")
        redacted = redact_secrets(value)
        command = redacted.get("command")
        if not isinstance(command, (list, tuple)):
            raise EvidenceValidationError("command must be an array")
        return cls(
            source_sha=str(redacted.get("source_sha", "")),
            policy_hash=str(redacted.get("policy_hash", "")),
            tool_name=str(redacted.get("tool_name", "")),
            tool_version=str(redacted.get("tool_version", "")),
            command=tuple(str(part) for part in command),
            environment_hash=str(redacted.get("environment_hash", "")),
            seed=redacted.get("seed"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_sha": self.source_sha.lower(),
            "policy_hash": self.policy_hash.lower(),
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "command": list(redact_secrets(self.command)),
            "environment_hash": self.environment_hash.lower(),
            "seed": self.seed,
        }


@dataclass(frozen=True)
class RetentionPolicy:
    """Manifest retention semantics.

    ``required`` means that a missing artifact is unverifiable and blocks
    replay.  ``manifest_only`` permits an expired artifact to be removed, but
    never turns the missing bytes into a successful verification or replay.
    """

    mode: str = "required"
    retain_until: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"required", "manifest_only"}:
            raise EvidenceValidationError("retention mode must be required or manifest_only")
        if self.retain_until is not None:
            parsed = _parse_timestamp(self.retain_until)
            if parsed is None:
                raise EvidenceValidationError("retain_until must be an ISO-8601 timestamp")

    def to_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "retain_until": self.retain_until}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RetentionPolicy":
        return cls(mode=str(value.get("mode", "")), retain_until=value.get("retain_until"))


@dataclass(frozen=True)
class StoredArtifact:
    """A content-addressed object and its one provenance observation."""

    ref: str
    sha256: str
    size: int
    binding: EvidenceBinding
    metadata: Mapping[str, Any] | None = None

    def provenance(self) -> dict[str, Any]:
        result = self.binding.to_dict()
        if self.metadata:
            result["metadata"] = redact_secrets(dict(self.metadata))
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "sha256": self.sha256,
            "size": self.size,
            "provenance": [self.provenance()],
        }


@dataclass(frozen=True)
class EvidenceManifest:
    """Deterministic index for deduplicated artifacts."""

    manifest_id: str
    artifacts: tuple[Mapping[str, Any], ...]
    retention: RetentionPolicy = RetentionPolicy()

    def payload(self) -> dict[str, Any]:
        return {
            "schema": MANIFEST_SCHEMA,
            "artifacts": [dict(item) for item in self.artifacts],
            "retention": self.retention.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.payload(), "manifest_id": self.manifest_id}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceManifest":
        if not isinstance(value, Mapping):
            raise EvidenceValidationError("manifest must be an object")
        if value.get("schema") != MANIFEST_SCHEMA:
            raise EvidenceValidationError(f"expected {MANIFEST_SCHEMA}")
        artifacts = value.get("artifacts")
        retention = value.get("retention")
        manifest_id = value.get("manifest_id")
        if not isinstance(artifacts, list) or not isinstance(retention, Mapping):
            raise EvidenceValidationError("manifest artifacts and retention are required")
        if not isinstance(manifest_id, str) or not _DIGEST.fullmatch(manifest_id):
            raise EvidenceValidationError("manifest_id must be a SHA-256 digest")
        policy = RetentionPolicy.from_mapping(retention)
        normalized = tuple(_normalize_artifact(item) for item in artifacts)
        result = cls(manifest_id=manifest_id, artifacts=normalized, retention=policy)
        if evidence_hash(result.payload()) != manifest_id:
            raise EvidenceValidationError("manifest_id does not match canonical manifest content")
        return result


@dataclass(frozen=True)
class VerificationResult:
    """Fail-closed result of checking a manifest and its object store."""

    status: str
    findings: tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        return self.status == "VERIFIED"


@dataclass(frozen=True)
class ReplayResult:
    """Result of replaying every provenance observation."""

    status: str
    artifact_hashes: tuple[str, ...]


def _parse_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _normalize_artifact(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceValidationError("artifact entry must be an object")
    required = {"ref", "sha256", "size", "provenance"}
    if not required.issubset(value):
        raise EvidenceValidationError("artifact entry is missing required fields")
    digest = str(value["sha256"]).lower()
    if not _DIGEST.fullmatch(digest):
        raise EvidenceValidationError("artifact sha256 must be a SHA-256 digest")
    ref = str(value["ref"])
    if not ref or Path(ref).is_absolute() or ".." in Path(ref).parts:
        raise EvidenceValidationError("artifact ref must be a relative safe path")
    if isinstance(value["size"], bool) or not isinstance(value["size"], int) or value["size"] < 0:
        raise EvidenceValidationError("artifact size must be a non-negative integer")
    provenance = value["provenance"]
    if not isinstance(provenance, list) or not provenance:
        raise EvidenceValidationError("artifact provenance must be a non-empty array")
    normalized_provenance: list[dict[str, Any]] = []
    for item in provenance:
        binding = EvidenceBinding.from_mapping(item)
        metadata = item.get("metadata") if isinstance(item, Mapping) else None
        normalized = binding.to_dict()
        if metadata is not None:
            if not isinstance(metadata, Mapping):
                raise EvidenceValidationError("provenance metadata must be an object")
            normalized["metadata"] = redact_secrets(dict(metadata))
        normalized_provenance.append(normalized)
    normalized_provenance.sort(key=lambda item: canonical_json(item))
    return {
        "ref": ref,
        "sha256": digest,
        "size": value["size"],
        "provenance": normalized_provenance,
    }


def _coerce_bytes(value: bytes | bytearray | memoryview | str | Path) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, Path):
        return value.read_bytes()
    if isinstance(value, str):
        return value.encode("utf-8")
    raise TypeError("artifact content must be bytes, text, or a path")


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class EvidenceStore:
    """Persist immutable evidence objects and one deterministic manifest."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.objects = self.root / "objects" / "sha256"

    def object_ref(self, digest: str) -> str:
        if not _DIGEST.fullmatch(digest):
            raise EvidenceValidationError("artifact digest must be a SHA-256 digest")
        return f"objects/sha256/{digest.lower()}"

    def put(
        self,
        content: bytes | bytearray | memoryview | str | Path,
        *,
        binding: EvidenceBinding | Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
    ) -> StoredArtifact:
        if metadata is not None and not isinstance(metadata, Mapping):
            raise EvidenceValidationError("metadata must be an object")
        raw = _coerce_bytes(content)
        digest = hashlib.sha256(raw).hexdigest()
        ref = self.object_ref(digest)
        target = self.root / ref
        if target.is_symlink():
            raise ArtifactTamperedError(f"content-addressed path is a symlink: {ref}")
        if not target.exists():
            _write_bytes_atomic(target, raw)
        elif not target.is_file():
            raise EvidenceError(f"content-addressed path is not a file: {ref}")
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != digest:
            raise ArtifactTamperedError(f"existing artifact does not match {ref}")
        normalized_binding = (
            binding if isinstance(binding, EvidenceBinding) else EvidenceBinding.from_mapping(binding)
        )
        return StoredArtifact(ref, digest, len(raw), normalized_binding, metadata)

    put_artifact = put

    def build_manifest(
        self,
        records: Iterable[StoredArtifact | Mapping[str, Any]],
        *,
        retention: RetentionPolicy = RetentionPolicy(),
    ) -> EvidenceManifest:
        grouped: dict[str, dict[str, Any]] = {}
        provenance_by_digest: defaultdict[str, dict[bytes, dict[str, Any]]] = defaultdict(dict)
        for record in records:
            if isinstance(record, StoredArtifact):
                item = record.to_dict()
            elif isinstance(record, Mapping):
                item = dict(record)
            else:
                raise EvidenceValidationError("manifest records must be StoredArtifact objects")
            normalized = _normalize_artifact(item)
            digest = normalized["sha256"]
            existing = grouped.setdefault(
                digest,
                {"ref": normalized["ref"], "sha256": digest, "size": normalized["size"]},
            )
            if existing["size"] != normalized["size"] or existing["ref"] != normalized["ref"]:
                raise EvidenceValidationError(f"conflicting metadata for artifact {digest}")
            for provenance in normalized["provenance"]:
                encoded = canonical_json(provenance)
                provenance_by_digest[digest][encoded] = provenance
        artifacts = []
        for digest in sorted(grouped):
            artifact = grouped[digest]
            artifact["provenance"] = [
                provenance_by_digest[digest][key]
                for key in sorted(provenance_by_digest[digest])
            ]
            artifacts.append(artifact)
        draft = {
            "schema": MANIFEST_SCHEMA,
            "artifacts": artifacts,
            "retention": retention.to_dict(),
        }
        manifest = EvidenceManifest(evidence_hash(draft), tuple(artifacts), retention)
        self._validate_manifest(manifest)
        return manifest

    manifest = build_manifest

    def write_manifest(
        self,
        manifest: EvidenceManifest | Mapping[str, Any],
        path: str | Path | None = None,
    ) -> Path:
        normalized = manifest if isinstance(manifest, EvidenceManifest) else EvidenceManifest.from_mapping(manifest)
        self._validate_manifest(normalized)
        target = self.root / "evidence-manifest.json" if path is None else Path(path)
        if not target.is_absolute():
            target = self.root / target
        write_json_atomic(target, normalized.to_dict())
        return target

    def read_manifest(self, path: str | Path | None = None) -> EvidenceManifest:
        target = self.root / "evidence-manifest.json" if path is None else Path(path)
        if not target.is_absolute():
            target = self.root / target
        try:
            return EvidenceManifest.from_mapping(json.loads(target.read_text(encoding="utf-8")))
        except FileNotFoundError as exc:
            raise ArtifactMissingError(f"manifest is missing: {target}") from exc
        except json.JSONDecodeError as exc:
            raise EvidenceValidationError(f"manifest is not valid JSON: {target}") from exc

    def verify(
        self,
        manifest: EvidenceManifest | Mapping[str, Any] | str | Path,
        *,
        now: datetime | None = None,
    ) -> VerificationResult:
        try:
            normalized = self._coerce_manifest(manifest)
        except EvidenceError as exc:
            return VerificationResult("INVALID", (str(exc),))
        findings: list[str] = []
        for artifact in normalized.artifacts:
            try:
                target = self._safe_target(artifact["ref"])
            except EvidenceError as exc:
                findings.append(f"invalid_ref:{artifact['sha256']}:{exc}")
                continue
            if not target.is_file():
                reason = "artifact_missing"
                expires_at = _parse_timestamp(normalized.retention.retain_until)
                check_at = now or datetime.now(timezone.utc)
                if normalized.retention.mode == "manifest_only":
                    reason = "artifact_not_retained"
                elif expires_at is not None and check_at >= expires_at:
                    reason = "artifact_expired"
                findings.append(f"{reason}:{artifact['sha256']}")
                continue
            try:
                raw = target.read_bytes()
            except OSError as exc:
                findings.append(f"artifact_unreadable:{artifact['sha256']}:{exc}")
                continue
            actual = hashlib.sha256(raw).hexdigest()
            if actual != artifact["sha256"] or len(raw) != artifact["size"]:
                findings.append(f"artifact_tampered:{artifact['sha256']}")
        if findings:
            missing_reasons = {"artifact_missing", "artifact_not_retained", "artifact_expired"}
            statuses = {item.split(":", 1)[0] for item in findings}
            status = "MISSING" if statuses and statuses.issubset(missing_reasons) else "TAMPERED"
            return VerificationResult(status, tuple(findings))
        return VerificationResult("VERIFIED")

    verify_manifest = verify

    def replay(
        self,
        manifest: EvidenceManifest | Mapping[str, Any] | str | Path,
        runner: Callable[[Mapping[str, Any]], bytes | bytearray | memoryview | str | Path],
    ) -> ReplayResult:
        normalized = self._coerce_manifest(manifest)
        verification = self.verify(normalized)
        if verification.status == "MISSING":
            raise ArtifactMissingError("cannot replay a manifest with missing artifacts")
        if verification.status != "VERIFIED":
            raise ArtifactTamperedError("cannot replay an unverifiable manifest")
        replayed: list[str] = []
        for artifact in normalized.artifacts:
            for provenance in artifact["provenance"]:
                try:
                    output = _coerce_bytes(runner(provenance))
                except Exception as exc:
                    raise ReplayMismatchError(
                        f"replay failed for {artifact['sha256']}: {exc}"
                    ) from exc
                digest = hashlib.sha256(output).hexdigest()
                if digest != artifact["sha256"]:
                    raise ReplayMismatchError(
                        f"replay digest {digest} does not match {artifact['sha256']}"
                    )
                replayed.append(digest)
        return ReplayResult("REPLAYED", tuple(replayed))

    replay_manifest = replay

    def _safe_target(self, ref: str) -> Path:
        raw = Path(ref)
        if raw.is_absolute() or ".." in raw.parts:
            raise EvidenceValidationError("artifact ref must stay below the evidence root")
        target = (self.root / raw).resolve()
        if target != self.root and self.root not in target.parents:
            raise EvidenceValidationError("artifact ref escapes the evidence root")
        return target

    def _coerce_manifest(self, value: EvidenceManifest | Mapping[str, Any] | str | Path) -> EvidenceManifest:
        if isinstance(value, EvidenceManifest):
            self._validate_manifest(value)
            return value
        if isinstance(value, (str, Path)):
            return self.read_manifest(value)
        manifest = EvidenceManifest.from_mapping(value)
        self._validate_manifest(manifest)
        return manifest

    @staticmethod
    def _validate_manifest(manifest: EvidenceManifest) -> None:
        if evidence_hash(manifest.payload()) != manifest.manifest_id:
            raise EvidenceValidationError("manifest_id does not match canonical manifest content")
        try:
            from .contract_validation import validate_contract_document

            errors = validate_contract_document(manifest.to_dict())
        except ImportError:
            errors = []
        if errors:
            raise EvidenceValidationError("; ".join(errors))


def write_json_atomic(path: str | Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try:
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target
