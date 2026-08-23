import asyncio
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from simplicio_loop_quality.adapters import Cancellation
from simplicio_loop_quality.agent_sdk import (
    AgentSDKError,
    EvidenceEmitter,
    build_context,
    derive_idempotency_key,
    emit_result,
    plan_agent,
    run_catalog_conformance,
    verify_deterministic_plan,
)
from simplicio_loop_quality.agents import AGENTS

CORPUS = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "contracts-v1-corpus.json").read_text()
)
NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def context(**overrides):
    values = {
        "identity": copy.deepcopy(CORPUS["identity"]),
        "role_id": "unit_component_agent",
        "stage_id": "unit-1",
        "seed": 7,
        "deadline": "2026-08-02T00:00:00Z",
    }
    values.update(overrides)
    return build_context(**values)


def stage_request(ctx):
    return {
        "schema": "simplicio.quality-stage-request/v1",
        "identity": dict(ctx.identity),
        "stage_id": ctx.stage_id,
        "lane": "unit",
        "agent": ctx.role_id,
        "command": ["python", "-m", "pytest"],
        "timeout_ms": 1000,
    }


def stage_result(ctx, status="BLOCKED"):
    result = {
        "schema": "simplicio.quality-stage-result/v1",
        "identity": dict(ctx.identity),
        "stage_id": ctx.stage_id,
        "status": status,
        "started_at": "2026-08-01T00:00:00Z",
        "completed_at": "2026-08-01T00:00:01Z",
        "exit_code": None,
        "evidence": [],
        "metrics": [],
        "findings": [],
    }
    if status == "PASS":
        result["exit_code"] = 0
        result["evidence"] = [copy.deepcopy(CORPUS["evidence"])]
    elif status == "FAIL":
        result["exit_code"] = 1
    return result


class SyncAgent:
    role_id = "unit_component_agent"

    def plan(self, ctx):
        return {"schema": "simplicio.quality-agent-plan/v1", "stage_request": stage_request(ctx)}


class AsyncAgent(SyncAgent):
    async def plan(self, ctx):
        return super().plan(ctx)


class CrashAgent(SyncAgent):
    def plan(self, _ctx):
        raise RuntimeError("agent crash")


class NondeterministicAgent(SyncAgent):
    def __init__(self):
        self.count = 0

    def plan(self, ctx):
        self.count += 1
        result = super().plan(ctx)
        result["stage_request"]["command"].append(str(self.count))
        return result


@pytest.mark.parametrize("agent_type", [SyncAgent, AsyncAgent])
def test_same_context_and_seed_produce_same_plan(agent_type):
    ctx = context()
    first = asyncio.run(verify_deterministic_plan(agent_type(), ctx, now=NOW))
    second = asyncio.run(verify_deterministic_plan(agent_type(), ctx, now=NOW))
    assert first.status == second.status == "PLANNED"
    assert first.plan == second.plan
    assert first.plan.seed == 7
    assert first.plan.idempotency_key == derive_idempotency_key(
        ctx.identity, ctx.role_id, ctx.stage_id, ctx.seed
    )
    document = first.plan.to_document()
    assert document["seed"] == ctx.seed
    assert document["idempotency_key"] == ctx.idempotency_key
    assert first.lifecycle_binding["identity"]["source_sha"] == ctx.identity["source_sha"]
    assert first.lifecycle_binding["idempotency_key"] == ctx.idempotency_key


def test_seed_changes_idempotency_and_plan_digest_deterministically():
    first = context(seed=7)
    second = context(seed=8)
    first_plan = asyncio.run(plan_agent(SyncAgent(), first, now=NOW)).plan
    second_plan = asyncio.run(plan_agent(SyncAgent(), second, now=NOW)).plan
    assert first.idempotency_key != second.idempotency_key
    assert first_plan.digest != second_plan.digest


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"identity": {"run_id": "partial"}}, "identity"),
        ({"role_id": ""}, "role_id"),
        ({"role_id": "unknown_agent"}, "declared"),
        ({"stage_id": ""}, "stage_id"),
        ({"seed": -1}, "seed"),
        ({"deadline": "not-a-time"}, "deadline"),
        ({"idempotency_key": "caller-forged"}, "idempotency"),
    ],
)
def test_context_rejects_incomplete_or_forged_bindings(changes, message):
    with pytest.raises(AgentSDKError, match=message):
        context(**changes)


