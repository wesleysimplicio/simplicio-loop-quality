"""Declarative quality-adapter contracts; execution remains owned by Loop Hub."""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from simplicio_loop.process_supervisor import ProcessSpec

from simplicio_loop_quality.contract_validation import validate_contract_document

ADAPTER_API = "1.0"
KNOWN_CAPABILITIES = frozenset({"test.run", "quality.collect", "quality.audit"})
KNOWN_OUTPUTS = frozenset(
    {
        "simplicio.quality-stage-request/v1",
        "simplicio.quality-stage-result/v1",
        "simplicio.quality-evidence/v2",
    }
)
FORBIDDEN_AUTHORITY = frozenset(
    {"schedule", "hub.submit", "terminal", "oracle.complete", "process.execute"}
)
FAILURE_CODES = frozenset(
    {
        "ADAPTER_INCOMPATIBLE",
        "ADAPTER_CRASHED",
        "ADAPTER_CANCELLED",
        "INVALID_ADAPTER_OUTPUT",
        "INFRASTRUCTURE_UNAVAILABLE",
    }
)
_ID = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class AdapterContractError(ValueError):
    """An adapter is incompatible before any invocation may occur."""


@dataclass(frozen=True)
class ResourceRequest:
    cpu_millis: int
    memory_mib: int
    timeout_seconds: float


@dataclass(frozen=True)
class AdapterDescriptor:
    adapter_id: str
    api_version: str
    capabilities: tuple[str, ...]
    output_schemas: tuple[str, ...]
    resources: ResourceRequest
    descriptor_hash: str


@dataclass(frozen=True)
class Cancellation:
    requested: bool
    reason_code: str | None = None


@dataclass(frozen=True)
class AdapterRequest:
    schema: str
    identity: Mapping[str, Any]
    capability: str
    payload: Mapping[str, Any]
    cancellation: Cancellation


@dataclass(frozen=True)
class AdapterOutcome:
    schema: str
    status: str
    output: Mapping[str, Any] | None
    failure_code: str | None
    retry_hint: bool


@runtime_checkable
class QualityAdapter(Protocol):
    descriptor: Mapping[str, Any]

    def invoke(
        self, request: AdapterRequest
    ) -> Mapping[str, Any] | Awaitable[Mapping[str, Any]]: ...


@runtime_checkable
class QualityAgent(Protocol):
    descriptor: Mapping[str, Any]

    def plan(self, request: AdapterRequest) -> Mapping[str, Any]: ...


def _canonical_hash(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_descriptor(value: Mapping[str, Any]) -> AdapterDescriptor:
    """Validate a closed descriptor without importing or invoking plugin code."""

    if not isinstance(value, Mapping):
        raise AdapterContractError("descriptor must be an object")
    expected = {
        "schema",
        "adapter_id",
        "api_version",
        "capabilities",
        "output_schemas",
        "resources",
    }
    if set(value) != expected or value.get("schema") != "simplicio.quality-adapter/v1":
        raise AdapterContractError("descriptor fields or schema are incompatible")
    adapter_id = value.get("adapter_id")
    if not isinstance(adapter_id, str) or not _ID.fullmatch(adapter_id):
        raise AdapterContractError("adapter_id must be canonical lowercase")
    api_version = value.get("api_version")
    if not isinstance(api_version, str) or not _VERSION.fullmatch(api_version):
        raise AdapterContractError("api_version must be major.minor")
    if api_version.split(".", 1)[0] != ADAPTER_API.split(".", 1)[0]:
        raise AdapterContractError("adapter API major version is incompatible")
    capabilities = value.get("capabilities")
    if (
        not isinstance(capabilities, list)
        or not capabilities
        or any(not isinstance(item, str) for item in capabilities)
    ):
        raise AdapterContractError("capabilities must be a non-empty array")
    if len(set(capabilities)) != len(capabilities):
        raise AdapterContractError("capabilities must be unique")
    unknown = set(capabilities) - KNOWN_CAPABILITIES
    forbidden = set(capabilities) & FORBIDDEN_AUTHORITY
    if unknown or forbidden:
        raise AdapterContractError("unknown or authority-bearing capability")
    outputs = value.get("output_schemas")
    if (
        not isinstance(outputs, list)
        or not outputs
        or any(not isinstance(item, str) for item in outputs)
        or len(set(outputs)) != len(outputs)
    ):
        raise AdapterContractError("output_schemas must be a unique non-empty array")
    if set(outputs) - KNOWN_OUTPUTS:
        raise AdapterContractError("unknown output schema")
    resources = value.get("resources")
    if not isinstance(resources, Mapping) or set(resources) != {
        "cpu_millis",
        "memory_mib",
        "timeout_seconds",
    }:
        raise AdapterContractError("resource request is incomplete or ambiguous")
    cpu, memory, timeout = (
        resources.get("cpu_millis"),
        resources.get("memory_mib"),
        resources.get("timeout_seconds"),
    )
    if not isinstance(cpu, int) or isinstance(cpu, bool) or not 1 <= cpu <= 16000:
        raise AdapterContractError("cpu_millis is outside policy")
    if not isinstance(memory, int) or isinstance(memory, bool) or not 1 <= memory <= 65536:
        raise AdapterContractError("memory_mib is outside policy")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not 0 < timeout <= 86400
    ):
        raise AdapterContractError("timeout_seconds is outside policy")
    canonical = dict(value)
    canonical["capabilities"] = sorted(capabilities)
    canonical["output_schemas"] = sorted(outputs)
    return AdapterDescriptor(
        adapter_id=adapter_id,
        api_version=api_version,
        capabilities=tuple(sorted(capabilities)),
        output_schemas=tuple(sorted(outputs)),
        resources=ResourceRequest(cpu, memory, float(timeout)),
        descriptor_hash=_canonical_hash(canonical),
    )


