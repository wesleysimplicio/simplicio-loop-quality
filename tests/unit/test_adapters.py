import asyncio
import copy
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from simplicio_loop_quality.adapters import (
    AdapterContractError,
    AdapterRequest,
    Cancellation,
    build_process_spec,
    discover_adapters,
    invoke_adapter,
    validate_descriptor,
)

CONTRACT_CORPUS = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "contracts-v1-corpus.json").read_text()
)


def valid_stage():
    return {
        "schema": "simplicio.quality-stage-result/v1",
        "identity": copy.deepcopy(CONTRACT_CORPUS["identity"]),
        "stage_id": "stage-1",
        "status": "BLOCKED",
        "started_at": "2026-08-01T00:00:00Z",
        "completed_at": "2026-08-01T00:00:01Z",
        "exit_code": None,
        "evidence": [],
        "metrics": [],
        "findings": [],
    }


def descriptor(adapter_id="python.pytest"):
    return {
        "schema": "simplicio.quality-adapter/v1",
        "adapter_id": adapter_id,
        "api_version": "1.0",
        "capabilities": ["test.run"],
        "output_schemas": ["simplicio.quality-stage-result/v1"],
        "resources": {"cpu_millis": 1000, "memory_mib": 512, "timeout_seconds": 30},
    }


def request(cancelled=False):
    return AdapterRequest(
        "simplicio.quality-adapter-request/v1",
        {"run_id": "run-1"},
        "test.run",
        {},
        Cancellation(cancelled, "operator_cancelled" if cancelled else None),
    )


class SyncAdapter:
    descriptor = descriptor()

    def invoke(self, _request):
        return valid_stage()


class AsyncAdapter(SyncAdapter):
    async def invoke(self, _request):
        return valid_stage()


class CrashAdapter(SyncAdapter):
    def invoke(self, _request):
        raise RuntimeError("plugin crash")


class HostileAdapter(SyncAdapter):
    descriptor = {**descriptor(), "capabilities": ["terminal"]}
    invoked = False

    def invoke(self, _request):
        self.invoked = True
        return {"schema": "simplicio.quality-stage-result/v1"}


def test_discovery_is_deterministic_and_immutable():
    values = [descriptor("z.adapter"), descriptor("a.adapter")]
    first = discover_adapters(values)
    second = discover_adapters(list(reversed(values)))
    assert [item.adapter_id for item in first] == ["a.adapter", "z.adapter"]
    assert first == second
    with pytest.raises(FrozenInstanceError):
        first[0].adapter_id = "changed"


def test_descriptor_hash_normalizes_declared_array_order():
    first = descriptor()
    first["capabilities"] = ["test.run", "quality.audit"]
    first["output_schemas"] = [
        "simplicio.quality-stage-result/v1",
        "simplicio.quality-evidence/v2",
    ]
    second = copy.deepcopy(first)
    second["capabilities"].reverse()
    second["output_schemas"].reverse()
    assert validate_descriptor(first).descriptor_hash == validate_descriptor(second).descriptor_hash


@pytest.mark.parametrize(
    "mutation",
    [
        lambda _value: ["not-an-object"],
        lambda value: value.update(extra=True),
        lambda value: value.update(adapter_id="Bad ID"),
        lambda value: value.update(api_version="one"),
        lambda value: value.update(api_version="2.0"),
        lambda value: value.update(capabilities=[]),
        lambda value: value.update(capabilities=["unknown"]),
        lambda value: value.update(capabilities=[{"hostile": True}]),
        lambda value: value.update(capabilities=["test.run", "test.run"]),
        lambda value: value.update(output_schemas=[]),
        lambda value: value.update(output_schemas=["unknown/v1"]),
        lambda value: value.update(output_schemas=[{"hostile": True}]),
        lambda value: value.update(resources={"cpu_millis": 1}),
        lambda value: value["resources"].update(cpu_millis=0),
        lambda value: value["resources"].update(memory_mib=0),
        lambda value: value["resources"].update(timeout_seconds=0),
    ],
)
def test_incompatible_descriptors_fail_before_invocation(mutation):
    value = copy.deepcopy(descriptor())
    value = mutation(value) or value
    with pytest.raises(AdapterContractError):
        validate_descriptor(value)


def test_published_conformance_corpus_is_fail_closed():
    corpus = json.loads(
        (Path(__file__).parents[1] / "fixtures" / "adapter-conformance-v1.json").read_text()
    )
    baseline = corpus["valid"][0]
    assert validate_descriptor(baseline).adapter_id == "python.pytest"
    for case in corpus["incompatible"] + corpus["hostile"]:
        candidate = copy.deepcopy(baseline)
        candidate.update(case["patch"])
        with pytest.raises(AdapterContractError):
            validate_descriptor(candidate)