def test_cancel_deadline_crash_and_wrong_role_fail_closed_without_retry():
    cancelled = context(cancellation=Cancellation(True, "operator_cancelled"))
    outcome = asyncio.run(plan_agent(SyncAgent(), cancelled, now=NOW))
    assert (outcome.status, outcome.failure_code, outcome.retry_hint) == (
        "CANCELLED",
        "AGENT_CANCELLED",
        False,
    )
    expired = context(deadline="2026-07-31T00:00:00Z")
    outcome = asyncio.run(plan_agent(SyncAgent(), expired, now=NOW))
    assert (outcome.status, outcome.failure_code) == ("BLOCKED", "AGENT_DEADLINE_EXCEEDED")
    outcome = asyncio.run(plan_agent(CrashAgent(), context(), now=NOW))
    assert (outcome.status, outcome.failure_code) == ("BLOCKED", "AGENT_CRASHED")
    wrong = SyncAgent()
    wrong.role_id = "security_agent"
    with pytest.raises(AgentSDKError, match="role"):
        asyncio.run(plan_agent(wrong, context(), now=NOW))


def test_live_cancellation_port_is_observable_during_async_planning():
    class Signal:
        cancelled = False

        def is_cancelled(self):
            return self.cancelled

    signal = Signal()
    started = asyncio.Event()
    release = asyncio.Event()

    class WaitingAgent(SyncAgent):
        async def plan(self, ctx):
            started.set()
            await release.wait()
            assert ctx.cancellation_requested()
            return super().plan(ctx)

    async def drive():
        task = asyncio.create_task(
            plan_agent(WaitingAgent(), context(cancellation_port=signal), now=NOW)
        )
        await started.wait()
        signal.cancelled = True
        release.set()
        return await task

    outcome = asyncio.run(drive())
    assert (outcome.status, outcome.failure_code, outcome.retry_hint) == (
        "CANCELLED",
        "AGENT_CANCELLED",
        False,
    )


def test_crashing_cancellation_port_and_blocked_outcomes_preserve_audit_binding():
    class BrokenPort:
        def is_cancelled(self):
            raise RuntimeError("port unavailable")

    ctx = context(cancellation_port=BrokenPort())
    outcome = asyncio.run(plan_agent(SyncAgent(), ctx, now=NOW))
    assert (outcome.status, outcome.failure_code) == (
        "BLOCKED",
        "CANCELLATION_PORT_UNAVAILABLE",
    )
    assert outcome.lifecycle_binding["identity"]["policy_hash"] == ctx.identity["policy_hash"]
    crashed = asyncio.run(plan_agent(CrashAgent(), context(), now=NOW))
    assert crashed.lifecycle_binding["seed"] == 7


def test_invalid_stale_hostile_and_nondeterministic_plans_block():
    class InvalidAgent(SyncAgent):
        def plan(self, _ctx):
            return {"schema": "wrong/v1", "stage_request": {}}

    class StaleAgent(SyncAgent):
        def plan(self, ctx):
            result = super().plan(ctx)
            result["stage_request"]["identity"]["run_id"] = "stale"
            return result

    class AuthorityAgent(SyncAgent):
        def plan(self, ctx):
            result = super().plan(ctx)
            result["stage_request"]["merge"] = True
            return result

    class NonObjectStageAgent(SyncAgent):
        def plan(self, _ctx):
            return {"schema": "simplicio.quality-agent-plan/v1", "stage_request": None}

    cases = [
        (InvalidAgent(), "INVALID_AGENT_PLAN"),
        (StaleAgent(), "STALE_AGENT_BINDING"),
        (AuthorityAgent(), "AGENT_AUTHORITY_FORBIDDEN"),
        (NonObjectStageAgent(), "INVALID_AGENT_PLAN"),
        (NondeterministicAgent(), "NONDETERMINISTIC_AGENT_PLAN"),
    ]
    for agent, code in cases:
        outcome = asyncio.run(verify_deterministic_plan(agent, context(), now=NOW))
        assert (outcome.status, outcome.failure_code) == ("BLOCKED", code)