def discover_adapters(values: Sequence[Mapping[str, Any]]) -> tuple[AdapterDescriptor, ...]:
    """Validate the supplied declarations first, then return deterministic order."""

    descriptors = [validate_descriptor(value) for value in values]
    ids = [descriptor.adapter_id for descriptor in descriptors]
    if len(set(ids)) != len(ids):
        raise AdapterContractError("duplicate adapter_id")
    return tuple(sorted(descriptors, key=lambda descriptor: descriptor.adapter_id))


def build_process_spec(
    argv: Sequence[str],
    *,
    cwd: str | None = None,
    cwd_allowlist: Sequence[str] = (),
    env: Mapping[str, str] | None = None,
    env_allowlist: Sequence[str] = (),
    timeout_seconds: float = 30.0,
    idempotency_key: str,
) -> ProcessSpec:
    """Build native Loop data only; this module never runs or submits it."""

    if not argv or any(not isinstance(part, str) or not part.strip() for part in argv):
        raise AdapterContractError("argv must contain non-empty strings")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise AdapterContractError("idempotency_key is required")
    if cwd is not None:
        if not cwd_allowlist:
            raise AdapterContractError("cwd requires a trusted allowlist")
        resolved = Path(cwd).resolve()
        if not any(resolved.is_relative_to(Path(root).resolve()) for root in cwd_allowlist):
            raise AdapterContractError("cwd is outside the trusted allowlist")
    return ProcessSpec(
        argv=tuple(argv),
        cwd=cwd,
        cwd_allowlist=tuple(cwd_allowlist),
        env=dict(env or {}),
        env_allowlist=tuple(env_allowlist),
        timeout_seconds=timeout_seconds,
        idempotency_key=idempotency_key,
        shell=False,
    )


async def invoke_adapter(adapter: QualityAdapter, request: AdapterRequest) -> AdapterOutcome:
    """Conformance invocation for in-process data adapters; commands remain unexecuted."""

    descriptor = validate_descriptor(adapter.descriptor)
    if request.capability not in descriptor.capabilities:
        raise AdapterContractError("requested capability was not declared")
    if request.cancellation.requested:
        return AdapterOutcome(
            "simplicio.quality-adapter-outcome/v1",
            "CANCELLED",
            None,
            "ADAPTER_CANCELLED",
            False,
        )
    try:
        safe_request = AdapterRequest(
            request.schema,
            _freeze(request.identity),
            request.capability,
            _freeze(request.payload),
            request.cancellation,
        )
        result = adapter.invoke(safe_request)
        if inspect.isawaitable(result):
            result = await result
    except Exception:
        return AdapterOutcome(
            "simplicio.quality-adapter-outcome/v1",
            "BLOCKED",
            None,
            "ADAPTER_CRASHED",
            False,
        )
    if not isinstance(result, Mapping):
        return AdapterOutcome(
            "simplicio.quality-adapter-outcome/v1",
            "BLOCKED",
            None,
            "INVALID_ADAPTER_OUTPUT",
            False,
        )
    output = dict(result)
    if output.get("schema") not in descriptor.output_schemas:
        return AdapterOutcome(
            "simplicio.quality-adapter-outcome/v1",
            "BLOCKED",
            None,
            "INVALID_ADAPTER_OUTPUT",
            False,
        )
    if validate_contract_document(output):
        return AdapterOutcome(
            "simplicio.quality-adapter-outcome/v1",
            "BLOCKED",
            None,
            "INVALID_ADAPTER_OUTPUT",
            False,
        )
    if set(output) & {"terminal", "ready", "schedule", "hub_submit"}:
        return AdapterOutcome(
            "simplicio.quality-adapter-outcome/v1",
            "BLOCKED",
            None,
            "INVALID_ADAPTER_OUTPUT",
            False,
        )
    return AdapterOutcome(
        "simplicio.quality-adapter-outcome/v1",
        "PASS",
        _freeze(output),
        None,
        False,
    )


AdapterFactory = Callable[[], QualityAdapter]


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value
