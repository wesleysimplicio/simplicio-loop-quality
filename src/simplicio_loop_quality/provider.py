"""Productive Loop extension entry point for the Quality provider."""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import resources
from types import MappingProxyType
from typing import Any

from simplicio_loop_quality.contract_validation import validate_contract_document
from simplicio_loop_quality.adapters import ResourceRequest
from simplicio_loop_quality.hub_process_adapter import (
    HubProcessAdapter,
    HubProcessAdapterError,
    QualityToolRequest,
)

PROVIDER_VERSION = "1.0.0"


def _manifest() -> dict[str, Any]:
    resource = resources.files("simplicio_loop_quality.contracts").joinpath("loop-extension.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def _role_binding(request: Any = None, **_kwargs: Any) -> dict[str, Any]:
    """Reject direct role execution; stage dispatch must arrive through the Loop Hub."""

    if not isinstance(request, Mapping):
        return {
            "schema": "simplicio.quality-provider-binding-result/v1",
            "status": "BLOCKED",
            "reason_code": "INVALID_ROLE_REQUEST",
            "terminal": False,
        }
    return {
        "schema": "simplicio.quality-provider-binding-result/v1",
        "status": "BLOCKED",
        "reason_code": "HUB_STAGE_DISPATCH_REQUIRED",
        "terminal": False,
    }


def _publish_quality_receipt(receipt: Any = None, **_kwargs: Any) -> dict[str, Any]:
    """Validate a receipt but never publish or grant terminal authority locally."""

    errors = validate_contract_document(receipt)
    return {
        "schema": "simplicio.quality-provider-binding-result/v1",
        "status": "VALIDATED" if not errors else "BLOCKED",
        "reason_code": "RECEIPT_VALIDATED" if not errors else "INVALID_QUALITY_RECEIPT",
        "errors": tuple(errors),
        "terminal": False,
    }


@dataclass(frozen=True)
class QualityProviderRuntime:
    manifest: Mapping[str, Any]
    bindings: Mapping[str, Callable[..., Any]]


def provider() -> QualityProviderRuntime:
    """Return an immutable runtime object consumed by Loop's extension registry."""

    manifest = _manifest()
    role_ids = [row["role_id"] for row in manifest["role_bindings"]]
    effect_ids = [row["effect_id"] for row in manifest["effect_handlers"]]
    bindings: dict[str, Callable[..., Any]] = {role_id: _role_binding for role_id in role_ids}
    bindings.update({effect_id: _publish_quality_receipt for effect_id in effect_ids})
    return QualityProviderRuntime(MappingProxyType(manifest), MappingProxyType(bindings))


def capability_negotiate() -> dict[str, Any]:
    """Advertise the executable provider protocol to Loop's quality gate."""

    return {
        "version": PROVIDER_VERSION,
        "capabilities": {
            "structured_findings": True,
            "cancel_token": True,
            "hub_process_adapter": True,
            "per_run_matrix": True,
        },
    }


def _hub_adapter() -> HubProcessAdapter:
    """Build the only productive execution binding: the Loop Hub client."""

    from simplicio_loop.hub_daemon import HubSocketClient, default_endpoint, default_transport
    from simplicio_loop.hub_queue_agent import HubQueueAgentClient

    endpoint = os.environ.get("SIMPLICIO_LOOP_HUB_ENDPOINT") or default_endpoint()
    transport = os.environ.get("SIMPLICIO_LOOP_HUB_TRANSPORT") or default_transport()
    client = HubQueueAgentClient(
        HubSocketClient(endpoint, timeout=5.0, transport=transport),
        client_id="simplicio-loop-quality",
        worker_id="simplicio-loop-quality",
        strict=True,
    )
    return HubProcessAdapter(client)


def run(
    *,
    run_id: str,
    tasks: list[Any],
    attempt: int,
    repo: str,
    worktree: str,
    head: str,
    diff_hash: str,
    policy: str,
    cancel_token: Any = None,
) -> dict[str, Any]:
    """Run the repository quality check as a Hub-owned process.

    The provider performs no local process creation.  Hub loss, malformed
    receipts, timeout, cancellation and non-zero checks are all surfaced as
    BLOCKED/FAIL results for Loop's existing fail-closed gate.
    """

    del tasks, worktree, head, diff_hash, policy
    from pathlib import Path

    repo_path = Path(repo).resolve()
    check_script = repo_path / "scripts" / "check.py"
    if not check_script.is_file():
        return {
            "status": "BLOCKED",
            "findings": [{"level": "error", "message": "scripts/check.py not found"}],
            "receipts": [],
            "detail": "quality provider could not locate scripts/check.py",
        }
    try:
        adapter = _hub_adapter()
        request = QualityToolRequest(
            run_id=str(run_id),
            task_id=f"quality-check-{run_id}",
            attempt_id=f"attempt-{attempt}",
            stage_id="quality-check",
            agent_id="simplicio-loop-quality",
            argv=(sys.executable, str(check_script)),
            cwd=str(repo_path),
            cwd_allowlist=(str(repo_path),),
            env={},
            env_allowlist=(),
            resources=ResourceRequest(cpu_millis=1000, memory_mib=1024, timeout_seconds=120.0),
            max_output_bytes=262144,
            idempotency_key=f"{run_id}:quality-check:{attempt}",
        )
        submission = adapter.submit(request)
        deadline = time.monotonic() + 120.0
        while True:
            if cancel_token is not None and cancel_token.is_set():
                receipt = adapter.cancel(submission, "quality provider cancelled")
                return {"status": "BLOCKED", "findings": [], "receipts": [receipt.raw_evidence], "detail": receipt.reason_code}
            status = adapter.poll(submission)
            state = str(status.get("state") or status.get("status") or "")
            if state in {"completed", "passed", "failed", "cancelled", "timed_out", "crashed"}:
                break
            if time.monotonic() >= deadline:
                receipt = adapter.cancel(submission, "quality provider timeout")
                return {"status": "BLOCKED", "findings": [], "receipts": [receipt.raw_evidence], "detail": receipt.reason_code}
            time.sleep(0.05)
        receipt = adapter.collect(submission)
        raw = dict(receipt.raw_evidence)
        if receipt.status == "PASS":
            return {"status": "PASS", "findings": [], "receipts": [raw], "detail": receipt.reason_code}
        return {
            "status": "BLOCKED",
            "findings": [{"level": "error", "message": receipt.reason_code}],
            "receipts": [raw],
            "detail": receipt.reason_code,
        }
    except (HubProcessAdapterError, OSError, RuntimeError, ValueError) as exc:
        return {
            "status": "BLOCKED",
            "findings": [{"level": "error", "message": str(exc)}],
            "receipts": [],
            "detail": f"Hub quality process unavailable: {exc}",
        }