@pytest.mark.parametrize("status", ["PASS", "FAIL", "BLOCKED"])
def test_emitter_accepts_contract_valid_commit_and_policy_bound_results(status):
    ctx = context()
    result = stage_result(ctx, status)
    outcome = EvidenceEmitter(ctx).emit(result, now=NOW)
    assert outcome.status == status
    assert outcome.failure_code is None
    result["identity"]["run_id"] = "mutated-after-emit"
    assert outcome.result["identity"]["run_id"] == ctx.identity["run_id"]
    with pytest.raises(TypeError):
        outcome.result["identity"]["policy_hash"] = "tampered"


def test_emitter_rejects_stale_self_approval_invalid_and_authority_results():
    ctx = context()
    stale = stage_result(ctx)
    stale["identity"]["policy_hash"] = "0" * 64
    invalid = stage_result(ctx, "PASS")
    invalid["evidence"] = []
    self_approved = stage_result(ctx, "PASS")
    self_approved["evidence"][0]["audit_agent"] = self_approved["evidence"][0]["producer_agent"]
    authority = stage_result(ctx)
    authority["close_issue"] = True
    for value, code in [
        (stale, "STALE_AGENT_BINDING"),
        (invalid, "INVALID_AGENT_RESULT"),
        (self_approved, "INVALID_AGENT_RESULT"),
        (authority, "AGENT_AUTHORITY_FORBIDDEN"),
        ({"not_json": {object()}}, "INVALID_AGENT_RESULT"),
        ([], "INVALID_AGENT_RESULT"),
    ]:
        outcome = emit_result(ctx, value, now=NOW)
        assert (outcome.status, outcome.failure_code, outcome.retry_hint) == (
            "BLOCKED",
            code,
            False,
        )
        assert outcome.lifecycle_binding["identity"]["source_sha"] == ctx.identity["source_sha"]
        assert outcome.lifecycle_binding["idempotency_key"] == ctx.idempotency_key


def test_emitter_propagates_cancel_and_deadline_and_preserves_lifecycle_binding():
    cancelled = context(cancellation=Cancellation(True, "stop"))
    outcome = emit_result(cancelled, stage_result(cancelled, "PASS"), now=NOW)
    assert (outcome.status, outcome.failure_code) == ("CANCELLED", "AGENT_CANCELLED")
    assert outcome.lifecycle_binding["seed"] == cancelled.seed
    expired = context(deadline="2026-07-31T00:00:00Z")
    outcome = EvidenceEmitter(expired).emit(stage_result(expired, "PASS"), now=NOW)
    assert (outcome.status, outcome.failure_code) == (
        "BLOCKED",
        "AGENT_DEADLINE_EXCEEDED",
    )


def test_published_conformance_fixture_covers_required_states_and_authority():
    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures" / "agent-sdk-conformance-v1.json").read_text()
    )
    assert set(fixture["states"]) == {"PASS", "FAIL", "BLOCKED", "CANCELLED", "CRASH"}
    assert all(not state["retry_hint"] for state in fixture["states"].values())
    assert {"schedule", "hub.submit", "terminal", "close_issue", "merge"} <= set(
        fixture["forbidden_authority"]
    )


def test_shared_conformance_suite_runs_every_declared_agent():
    class CatalogAgent(SyncAgent):
        def __init__(self, role_id):
            self.role_id = role_id

    agents = {spec.role_id: CatalogAgent(spec.role_id) for spec in AGENTS}
    contexts = {
        spec.role_id: context(role_id=spec.role_id, stage_id=f"stage-{index}")
        for index, spec in enumerate(AGENTS)
    }
    outcomes = asyncio.run(run_catalog_conformance(agents, contexts, now=NOW))
    assert set(outcomes) == {spec.role_id for spec in AGENTS}
    assert all(outcome.status == "PLANNED" for outcome in outcomes.values())
    with pytest.raises(TypeError):
        outcomes["extra"] = None
    with pytest.raises(AgentSDKError, match="every declared"):
        asyncio.run(run_catalog_conformance({}, {}, now=NOW))
