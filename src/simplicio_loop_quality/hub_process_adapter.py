"""Thin Quality tool adapter for Loop's centralized Hub process lifecycle."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol

from simplicio_loop.hub_queue_agent import HubQueueAgentError
from simplicio_loop.process_supervisor import PROCESS_RESULT_SCHEMA, ProcessSpec

from .adapters import ResourceRequest, build_process_spec

TEST_PROCESS_PRIORITY = 100


class HubProcessAdapterError(RuntimeError):
    """Fail-closed adapter error with a stable machine-readable reason."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code
        self.detail = detail


class HubProcessClient(Protocol):
    def claim(self, *, role: str, stage: str, context: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def status(self, handle: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def send(
        self, handle: Mapping[str, Any], stage_input: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...
    def collect(self, handle: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def cancel(self, handle: Mapping[str, Any], *, reason: str) -> Mapping[str, Any]: ...
    def recover(self, handle: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class QualityToolRequest:
    run_id: str
    task_id: str
    attempt_id: str
    stage_id: str
    agent_id: str
    argv: tuple[str, ...]
    cwd: str | None
    cwd_allowlist: tuple[str, ...]
    env: Mapping[str, str]
    env_allowlist: tuple[str, ...]
    resources: ResourceRequest
    max_output_bytes: int
    idempotency_key: str


@dataclass
class HubProcessSubmission:
    schema: str
    request: QualityToolRequest
    process_spec: ProcessSpec
    handle: Mapping[str, Any]
    process_id: str


@dataclass(frozen=True)
class QualityProcessReceipt:
    schema: str
    status: str
    reason_code: str
    run_id: str
    task_id: str
    attempt_id: str
    stage_id: str
    process_id: str
    spec_hash: str
    process_terminal: bool
    raw_evidence: Mapping[str, Any]


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _stable_id(value: Mapping[str, Any]) -> str:
    process_id = value.get("handle_id") or value.get("lease_id") or value.get("job_id")
    if not isinstance(process_id, str) or not process_id:
        raise HubProcessAdapterError("INVALID_HUB_RESPONSE", "Hub handle has no stable process id")
    return process_id


def _validate_request(request: QualityToolRequest) -> None:
    identities = (
        request.run_id,
        request.task_id,
        request.attempt_id,
        request.stage_id,
        request.agent_id,
        request.idempotency_key,
    )
    if any(not isinstance(value, str) or not value.strip() for value in identities):
        raise HubProcessAdapterError(
            "INVALID_IDENTITY", "all Loop and process identities are required"
        )
    if not isinstance(request.env, Mapping):
        raise HubProcessAdapterError("INVALID_PROCESS_SPEC", "environment must be a mapping")


class HubProcessAdapter:
    """Convert Quality tool requests to Hub data; never execute or schedule locally."""

    def __init__(self, hub: HubProcessClient) -> None:
        if hub is None:
            raise HubProcessAdapterError("HUB_UNAVAILABLE", "Hub client is required")
        self._hub = hub

    @staticmethod
    def _call(operation: Any, *args: Any, **kwargs: Any) -> Mapping[str, Any]:
        try:
            response = operation(*args, **kwargs)
        except HubQueueAgentError as exc:
            code = "STALE_FENCE" if exc.reason_code == "stale_fence" else "HUB_UNAVAILABLE"
            raise HubProcessAdapterError(code, str(exc)) from exc
        except (ConnectionError, OSError, RuntimeError) as exc:
            raise HubProcessAdapterError("HUB_UNAVAILABLE", str(exc)) from exc
        if not isinstance(response, Mapping):
            raise HubProcessAdapterError("INVALID_HUB_RESPONSE", "Hub response must be an object")
        return response

    def submit(self, request: QualityToolRequest) -> HubProcessSubmission:
        _validate_request(request)
        try:
            spec = build_process_spec(
                request.argv,
                cwd=request.cwd,
                cwd_allowlist=request.cwd_allowlist,
                env=request.env,
                env_allowlist=request.env_allowlist,
                timeout_seconds=request.resources.timeout_seconds,
                max_output_bytes=request.max_output_bytes,
                priority=TEST_PROCESS_PRIORITY,
                idempotency_key=request.idempotency_key,
            )
        except (TypeError, ValueError) as exc:
            raise HubProcessAdapterError("INVALID_PROCESS_SPEC", str(exc)) from exc
        context = {
            "run_id": request.run_id,
            "task_id": request.task_id,
            "attempt_id": request.attempt_id,
            "stage_id": request.stage_id,
            "priority": "test",
            "resources": {
                "cpu_millis": request.resources.cpu_millis,
                "memory_mib": request.resources.memory_mib,
            },
            "resource_request": {
                "cpu": request.resources.cpu_millis,
                "memory_bytes": request.resources.memory_mib * 1024 * 1024,
                "disk_bytes": 0,
                "gpu": 0,
                "processes": 1,
                "connections": 0,
                "tokens": 0,
            },
            "timeout_seconds": request.resources.timeout_seconds,
            "process_spec": spec.to_dict(),
            "idempotency_key": request.idempotency_key,
        }
        handle = dict(self._call(
            self._hub.claim,
            role=request.agent_id,
            stage=request.stage_id,
            context=context,
        ))
        process_id = _stable_id(handle)
        sent = self._call(self._hub.send, handle, {"process_spec_hash": spec.spec_hash})
        updated = sent.get("handle")
        if isinstance(updated, Mapping):
            handle = dict(updated)
        return HubProcessSubmission(
            "simplicio.quality-hub-process-submission/v1",
            request,
            spec,
            handle,
            process_id,
        )

    def poll(self, submission: HubProcessSubmission) -> Mapping[str, Any]:
        response = self._call(self._hub.status, submission.handle)
        self._refresh_handle(submission, response)
        return _freeze(response)

    def reconnect(self, submission: HubProcessSubmission) -> Mapping[str, Any]:
        """Observe an existing handle after reconnect; never submit it again."""
        response = self._call(self._hub.recover, submission.handle)
        self._refresh_handle(submission, response)
        return _freeze(response)

    def collect(self, submission: HubProcessSubmission) -> QualityProcessReceipt:
        raw = dict(self._call(self._hub.collect, submission.handle))
        process_result = raw.get("process_result") or raw.get("result") or raw
        if (
            not isinstance(process_result, Mapping)
            or process_result.get("schema") != PROCESS_RESULT_SCHEMA
        ):
            return self._receipt(submission, "BLOCKED", "INVALID_HUB_RESPONSE", raw)
        required = {
            "returncode", "stdout", "stderr", "duration_seconds", "timed_out",
            "cancelled", "truncated", "error_code", "lease_id",
        }
        if not required.issubset(process_result):
            return self._receipt(submission, "BLOCKED", "INVALID_HUB_RESPONSE", raw)
        returncode = process_result["returncode"]
        duration = process_result["duration_seconds"]
        valid = (
            (returncode is None or type(returncode) is int)
            and isinstance(process_result["stdout"], str)
            and isinstance(process_result["stderr"], str)
            and type(duration) in {int, float}
            and math.isfinite(duration)
            and duration >= 0
            and type(process_result["timed_out"]) is bool
            and type(process_result["cancelled"]) is bool
            and type(process_result["truncated"]) is bool
            and isinstance(process_result["error_code"], str)
            and process_result["lease_id"] == submission.process_id
        )
        if not valid:
            return self._receipt(submission, "BLOCKED", "INVALID_HUB_RESPONSE", raw)
        if process_result.get("cancelled"):
            return self._receipt(submission, "CANCELLED", "HUB_CANCELLED", raw)
        if process_result.get("timed_out"):
            return self._receipt(submission, "BLOCKED", "PROCESS_TIMEOUT", raw)
        if process_result.get("truncated"):
            return self._receipt(submission, "BLOCKED", "OUTPUT_TRUNCATED", raw)
        if process_result.get("error_code") or process_result.get("returncode") != 0:
            return self._receipt(submission, "BLOCKED", "PROCESS_CRASHED", raw)
        return self._receipt(submission, "PASS", "PROCESS_SUCCEEDED", raw)

    def cancel(self, submission: HubProcessSubmission, reason: str) -> QualityProcessReceipt:
        if not isinstance(reason, str) or not reason.strip():
            raise HubProcessAdapterError("INVALID_CANCEL_REASON", "cancel reason is required")
        raw = dict(self._call(self._hub.cancel, submission.handle, reason=reason))
        self._refresh_handle(submission, raw)
        state = str(raw.get("state") or raw.get("status") or "")
        if state == "cancelled":
            return self._receipt(submission, "CANCELLED", "HUB_CANCELLED", raw)
        return self._receipt(
            submission, "BLOCKED", "HUB_CANCEL_PENDING", raw, process_terminal=False
        )

    @staticmethod
    def _refresh_handle(
        submission: HubProcessSubmission, response: Mapping[str, Any]
    ) -> None:
        updated = response.get("handle")
        if isinstance(updated, Mapping):
            submission.handle = dict(updated)
            submission.process_id = _stable_id(submission.handle)
            return
        execution = response.get("execution")
        if isinstance(execution, Mapping) and execution.get("fence") is not None:
            handle = dict(submission.handle)
            handle["fence"] = execution["fence"]
            submission.handle = handle

    @staticmethod
    def _receipt(
        submission: HubProcessSubmission,
        status: str,
        reason_code: str,
        raw: Mapping[str, Any],
        *,
        process_terminal: bool = True,
    ) -> QualityProcessReceipt:
        evidence = dict(raw)
        evidence["evidence_hash"] = hashlib.sha256(
            json.dumps(evidence, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        request = submission.request
        return QualityProcessReceipt(
            "simplicio.quality-process-receipt/v1",
            status,
            reason_code,
            request.run_id,
            request.task_id,
            request.attempt_id,
            request.stage_id,
            submission.process_id,
            submission.process_spec.spec_hash,
            process_terminal,
            _freeze(evidence),
        )