def test_duplicate_adapter_ids_fail_closed():
    with pytest.raises(AdapterContractError, match="duplicate"):
        discover_adapters([descriptor(), descriptor()])


def test_native_process_spec_is_data_only():
    spec = build_process_spec(
        ["python", "-m", "pytest"], idempotency_key="run-1:stage-1", timeout_seconds=10
    )
    assert tuple(spec.argv) == ("python", "-m", "pytest")
    assert spec.shell is False
    with pytest.raises(AdapterContractError):
        build_process_spec([], idempotency_key="x")
    with pytest.raises(AdapterContractError):
        build_process_spec(["python"], idempotency_key="")
    with pytest.raises(AdapterContractError):
        build_process_spec(["python"], cwd="C:/Windows", idempotency_key="x")


@pytest.mark.parametrize("adapter_type", [SyncAdapter, AsyncAdapter])
def test_fake_sync_and_async_adapters_return_data(adapter_type):
    outcome = asyncio.run(invoke_adapter(adapter_type(), request()))
    assert outcome.status == "PASS"
    assert outcome.output["status"] == "BLOCKED"
    assert outcome.retry_hint is False


def test_crash_cancel_hostile_and_unknown_capability_never_become_pass():
    crashed = asyncio.run(invoke_adapter(CrashAdapter(), request()))
    assert (crashed.status, crashed.failure_code) == ("BLOCKED", "ADAPTER_CRASHED")
    cancelled = asyncio.run(invoke_adapter(SyncAdapter(), request(cancelled=True)))
    assert (cancelled.status, cancelled.failure_code) == ("CANCELLED", "ADAPTER_CANCELLED")
    hostile = HostileAdapter()
    with pytest.raises(AdapterContractError):
        asyncio.run(invoke_adapter(hostile, request()))
    assert hostile.invoked is False
    unknown = request()
    unknown = AdapterRequest(
        unknown.schema, unknown.identity, "unknown", unknown.payload, unknown.cancellation
    )
    with pytest.raises(AdapterContractError):
        asyncio.run(invoke_adapter(SyncAdapter(), unknown))


def test_adapter_cannot_claim_terminal_authority_or_return_unknown_schema():
    class AuthorityAdapter(SyncAdapter):
        def invoke(self, _request):
            return {"schema": "simplicio.quality-stage-result/v1", "terminal": True}

    class UnknownOutput(SyncAdapter):
        def invoke(self, _request):
            return {"schema": "unknown/v1"}

    class NonObjectOutput(SyncAdapter):
        def invoke(self, _request):
            return []

    for adapter in (AuthorityAdapter(), UnknownOutput(), NonObjectOutput()):
        outcome = asyncio.run(invoke_adapter(adapter, request()))
        assert (outcome.status, outcome.failure_code) == ("BLOCKED", "INVALID_ADAPTER_OUTPUT")


def test_adapter_receives_deeply_immutable_request_and_malformed_stage_blocks():
    class MutatingAdapter(SyncAdapter):
        def invoke(self, incoming):
            incoming.identity["run_id"] = "tampered"

    class BareStage(SyncAdapter):
        def invoke(self, _request):
            return {"schema": "simplicio.quality-stage-result/v1"}

    original = request()
    outcome = asyncio.run(invoke_adapter(MutatingAdapter(), original))
    assert (outcome.status, outcome.failure_code) == ("BLOCKED", "ADAPTER_CRASHED")
    assert original.identity["run_id"] == "run-1"
    malformed = asyncio.run(invoke_adapter(BareStage(), request()))
    assert (malformed.status, malformed.failure_code) == (
        "BLOCKED",
        "INVALID_ADAPTER_OUTPUT",
    )


def test_passed_output_is_detached_and_deeply_immutable():
    class HoldingAdapter(SyncAdapter):
        def __init__(self):
            self.result = valid_stage()

        def invoke(self, _request):
            return self.result

    adapter = HoldingAdapter()
    outcome = asyncio.run(invoke_adapter(adapter, request()))
    adapter.result["identity"]["run_id"] = "tampered-after-pass"
    assert outcome.status == "PASS"
    assert outcome.output["identity"]["run_id"] == "run-1"
    with pytest.raises(TypeError):
        outcome.output["identity"]["run_id"] = "tampered"
