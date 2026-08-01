"""Auditable, deterministic data lifecycle for Quality agents."""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from simplicio_loop_quality.adapters import Cancellation
from simplicio_loop_quality.agents import AGENTS, agent_ids
from simplicio_loop_quality.contract_validation import validate_contract_document

PLAN_SCHEMA = "simplicio.quality-agent-plan/v1"
OUTCOME_SCHEMA = "simplicio.quality-agent-outcome/v1"
IDENTITY_FIELDS = frozenset(
    {
        "run_id",
        "task_id",
        "attempt_id",
        "source_sha",
        "tree_hash",
        "diff_hash",
        "policy_hash",
        "config_hash",
        "toolchain_hash",
    }
)
FORBIDDEN_AUTHORITY_FIELDS = frozenset(
    {
        "terminal",
        "ready",
        "schedule",
        "retry",
        "hub_submit",
        "hub.submit",
        "oracle",
        "oracle_complete",
        "close_issue",
        "merge",
        "delivery",
    }
)


class AgentSDKError(ValueError):
    """Agent lifecycle input or output violates the SDK contract."""


@runtime_checkable
class CancellationPort(Protocol):
    def is_cancelled(self) -> bool: ...


@dataclass(frozen=True)
class AgentContext:
    identity: Mapping[str, Any]
    role_id: str
    stage_id: str
    seed: int
    idempotency_key: str
    deadline: str
    cancellation: Cancellation
    cancellation_port: CancellationPort | None = None

    def cancellation_requested(self) -> bool:
        return self.cancellation.requested or bool(
            self.cancellation_port and self.cancellation_port.is_cancelled()
        )


@dataclass(frozen=True)
class AgentPlan:
    schema: str
    stage_request: Mapping[str, Any]
    seed: int
    idempotency_key: str
    digest: str

    def to_document(self) -> Mapping[str, Any]:
        return _freeze(
            {
                "schema": self.schema,
                "stage_request": _thaw(self.stage_request),
                "seed": self.seed,
                "idempotency_key": self.idempotency_key,
                "digest": self.digest,
            }
        )


@dataclass(frozen=True)
class AgentOutcome:
    schema: str
    status: str
    plan: AgentPlan | None
    result: Mapping[str, Any] | None
    failure_code: str | None
    retry_hint: bool
    lifecycle_binding: Mapping[str, Any] | None = None


@runtime_checkable
class QualityAgent(Protocol):
    role_id: str

    def plan(self, context: AgentContext) -> Mapping[str, Any] | Awaitable[Mapping[str, Any]]: ...


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def derive_idempotency_key(
    identity: Mapping[str, Any], role_id: str, stage_id: str, seed: int
) -> str:
    return canonical_hash(
        {
            "identity": dict(identity),
            "role_id": role_id,
            "stage_id": stage_id,
            "seed": seed,
        }
    )


def build_context(
    *,
    identity: Mapping[str, Any],
    role_id: str,
    stage_id: str,
    seed: int,
    deadline: str,
    cancellation: Cancellation | None = None,
    cancellation_port: CancellationPort | None = None,
    idempotency_key: str | None = None,
) -> AgentContext:
    """Validate and freeze the complete context before agent code observes it."""

    if not isinstance(identity, Mapping) or set(identity) != IDENTITY_FIELDS:
        raise AgentSDKError("identity fields are incomplete or ambiguous")
    if not isinstance(role_id, str) or not role_id.strip():
        raise AgentSDKError("role_id is required")
    if role_id not in agent_ids():
        raise AgentSDKError("role_id is not declared")
    if not isinstance(stage_id, str) or not stage_id.strip():
        raise AgentSDKError("stage_id is required")
    identity_errors = validate_contract_document(
        {
            "schema": "simplicio.quality-stage-request/v1",
            "identity": dict(identity),
            "stage_id": stage_id,
            "lane": "context_validation",
            "agent": role_id,
            "command": ["context-only"],
            "timeout_ms": 1,
        }
    )
    if identity_errors:
        raise AgentSDKError("identity is invalid: " + "; ".join(identity_errors))
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise AgentSDKError("seed must be a non-negative integer")
    if _parse_timestamp(deadline) is None:
        raise AgentSDKError("deadline must be an aware timestamp")
    expected_key = derive_idempotency_key(identity, role_id, stage_id, seed)
    if idempotency_key is not None and idempotency_key != expected_key:
        raise AgentSDKError("idempotency key does not match context")
    return AgentContext(
        _freeze(dict(identity)),
        role_id,
        stage_id,
        seed,
        expected_key,
        deadline,
        cancellation or Cancellation(False, None),
        cancellation_port,
    )


