import copy

import pytest
from simplicio_loop.process_supervisor import PROCESS_RESULT_SCHEMA

from simplicio_loop_quality.adapters import ResourceRequest
from simplicio_loop_quality.hub_process_adapter import (
    HubProcessAdapter,
    HubProcessAdapterError,
    QualityToolRequest,
)


def request():
    return QualityToolRequest(
        run_id="run-1",
        task_id="task-1",
        attempt_id="attempt-1",
        stage_id="testing",
        agent_id="test-executor",
        argv=("python", "-m", "pytest"),
        cwd=None,
        cwd_allowlist=(),
        env={"CI": "1"},
        env_allowlist=("CI",),
        resources=ResourceRequest(1000, 512, 30),
        max_output_bytes=4096,
        idempotency_key="run-1:testing:test-executor",
    )


def result(**overrides):
    value = {
        "schema": PROCESS_RESULT_SCHEMA,
        "returncode": 0,
        "stdout": "ok",
        "stderr": "",
        "duration_seconds": 0.1,
        "timed_out": False,
        "cancelled": False,
        "truncated": False,
        "error_code": "",
        "lease_id": "process-1",
    }
    value.update(overrides)
    return value


class FakeHub:
    def __init__(self, process_result=None):
        self.calls = []
        self.process_result = process_result or result()

    def claim(self, **kwargs):
        self.calls.append(("claim", kwargs))
        return {"handle_id": "process-1", "fence": 7, "idempotency_key": "idem"}

    def send(self, handle, stage_input):
        self.calls.append(("send", handle, stage_input))
        return {"ok": True}

    def status(self, handle):
        self.calls.append(("status", handle))
        return {"status": "running", "handle_id": "process-1"}

    def recover(self, handle):
        self.calls.append(("recover", handle))
        return {"status": "running", "handle_id": "process-1"}

    def collect(self, handle):
        self.calls.append(("collect", handle))
        return {"process_result": copy.deepcopy(self.process_result), "hub_receipt": "receipt-1"}

    def cancel(self, handle, *, reason):
        self.calls.append(("cancel", handle, reason))
        return {"status": "cancelled", "reason": reason}


def test_submit_propagates_process_spec_identity_limits_and_priority():
    hub = FakeHub()
    submission = HubProcessAdapter(hub).submit(request())
    assert [call[0] for call in hub.calls] == ["claim", "send"]
    context = hub.calls[0][1]["context"]
    assert context["priority"] == "test"
    assert context["run_id"] == "run-1"
    assert context["task_id"] == "task-1"
    assert context["attempt_id"] == "attempt-1"
    assert context["stage_id"] == "testing"
    assert context["resources"] == {"cpu_millis": 1000, "memory_mib": 512}
    assert context["resource_request"]["memory_bytes"] == 512 * 1024 * 1024
    assert context["resource_request"]["processes"] == 1
    assert context["process_spec"]["max_output_bytes"] == 4096
    assert context["process_spec"]["priority"] == 100
    assert context["process_spec"]["env"] == {"CI": "1"}
    assert context["process_spec"]["shell"] is False
    assert submission.process_id == "process-1"


def test_poll_reconnect_collect_and_cancel_never_resubmit():
    hub = FakeHub()
    adapter = HubProcessAdapter(hub)
    submission = adapter.submit(request())
    assert adapter.poll(submission)["status"] == "running"
    assert adapter.reconnect(submission)["status"] == "running"
    receipt = adapter.collect(submission)
    cancelled = adapter.cancel(submission, "operator_cancelled")
    assert receipt.status == "PASS"
    assert receipt.process_terminal is True
    assert receipt.raw_evidence["process_result"]["stdout"] == "ok"
    assert cancelled.status == "CANCELLED"
    assert [call[0] for call in hub.calls].count("claim") == 1


@pytest.mark.parametrize(
    ("mutation", "status", "reason"),
    [
        ({"timed_out": True}, "BLOCKED", "PROCESS_TIMEOUT"),
        ({"cancelled": True}, "CANCELLED", "HUB_CANCELLED"),
        ({"truncated": True}, "BLOCKED", "OUTPUT_TRUNCATED"),
        ({"returncode": 9}, "BLOCKED", "PROCESS_CRASHED"),
        ({"error_code": "oom"}, "BLOCKED", "PROCESS_CRASHED"),
    ],
)
def test_terminal_process_failures_are_receipted(mutation, status, reason):
    adapter = HubProcessAdapter(FakeHub(result(**mutation)))
    receipt = adapter.collect(adapter.submit(request()))
    assert (receipt.status, receipt.reason_code) == (status, reason)
    assert receipt.raw_evidence["evidence_hash"]


def test_hub_loss_invalid_responses_identity_and_allowlists_fail_closed():
    class LostHub(FakeHub):
        def claim(self, **kwargs):
            raise ConnectionError("hub lost")

    with pytest.raises(HubProcessAdapterError, match="hub lost") as lost:
        HubProcessAdapter(LostHub()).submit(request())
    assert lost.value.reason_code == "HUB_UNAVAILABLE"

    class InvalidHub(FakeHub):
        def claim(self, **kwargs):
            return []

    with pytest.raises(HubProcessAdapterError) as invalid:
        HubProcessAdapter(InvalidHub()).submit(request())
    assert invalid.value.reason_code == "INVALID_HUB_RESPONSE"

    bad_identity = request()
    bad_identity = QualityToolRequest(**{**bad_identity.__dict__, "run_id": ""})
    with pytest.raises(HubProcessAdapterError) as identity:
        HubProcessAdapter(FakeHub()).submit(bad_identity)
    assert identity.value.reason_code == "INVALID_IDENTITY"

    bad_env = request()
    bad_env = QualityToolRequest(**{**bad_env.__dict__, "env": {"SECRET": "x"}})
    with pytest.raises(HubProcessAdapterError) as unsafe:
        HubProcessAdapter(FakeHub()).submit(bad_env)
    assert unsafe.value.reason_code == "INVALID_PROCESS_SPEC"


def test_incompatible_process_result_blocks_and_raw_evidence_is_immutable():
    hub = FakeHub({"schema": "unknown/v1"})
    adapter = HubProcessAdapter(hub)
    receipt = adapter.collect(adapter.submit(request()))
    assert (receipt.status, receipt.reason_code) == ("BLOCKED", "INVALID_HUB_RESPONSE")
    with pytest.raises(TypeError):
        receipt.raw_evidence["changed"] = True


@pytest.mark.parametrize(
    "mutation",
    [
        {"returncode": False},
        {"stdout": []},
        {"stderr": {}},
        {"duration_seconds": "fast"},
        {"duration_seconds": float("nan")},
        {"timed_out": 0},
        {"cancelled": 0},
        {"truncated": 0},
        {"error_code": None},
        {"lease_id": "another-process"},
    ],
)
def test_hostile_or_cross_process_result_never_passes(mutation):
    adapter = HubProcessAdapter(FakeHub(result(**mutation)))
    receipt = adapter.collect(adapter.submit(request()))
    assert (receipt.status, receipt.reason_code) == ("BLOCKED", "INVALID_HUB_RESPONSE")