async def plan_agent(
    agent: QualityAgent, context: AgentContext, *, now: datetime | None = None
) -> AgentOutcome:
    """Invoke planning once and normalize cancel/deadline/crash without retries."""

    state = _preflight_state(context, now=now)
    if state is not None:
        return state
    if agent.role_id != context.role_id:
        raise AgentSDKError("agent role does not match context")
    try:
        raw = agent.plan(context)
        if inspect.isawaitable(raw):
            raw = await raw
    except Exception:
        return _blocked("AGENT_CRASHED", context)
    state = _preflight_state(context, now=now)
    if state is not None:
        return state
    if not isinstance(raw, Mapping) or set(raw) != {"schema", "stage_request"}:
        return _blocked("INVALID_AGENT_PLAN", context)
    if raw.get("schema") != PLAN_SCHEMA:
        return _blocked("INVALID_AGENT_PLAN", context)
    raw_stage_request = raw.get("stage_request")
    if not isinstance(raw_stage_request, Mapping):
        return _blocked("INVALID_AGENT_PLAN", context)
    stage_request = dict(raw_stage_request)
    if stage_request.get("identity") != dict(context.identity):
        return _blocked("STALE_AGENT_BINDING", context)
    if stage_request.get("stage_id") != context.stage_id:
        return _blocked("STALE_AGENT_BINDING", context)
    if set(stage_request) & FORBIDDEN_AUTHORITY_FIELDS:
        return _blocked("AGENT_AUTHORITY_FORBIDDEN", context)
    if validate_contract_document(stage_request):
        return _blocked("INVALID_AGENT_PLAN", context)
    frozen_request = _freeze(stage_request)
    plan_payload = {
        "schema": PLAN_SCHEMA,
        "stage_request": stage_request,
        "seed": context.seed,
        "idempotency_key": context.idempotency_key,
    }
    plan = AgentPlan(
        PLAN_SCHEMA,
        frozen_request,
        context.seed,
        context.idempotency_key,
        canonical_hash(plan_payload),
    )
    return AgentOutcome(OUTCOME_SCHEMA, "PLANNED", plan, None, None, False, _binding(context))


def emit_result(
    context: AgentContext,
    result: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> AgentOutcome:
    """Validate, bind and detach a stage result/evidence document."""

    state = _preflight_state(context, now=now)
    if state is not None:
        return state
    if not isinstance(result, Mapping):
        return _blocked("INVALID_AGENT_RESULT", context)
    try:
        detached = json.loads(json.dumps(result))
    except (TypeError, ValueError):
        return _blocked("INVALID_AGENT_RESULT", context)
    if set(detached) & FORBIDDEN_AUTHORITY_FIELDS:
        return _blocked("AGENT_AUTHORITY_FORBIDDEN", context)
    if detached.get("identity") != dict(context.identity):
        return _blocked("STALE_AGENT_BINDING", context)
    if (
        detached.get("schema") == "simplicio.quality-stage-result/v1"
        and detached.get("stage_id") != context.stage_id
    ):
        return _blocked("STALE_AGENT_BINDING", context)
    errors = validate_contract_document(detached)
    if errors:
        return _blocked("INVALID_AGENT_RESULT", context)
    return AgentOutcome(
        OUTCOME_SCHEMA,
        str(detached.get("status", "RECORDED")),
        None,
        _freeze(detached),
        None,
        False,
        _binding(context),
    )


class EvidenceEmitter:
    """Context-bound emitter that never executes commands or grants authority."""

    def __init__(self, context: AgentContext):
        self._context = context

    def emit(self, result: Mapping[str, Any], *, now: datetime | None = None) -> AgentOutcome:
        return emit_result(self._context, result, now=now)


async def verify_deterministic_plan(
    agent: QualityAgent, context: AgentContext, *, now: datetime | None = None
) -> AgentOutcome:
    """Run shared conformance twice and fail closed on nondeterministic plans."""

    first = await plan_agent(agent, context, now=now)
    second = await plan_agent(agent, context, now=now)
    if first.status != "PLANNED" or second.status != "PLANNED":
        return first if first.status != "PLANNED" else second
    if first.plan != second.plan:
        return _blocked("NONDETERMINISTIC_AGENT_PLAN", context)
    return first


async def run_catalog_conformance(
    agents: Mapping[str, QualityAgent],
    contexts: Mapping[str, AgentContext],
    *,
    now: datetime | None = None,
) -> Mapping[str, AgentOutcome]:
    """Run the shared deterministic planning contract against every declared role."""

    expected = {spec.role_id for spec in AGENTS}
    if set(agents) != expected or set(contexts) != expected:
        raise AgentSDKError("conformance suite must cover every declared agent exactly once")
    outcomes: dict[str, AgentOutcome] = {}
    for role_id in sorted(expected):
        if agents[role_id].role_id != role_id or contexts[role_id].role_id != role_id:
            raise AgentSDKError("conformance role binding mismatch")
        outcomes[role_id] = await verify_deterministic_plan(
            agents[role_id], contexts[role_id], now=now
        )
    return MappingProxyType(outcomes)


def _preflight_state(context: AgentContext, *, now: datetime | None) -> AgentOutcome | None:
    try:
        cancellation_requested = context.cancellation_requested()
    except Exception:
        return _blocked("CANCELLATION_PORT_UNAVAILABLE", context)
    if cancellation_requested:
        return AgentOutcome(
            OUTCOME_SCHEMA,
            "CANCELLED",
            None,
            None,
            "AGENT_CANCELLED",
            False,
            _binding(context),
        )
    deadline = _parse_timestamp(context.deadline)
    current = now or datetime.now(timezone.utc)
    if deadline is None or deadline <= current:
        return _blocked("AGENT_DEADLINE_EXCEEDED", context)
    return None


def _blocked(code: str, context: AgentContext | None = None) -> AgentOutcome:
    return AgentOutcome(
        OUTCOME_SCHEMA,
        "BLOCKED",
        None,
        None,
        code,
        False,
        _binding(context) if context is not None else None,
    )


def _binding(context: AgentContext) -> Mapping[str, Any]:
    return _freeze(
        {
            "identity": _thaw(context.identity),
            "role_id": context.role_id,
            "stage_id": context.stage_id,
            "seed": context.seed,
            "idempotency_key": context.idempotency_key,
        }
    )


def _parse_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
